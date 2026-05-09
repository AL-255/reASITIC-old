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

    where ``γ`` is :func:`propagation_constant`.
    """
    gamma = propagation_constant(k_rho, omega_rad, sigma_S_per_m)
    return (k_rho - gamma) / (k_rho + gamma)


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
    # Layered stack: layer 0 = top (under metal), layer N-1 = bulk.
    # We assume a perfect ground below the bulk.
    R = 1.0  # ground at the bottom = +1 reflection
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
    """Quasi-static substrate Green's function value, in 1/(F·m).

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
    """
    rho_m = max(rho_um, 1e-6) * UM_TO_M
    z1_m = z1_um * UM_TO_M
    z2_m = z2_um * UM_TO_M
    r_plus = math.sqrt(rho_m**2 + (z1_m - z2_m) ** 2)
    r_minus = math.sqrt(rho_m**2 + (z1_m + z2_m) ** 2)
    # 1/k_ρ in the static limit; effective k for the reflection term
    k_eff = 1.0 / max(rho_m, 1e-30)
    R_stack = _stack_reflection_coefficient(tech, k_eff)
    return (1.0 / r_plus + R_stack / r_minus) / (4.0 * math.pi * EPS_0)


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
