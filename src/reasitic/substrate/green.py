"""Multi-layer substrate Green's function via Sommerfeld integration.

For a planar inductor over a stratified substrate (silicon + oxide
+ optional metal back-plane) the proper electromagnetic coupling
goes via the Green's function for an electric current source above
the stack. The textbook result is a Sommerfeld integral over the
radial wavenumber ``k_ρ``:

.. math::

    G(z, z'; \\rho) = \\frac{1}{4\\pi} \\int_0^\\infty
        \\frac{k_\\rho}{k_z}\\,
        \\bigl(e^{-jk_z|z-z'|} + R(k_\\rho) e^{-jk_z(z+z')}\\bigr)
        J_0(k_\\rho \\rho)\\, dk_\\rho

where ``R(k_ρ)`` is the layered-stack reflection coefficient and
``k_z = \\sqrt{k_0^2 \\varepsilon_r - k_\\rho^2}``.

The original ASITIC binary precomputes this Green's function on a
2-D grid via FFT-based convolution (``compute_green_function`` at
``0x0808c350``, ``fft_setup``, ``fft_apply_to_green``). For the
clean-room Python port we instead evaluate the integral on demand
with ``scipy.integrate.quad``. This trades performance for
clarity: per-pair evaluation is ~10 ms vs the FFT's amortised
~10 μs. For research-scale spirals (≤ 100 segments) the cost is
manageable.

The implementation here is the **quasi-static** limit: we drop
``e^{-jk_z|z|}`` factors and compute the static Green's function
``G_qs(ρ) = (1/4πε₀ε_eff) · 1/sqrt(ρ² + h²)`` enhanced by the
multi-layer reflection-coefficient kernel. This captures the
substrate-coupled capacitance with reasonable accuracy at the
megahertz-to-low-GHz range without incurring the full Bessel-
function integration cost.
"""

from __future__ import annotations

import cmath
import math

import scipy.integrate

from reasitic.tech import Tech
from reasitic.units import EPS_0, UM_TO_M

# Magic constant from the binary: 2π · μ₀ ≈ 7.8957e-6 (in SI, F/m → H/m).
# Mirrors the literal at decomp/output/asitic_kernel.c:13254 (and twin
# at :13273) inside complex_propagation_constant_a/b.
TWO_PI_MU0 = 7.895683520871488e-06


def propagation_constant(
    k_rho: float,
    omega_rad: float,
    sigma_S_per_m: float,
) -> complex:
    """Complex propagation constant for one substrate layer.

    Mirrors the binary's ``complex_propagation_constant_a`` and ``_b``
    (decomp addresses ``0x0809421c`` and ``0x08094268``):

    .. math::

        \\gamma = \\sqrt{k_\\rho^2 + j \\, 2\\pi\\mu_0 \\sigma \\omega}

    The square root is the principal complex sqrt (positive real
    part), matching the convention of the libstdc++ ``sqrt(complex)``
    used in the binary.

    Args:
        k_rho:           Radial wavenumber in 1/m.
        omega_rad:       Angular frequency in rad/s.
        sigma_S_per_m:   Bulk conductivity in S/m.

    Returns:
        Complex ``γ`` in 1/m.
    """
    z2 = k_rho * k_rho + 1j * TWO_PI_MU0 * sigma_S_per_m * omega_rad
    return cmath.sqrt(z2)


def green_oscillating_integrand(
    k_rho: float,
    omega_rad: float,
    sigma_a_S_per_m: float,
    sigma_b_S_per_m: float,
    layer_thickness_m: float,
    rho_m: float,
) -> complex:
    """Sommerfeld integrand with an oscillating ``cos(k·ρ)`` factor.

    Mirrors ``green_oscillating_integrand`` (decomp ``0x080937cc``)
    — the ``code *`` plugged into QUADPACK's DQAWF cosine-weighted
    driver. Combines two layer propagation constants ``γ_a`` /
    ``γ_b`` (computed via :func:`propagation_constant`) with a
    ``tanh(γ_a · t)`` boundary factor, then returns the rational
    expression that — once multiplied by ``cos(k_ρ ρ)`` and
    integrated over k_ρ — gives the layered-substrate Green's
    function in the cosine-transform form.

    Args:
        k_rho:            Radial wavenumber (1/m) — the integration
                          variable.
        omega_rad:        Angular frequency (rad/s).
        sigma_a_S_per_m:  Conductivity of layer A.
        sigma_b_S_per_m:  Conductivity of layer B.
        layer_thickness_m: Thickness of the bottom layer (m).
        rho_m:            Source-field horizontal separation (m).
    """
    gamma_a = propagation_constant(k_rho, omega_rad, sigma_a_S_per_m)
    gamma_b = propagation_constant(k_rho, omega_rad, sigma_b_S_per_m)
    # Note rho_m only enters via the cosine weighting in the QUADPACK
    # DQAWF wrapper; the integrand here is the kernel without the
    # cos factor (DQAWF supplies that).
    _ = rho_m  # kept for API symmetry with the binary's signature
    # Boundary-condition factor between layer A and layer B
    # (cosh / sinh of γ_a × thickness, i.e. tanh)
    arg = gamma_a * layer_thickness_m
    if arg.real > 50.0:
        boundary = 1.0 + 0j
    elif arg.real < -50.0:
        boundary = -1.0 + 0j
    else:
        boundary = cmath.tanh(arg)
    # Standard layered-Green's combination:
    #     I = (k - γ_a · boundary) / (γ_b * (k + γ_a · boundary))
    # which is the rational expression the binary assembles via its
    # FPU stack shuffle.
    num = k_rho - gamma_a * boundary
    den = gamma_b * (k_rho + gamma_a * boundary)
    if den == 0:
        return 0j
    return num / den


def green_propagation_integrand(
    k_rho: float,
    omega_rad: float,
    sigma_a_S_per_m: float,
    sigma_b_S_per_m: float,
    layer_thickness_m: float,
    z_m: float,
) -> complex:
    """Sommerfeld integrand with an exponential ``e^{-γ z}`` propagation factor.

    Mirrors ``green_propagation_integrand`` (decomp ``0x08093b34``).
    Like :func:`green_oscillating_integrand` but with a vertical
    decay factor for the field point at height ``z`` above the
    substrate stack rather than a horizontal cosine modulation.
    """
    gamma_a = propagation_constant(k_rho, omega_rad, sigma_a_S_per_m)
    gamma_b = propagation_constant(k_rho, omega_rad, sigma_b_S_per_m)
    # Vertical decay through the substrate
    decay = cmath.exp(-2.0 * gamma_a * layer_thickness_m)
    # Boundary condition factor: (1 + decay) / (1 - decay) inverted
    # for the propagation form
    enum = (1.0 + decay) - 1.0  # = decay
    eden = (1.0 + decay) + 1.0
    boundary = enum / eden if eden != 0 else 0j
    # Source-field separation factor
    arg = -gamma_a * z_m
    propagation = 0j if arg.real < -50.0 else cmath.exp(arg)
    # Combine
    den = gamma_b * (k_rho + gamma_a * boundary)
    if den == 0:
        return 0j
    return (propagation * (k_rho - gamma_a * boundary)) / den


def green_function_kernel_a_oscillating(
    k_rho: float,
    *,
    omega_rad: float,
    sigma_a_S_per_m: float,
    sigma_b_S_per_m: float,
    layer_thickness_m: float,
    z_m: float,
) -> float:
    """Green's-function inner kernel with the ``2^{-k h / ln2}`` damping factor.

    Mirrors ``green_function_kernel_a_oscillating`` (decomp
    ``0x080948d0``). Multiplies :func:`green_oscillating_integrand`
    by ``exp(-k_ρ z)/k_ρ`` (the ``2^{-k·z / ln 2} / k`` factor in
    the binary, which is just a clever ``f2xm1 / fscale``-friendly
    form of ``e^{-k·z}/k``). Returns the **real** part because the
    QUADPACK driver only consumes that.
    """
    if k_rho <= 0:
        return 0.0
    integrand = green_oscillating_integrand(
        k_rho, omega_rad,
        sigma_a_S_per_m, sigma_b_S_per_m,
        layer_thickness_m, rho_m=0.0,
    )
    decay = math.exp(-k_rho * z_m)
    return float((integrand * decay / k_rho).real)


def green_function_kernel_b_reflection(
    k_rho: float,
    *,
    omega_rad: float,
    sigma_a_S_per_m: float,
    sigma_b_S_per_m: float,
    layer_thickness_m: float,
    z_m: float,
) -> float:
    """Green's-function inner kernel with the substrate reflection factor.

    Mirrors ``green_function_kernel_b_reflection``. Uses the
    :func:`layer_reflection_coefficient` ``Γ`` instead of the
    direct-source kernel, giving the *image* contribution to the
    layered-substrate Green's function. Returns the real part.
    """
    if k_rho <= 0:
        return 0.0
    integrand = green_oscillating_integrand(
        k_rho, omega_rad,
        sigma_a_S_per_m, sigma_b_S_per_m,
        layer_thickness_m, rho_m=0.0,
    )
    R = layer_reflection_coefficient(k_rho, omega_rad, sigma_b_S_per_m)
    decay = math.exp(-k_rho * z_m)
    return float((integrand * R * decay / k_rho).real)


def green_function_select_integrator(
    integrand_kind: str,
    omega_rad: float,
    *,
    lower: float = 0.0,
    upper: float = float("inf"),
    integrand_args: dict[str, float] | None = None,
) -> float:
    """Adaptively choose between the cosine-weighted and infinite-range
    Sommerfeld integrators.

    Mirrors ``green_function_select_integrator`` (decomp ``0x080949dc``):
    if ``|omega| ≥ 1e-10`` the binary uses QUADPACK's DQAWF (cosine-
    weighted Fourier integrator) on the oscillating-integrand path;
    otherwise it uses DQAGI (infinite-range adaptive integrator).
    The result is then multiplied by ``-μ₀ · ω`` to produce the
    final contribution to the substrate Green's function.

    The Python equivalent uses :func:`scipy.integrate.quad` for
    both paths since scipy's quad handles oscillation and infinite
    ranges adaptively. Returns ``-μ₀ · ω · ∫ integrand dk``.

    Args:
        integrand_kind:    ``"oscillating"`` or ``"propagation"`` —
                           selects which integrand to evaluate (see
                           :func:`green_oscillating_integrand` and
                           :func:`green_propagation_integrand`).
        omega_rad:         Angular frequency.
        lower, upper:      Integration limits.
        integrand_args:    Extra keyword arguments forwarded to the
                           chosen integrand (sigma_a/b, layer_thickness,
                           rho_m / z_m).
    """
    from collections.abc import Callable

    import scipy.integrate
    args = integrand_args or {}
    f: Callable[..., complex]
    if integrand_kind == "oscillating":
        f = green_oscillating_integrand
    elif integrand_kind == "propagation":
        f = green_propagation_integrand
    else:
        raise ValueError(
            f"unknown integrand_kind {integrand_kind!r}; "
            "use 'oscillating' or 'propagation'"
        )

    # scipy.quad operates on real-valued integrands; we take the real
    # part of the integrand here for the layered-Green's static path.
    # The full complex integral can be done by repeating with .imag.
    def _real_integrand(k_rho: float) -> float:
        return float(f(k_rho, omega_rad, **args).real)

    val, _err = scipy.integrate.quad(
        _real_integrand, lower, upper, limit=200,
    )
    MU_0 = 4.0e-7 * math.pi
    return float(-MU_0 * omega_rad * val)


def green_kernel_shared_helper(
    k_rho: float,
    z_a_um: float,
    z_b_um: float,
) -> float:
    """Region-independent (Coulomb-like) static term of the
    substrate Green's function.

    Mirrors ``green_kernel_shared_helper_a`` (decomp ``0x0808f80c``)
    and its sister ``_b`` (``0x0808f004``). The two share the same
    static body but accept slightly different argument layouts in
    the binary; in our cleaner Python API we collapse them to a
    single function. Returns the ``1 / (4 π ε₀ √(ρ² + (z_a + z_b)²))``
    image contribution at lateral wavenumber ``k_ρ``.
    """
    if k_rho <= 0:
        return 0.0
    z_um = z_a_um + z_b_um
    z_m = z_um * UM_TO_M
    return float(math.exp(-k_rho * z_m) / (2.0 * EPS_0 * k_rho))


def green_kernel_a_helper(
    k_rho: float,
    z_a_um: float,
    z_b_um: float,
    *,
    omega_rad: float = 0.0,
    sigma_S_per_m: float = 0.0,
) -> float:
    """Above-source region kernel helper.

    Mirrors ``green_kernel_a_helper`` (decomp ``0x0808fc04``). For
    the field point above the source layer this is the direct
    Coulomb kernel ``1/r`` plus a substrate-induced loss term
    ``Re(γ) · e^{-k(z_a+z_b)}``.
    """
    base = green_kernel_shared_helper(k_rho, z_a_um, z_b_um)
    if omega_rad == 0 or sigma_S_per_m == 0:
        return base
    gamma = propagation_constant(k_rho, omega_rad, sigma_S_per_m)
    z_um = z_a_um + z_b_um
    correction = (
        gamma.real
        * math.exp(-k_rho * z_um * UM_TO_M)
        / (2.0 * EPS_0)
    )
    return base + float(correction)


def green_kernel_b_helper(
    k_rho: float,
    z_a_um: float,
    z_b_um: float,
    *,
    omega_rad: float = 0.0,
    sigma_S_per_m: float = 0.0,
) -> float:
    """Below-source region kernel helper.

    Mirrors ``green_kernel_b_helper`` (decomp ``0x0808f3f0``). For
    the field point below the source: direct kernel minus the
    substrate reflection loss term. Sister of
    :func:`green_kernel_a_helper`.
    """
    base = green_kernel_shared_helper(k_rho, z_a_um, z_b_um)
    if omega_rad == 0 or sigma_S_per_m == 0:
        return base
    gamma = propagation_constant(k_rho, omega_rad, sigma_S_per_m)
    z_um = z_a_um + z_b_um
    correction = (
        gamma.real
        * math.exp(-k_rho * z_um * UM_TO_M)
        / (2.0 * EPS_0)
    )
    return base - float(correction)


def green_function_kernel_a(
    k_rho: float,
    *,
    z_a_um: float,
    z_b_um: float,
    omega_rad: float = 0.0,
    sigma_S_per_m: float = 0.0,
) -> float:
    """Top-level Sommerfeld integrand for the above-source region.

    Mirrors ``green_function_kernel_a`` (decomp ``0x0808cc90``) —
    the 3637-byte top-level integrand for the above-source half of
    the layered Green's function. Combines :func:`green_kernel_a_helper`
    with the propagation factor.
    """
    return green_kernel_a_helper(
        k_rho, z_a_um, z_b_um,
        omega_rad=omega_rad, sigma_S_per_m=sigma_S_per_m,
    )


def green_function_kernel_b(
    k_rho: float,
    *,
    z_a_um: float,
    z_b_um: float,
    omega_rad: float = 0.0,
    sigma_S_per_m: float = 0.0,
) -> float:
    """Top-level Sommerfeld integrand for the below-source region.

    Mirrors ``green_function_kernel_b`` (decomp ``0x0808dad4``).
    Sister to :func:`green_function_kernel_a` for the below-source
    half of the layered Green's function.
    """
    return green_kernel_b_helper(
        k_rho, z_a_um, z_b_um,
        omega_rad=omega_rad, sigma_S_per_m=sigma_S_per_m,
    )


def layer_reflection_coefficient(
    k_rho: float,
    omega_rad: float,
    sigma_S_per_m: float,
) -> complex:
    """Substrate reflection coefficient for one Bessel mode.

    Mirrors ``reflection_coeff_imag`` (decomp ``0x08093eb8``) but
    returns the *full* complex coefficient instead of just its
    imaginary part — callers can take ``.imag`` when they need to
    match the binary's narrowed return.

    .. math::

        \\Gamma(k_\\rho) = \\frac{k_\\rho - \\gamma(k_\\rho)}
                                 {k_\\rho + \\gamma(k_\\rho)}

    where ``γ`` is :func:`propagation_constant`. Verified against
    the C decomp:

    * line 13100: ``local_24 = k * k`` (sets up ``z = k²``)
    * line 13101: ``local_2c = DAT_080ceb40 * 7.895683520871488e-06 * omega``
      (imaginary part of γ²; ``DAT_080ceb40`` is the substrate
      conductivity σ at this layer, and ``7.895683520871488e-06``
      is ``2π·μ₀`` in SI — see :data:`TWO_PI_MU0`)
    * line 13105: ``sqrt(complex)`` evaluates ``γ = √(k² + j·2π·μ₀·σ·ω)``
    * lines 13106-13110: builds ``(k − γ)`` and ``(k + γ)`` then
      complex-divides to give Γ; the C narrows the return to
      ``Γ.imag``.

    At the static limit ``ω → 0`` (or ``σ → 0``), ``γ → k`` and
    therefore ``Γ → 0`` — the C model has no static stack
    reflection.
    """
    gamma = propagation_constant(k_rho, omega_rad, sigma_S_per_m)
    return (k_rho - gamma) / (k_rho + gamma)


def green_layer_tanh_factor(k_rho: float, dz_um: float) -> float:
    """Layered-Green's tanh boundary factor: ``tanh(k_ρ · Δz)``.

    Mirrors the inner ``(2^x − 1) / (2^x + 1) × sign`` computation
    that ``green_function_kernel_a`` (decomp ``0x0808cc90``, lines
    9630-9669) performs three times for different layer-boundary
    distances. The C builds it via the x87 ``f2xm1`` / ``fscale``
    instructions that compute ``2^x − 1`` directly:

    .. code-block:: c

        lVar15 = k_rho * (g_capacitance_options[p3] - z_obs);  // = k·Δz
        lVar11 = 1.4426950408889634 * -ABS(lVar15 + lVar15);   // = -2|k·Δz|/ln(2)
        // f2xm1+fscale: lVar14 = 2^lVar11 - 1 = exp(-2|k·Δz|) - 1
        lVar11 = 1.0; if (-lVar15 < 0.0) lVar11 = -1.0;        // sign of Δz
        dVar1 = (lVar14 / (lVar14 + 2.0)) * lVar11;

    Algebraically with ``u = exp(−2|k·Δz|)``::

        (u − 1) / ((u − 1) + 2) = (u − 1) / (u + 1) = −tanh(|k·Δz|)

    Multiplied by ``sign(Δz)``, the result is ``tanh(k_ρ · Δz)`` —
    the standard layered-substrate tanh boundary factor at one
    interface. The C-side magic constants (``0x080c8080 = -1.0``,
    ``0x080c8090 = 2.0``, ``0x080c80d0 = 0.0``,
    ``0x1.71547652b82fep+0 = 1.4426950408889634 = 1/ln 2``) are
    included in the rodata at the listed addresses.

    Args:
        k_rho:  radial wavenumber in 1/m.
        dz_um:  signed layer-boundary distance in microns
            (sign carries through to the tanh).

    Returns:
        ``tanh(k_ρ · Δz)``. Approaches 0 for ``k·Δz → 0`` and
        ``±1`` for large ``|k·Δz|``.
    """
    return math.tanh(k_rho * dz_um * UM_TO_M)


def _stack_reflection_coefficient(tech: Tech, k_rho: float) -> float:
    """Recursive layered-substrate reflection coefficient.

    Bottom-up recursion: starts at the substrate's deepest layer
    (assumed terminated by a perfect ground), then computes the
    reflection at each interface using the standard transmission-
    line formula::

        R_n = (Γ_n + R_{n+1} e^{-2 k_z h_{n+1}}) /
              (1 + Γ_n R_{n+1} e^{-2 k_z h_{n+1}})

    where ``Γ_n = (ε_n − ε_{n+1}) / (ε_n + ε_{n+1})`` is the
    Fresnel coefficient for normal incidence on the boundary.

    The ``k_rho`` argument is unused in the quasi-static limit but
    is retained for future full-EM extension.
    """
    if not tech.layers:
        return 0.0
    if k_rho <= 0:
        return 0.0
    # NOTE: the ASITIC C path (``reflection_coeff_imag`` at
    # ``asitic_kernel.c:13090``) does **not** use a static-limit
    # stack-composition formula. It evaluates a single-layer
    # frequency-dependent Fresnel coefficient
    # ``Γ = (k − γ) / (k + γ)`` with ``γ = sqrt(k² + j·const·σ·ω)``
    # and integrates the full Sommerfeld kernel
    # (``green_function_kernel_b_reflection`` at ``:13446``). At
    # ω → 0 the C coefficient collapses to zero — the C model has
    # no static stack reflection.
    #
    # Until the Sommerfeld pipeline is ported faithfully, this
    # function remains a quasi-static *stub* with the original
    # multi-layer recursion. Sign and iteration choices here are
    # not C-grounded; callers needing physical static reflection
    # values should not rely on this.
    R = 1.0  # stub initial value; see note above
    for upper, lower in zip(tech.layers[:-1], tech.layers[1:], strict=False):
        if upper.eps <= 0 or lower.eps <= 0:
            continue
        gamma = (upper.eps - lower.eps) / (upper.eps + lower.eps)
        h_m = lower.t * UM_TO_M
        attenuation = math.exp(-2.0 * k_rho * h_m)
        R = (gamma + R * attenuation) / (1.0 + gamma * R * attenuation)
    return R


def green_function_static(
    rho_um: float,
    z1_um: float,
    z2_um: float,
    tech: Tech,
) -> float:
    """Quasi-static substrate Green's function value, in V/C.

    ``rho_um`` is the lateral separation; ``z1_um`` / ``z2_um`` are
    the two source heights above the substrate. The result has units
    of inverse capacitance per length and is what gets convolved with
    the metal charge distribution to get coupled capacitances.

    For the full Sommerfeld integral (which this stub approximates
    via the leading 1/ρ kernel plus a layered reflection enhancement)
    we evaluate

    .. math::

        G(\\rho, z_1, z_2)
        = \\frac{1}{4\\pi\\varepsilon_0}
          \\bigl( \\frac{1}{r_+} + R_\\text{stack}(\\rho)\\,\\frac{1}{r_-} \\bigr)

    where ``r_± = sqrt(ρ² + (z₁ ∓ z₂)²)``.

    For ``rho_um → 0`` and same-layer pairs (``z₁ = z₂``) the direct
    1/r_+ term diverges. Callers that need a singular self-term
    (e.g. a same-tile diagonal in the per-segment cap matrix) should
    use :func:`rect_tile_self_inv_r` to compute the analytical
    finite-rectangle ⟨1/r⟩ instead. This function regularises the
    singular point with a 1 µm floor so it stays finite, but the
    floor is conservative (much smaller than typical tile sizes) and
    will overshoot the diagonal value if used as-is.
    """
    rho_m = max(rho_um, 1.0) * UM_TO_M
    z1_m = z1_um * UM_TO_M
    z2_m = z2_um * UM_TO_M
    r_plus = math.sqrt(rho_m**2 + (z1_m - z2_m) ** 2)
    r_minus = math.sqrt(rho_m**2 + (z1_m + z2_m) ** 2)
    # 1/k_ρ in the static limit; effective k for the reflection term
    k_eff = 1.0 / max(rho_m, 1e-30)
    R_stack = _stack_reflection_coefficient(tech, k_eff)
    return (1.0 / r_plus + R_stack / r_minus) / (4.0 * math.pi * EPS_0)


def rect_tile_self_inv_r(width_um: float, length_um: float) -> float:
    """Average of ``1/r`` over a uniformly-charged rectangular tile.

    Returns the finite, non-singular self-overlap integral

    .. math::

        \\langle 1/r \\rangle_\\text{self}
          = \\frac{1}{(ab)^2}
            \\int_0^a\\!\\int_0^a\\!\\int_0^b\\!\\int_0^b
              \\frac{1}{\\sqrt{(x-x')^2 + (y-y')^2}}
              \\,dx\\,dx'\\,dy\\,dy'

    in units of **1/m**. Multiplied by ``1/(4πε₀)`` it gives the
    average potential per unit charge for the tile, which is the
    correct diagonal entry of the MoM potential matrix.

    Closed form (Nabors-White 1991, Walker 1990):

    .. math::

        \\frac{4}{3 a^2 b^2}\\, \\bigl[
            -a^3 - b^3 + (a^2+b^2)^{3/2}
            + 3 a^2 b \\sinh^{-1}(b/a)
            + 3 a b^2 \\sinh^{-1}(a/b)
        \\bigr]

    Both ``width_um`` and ``length_um`` are in **microns**.
    """
    if width_um <= 0 or length_um <= 0:
        return 0.0
    a = width_um * UM_TO_M
    b = length_um * UM_TO_M
    a2 = a * a
    b2 = b * b
    sum2 = a2 + b2
    integral = (4.0 / 3.0) * (
        -a * a * a
        - b * b * b
        + math.sqrt(sum2) * sum2
        + 3.0 * a2 * b * math.asinh(b / a)
        + 3.0 * a * b2 * math.asinh(a / b)
    )
    return integral / (a2 * b2)


def coupled_capacitance_per_pair(
    rho_um: float,
    z1_um: float,
    z2_um: float,
    a1_um2: float,
    a2_um2: float,
    tech: Tech,
) -> float:
    """Mutual capacitance between two finite metal patches.

    The patches lie at heights ``z1`` / ``z2`` with footprint areas
    ``a1`` / ``a2`` and lateral separation ``rho`` (centre-to-centre).
    Returns C in farads.

    Uses the static Green's-function value evaluated at ``ρ`` as the
    inverse-distance kernel; for self-capacitance (ρ → 0) one of the
    patches' size becomes the regularising radius — we use
    ``ρ ← max(ρ, sqrt(a1)/π)`` to avoid the singularity.
    """
    if a1_um2 <= 0 or a2_um2 <= 0:
        return 0.0
    rho_eff = max(rho_um, math.sqrt(a1_um2) / math.pi, math.sqrt(a2_um2) / math.pi)
    G = green_function_static(rho_eff, z1_um, z2_um, tech)
    # Capacitance from areas via charge-Green's-function relation:
    # C = (a1 · a2) / (4π ε₀)⁻¹ · G  approximated by  ε₀ G a1 a2.
    # Convert μm² × μm² to m⁴ for consistent SI.
    area_factor = a1_um2 * a2_um2 * (UM_TO_M**4)
    if G == 0:
        return 0.0
    return area_factor / (G * UM_TO_M)


def integrate_green_kernel(
    rho_um: float,
    z1_um: float,
    z2_um: float,
    tech: Tech,
    *,
    k_max: float = 1.0e8,
) -> float:
    """Sommerfeld-style numerical Bessel-J0 integral.

    Numerically evaluates

    .. math::

        \\int_0^{k_\\text{max}} \\frac{1}{k_\\rho}
            R_\\text{stack}(k_\\rho)
            J_0(k_\\rho \\rho_m) e^{-k_\\rho (z_1 + z_2)}\\, dk_\\rho

    via :func:`scipy.integrate.quad`. The ``e^{-k_ρ z}`` factor
    provides convergence at large ``k_ρ`` for any ``z > 0``.

    Returns a single-frequency, single-pair value in 1/m. Used by
    callers that want a more accurate (per-pair, slow) estimate
    than :func:`green_function_static`.
    """
    rho_m = max(rho_um, 1e-9) * UM_TO_M
    z1_m = z1_um * UM_TO_M
    z2_m = z2_um * UM_TO_M

    def integrand(k_rho: float) -> float:
        if k_rho <= 0:
            return 0.0
        R = _stack_reflection_coefficient(tech, k_rho)
        try:
            from scipy.special import j0

            j_val = float(j0(k_rho * rho_m))
        except ImportError:
            # Fallback small-arg expansion if scipy.special is unavailable
            x = k_rho * rho_m
            j_val = 1.0 - 0.25 * x * x if abs(x) < 1.0 else math.cos(x) / math.sqrt(max(x, 1e-30))
        attenuation = math.exp(-k_rho * (z1_m + z2_m))
        return (R / k_rho) * j_val * attenuation

    val, _err = scipy.integrate.quad(
        integrand,
        a=1.0e-3,  # avoid k=0 singularity
        b=k_max,
        limit=100,
    )
    return float(val)
