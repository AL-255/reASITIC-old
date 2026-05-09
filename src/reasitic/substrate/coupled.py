"""Hammerstad–Jensen coupled-microstrip capacitance.

Closed-form per-unit-length capacitance for a pair of parallel
microstrip traces of equal width, sitting on top of a single
homogeneous dielectric of relative permittivity ``eps_r`` and
height ``h`` (a ground plane sits at the bottom of the dielectric).

This is the model used by the original ASITIC binary in
``coupled_microstrip_caps_hj`` (``decomp/output/asitic_kernel.c:398``,
address ``0x0804df6c``) and exposed via
``coupled_microstrip_to_cap_matrix`` (``0x0804ecac``). The decomp's
``Cgd`` expression has a transcription artefact — it uses
``ln(2) · coth(πs/4h)`` rather than the canonical
``ln(coth(πs/4h))``; the implementation here follows the original
Hammerstad–Jensen 1980 reference instead.

The five components returned by :func:`coupled_microstrip_caps_hj`
are:

* ``Cp``  — broadside parallel-plate capacitance from one strip to ground.
* ``Cf``  — outer-edge fringing capacitance.
* ``Cf_prime`` — modified inner-edge fringing capacitance, weakened
  by the presence of the adjacent strip.
* ``Cga`` — air-side gap capacitance between the two strips.
* ``Cgd`` — dielectric-side gap capacitance between the two strips.

All capacitances are returned in **F/cm** (matching the binary,
which uses ``ε₀ = 8.854e-14 F/cm``). All input lengths are in **cm**.

Reference:
    E. Hammerstad and Ø. Jensen,
    *Accurate Models for Microstrip Computer-Aided Design*,
    IEEE MTT-S Int. Microwave Symp. Digest, 1980, pp. 407–409.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

ETA_0 = 376.99111843077515  # vacuum wave impedance, Ω
EPS_0_FCM = 8.854e-14       # vacuum permittivity, F/cm (= 8.854 pF/m / 100)
C0_CM = 2.99792458e10       # speed of light, cm/s


@dataclass(frozen=True)
class HJCoupledCaps:
    """Five Hammerstad–Jensen capacitance components, all in F/cm."""

    Cp: float
    Cf: float
    Cf_prime: float
    Cga: float
    Cgd: float


def _eps_eff(W_over_h: float, eps_r: float) -> float:
    """Effective permittivity of a single microstrip (Hammerstad)."""
    a = (eps_r + 1.0) / 2.0
    b = (eps_r - 1.0) / (2.0 * math.sqrt(1.0 + 12.0 / W_over_h))
    return a + b


def _z0_microstrip(W_over_h: float, eps_eff: float) -> float:
    """Characteristic impedance of a single microstrip (Hammerstad)."""
    if W_over_h <= 1.0:
        return (60.0 / math.sqrt(eps_eff)) * math.log(
            8.0 / W_over_h + W_over_h / 4.0
        )
    return ETA_0 / (
        math.sqrt(eps_eff)
        * (W_over_h + 1.393 + 0.667 * math.log(W_over_h + 1.444))
    )


def _kk_prime_ratio(k: float) -> float:
    """Return ``K(k') / K(k)``, the complete-elliptic-integral ratio.

    Uses Hammerstad's piecewise closed-form (accurate to ~1e-5):

    * For ``k² ≤ 0.5``: ``(1/π) · ln(2 (1+√k′)/(1−√k′))``
    * For ``k² > 0.5``: ``π / ln(2 (1+√k)/(1−√k))``

    The ratio is monotonically *decreasing* in ``k`` over ``(0, 1)``:
    it diverges as ``k → 0`` (touching strips) and shrinks toward 0
    as ``k → 1`` (decoupled).
    """
    if not 0.0 <= k <= 1.0:
        raise ValueError(f"k must be in [0, 1], got {k}")
    if k * k <= 0.5:
        kp = math.sqrt(1.0 - k * k)
        return (1.0 / math.pi) * math.log(
            2.0 * (1.0 + math.sqrt(kp)) / (1.0 - math.sqrt(kp))
        )
    return math.pi / math.log(
        2.0 * (1.0 + math.sqrt(k)) / (1.0 - math.sqrt(k))
    )


def coupled_microstrip_caps_hj(
    W_cm: float,
    s_cm: float,
    h_cm: float,
    eps_r: float,
) -> HJCoupledCaps:
    """Five-component coupled-microstrip capacitance per unit length.

    Args:
        W_cm:   Strip width, cm.
        s_cm:   Edge-to-edge spacing between strips, cm.
        h_cm:   Substrate (dielectric) height to ground, cm.
        eps_r:  Relative dielectric permittivity.

    Returns:
        :class:`HJCoupledCaps` with five F/cm components.
    """
    if W_cm <= 0 or h_cm <= 0:
        raise ValueError("W and h must be positive")
    if s_cm <= 0:
        raise ValueError("s must be positive")
    if eps_r < 1.0:
        raise ValueError("eps_r must be ≥ 1")

    Wh = W_cm / h_cm
    sh = s_cm / h_cm

    eps_eff = _eps_eff(Wh, eps_r)
    Z0 = _z0_microstrip(Wh, eps_eff)

    # Single-strip parallel-plate vs total cap
    Cp = eps_r * EPS_0_FCM * Wh
    C_total = math.sqrt(eps_eff) / (Z0 * C0_CM)
    Cf = 0.5 * (C_total - Cp)

    # Modified inner-edge fringe (HJ formula 4 in the 1980 paper).
    # The exponential reduction comes from the adjacent strip's
    # presence; the constant 0.1 below is the HJ "A" parameter.
    A = math.exp(-0.1 * math.exp(2.33 - 2.53 * Wh))
    tanh_factor = math.tanh(8.0 * sh)
    Cf_prime = Cf / (1.0 + (1.0 / sh) * A * tanh_factor)

    # Air-gap capacitance (capacitance between strips through air)
    # via the elliptic-integral ratio:
    k = sh / (sh + 2.0 * Wh)
    Cga = EPS_0_FCM * 0.5 * _kk_prime_ratio(k)

    # Dielectric-gap (canonical HJ form: ln(coth(πs/(4h))))
    Cgd = (eps_r * EPS_0_FCM / math.pi) * math.log(
        1.0 / math.tanh(math.pi * sh / 4.0)
    ) + 0.65 * Cf * (
        0.02 * math.sqrt(eps_r) / sh + 1.0 - 1.0 / (eps_r * eps_r)
    )

    return HJCoupledCaps(Cp=Cp, Cf=Cf, Cf_prime=Cf_prime,
                         Cga=Cga, Cgd=Cgd)


def coupled_microstrip_to_cap_matrix(
    W_cm: float,
    s_cm: float,
    h_cm: float,
    eps_r: float,
    *,
    mode: int = 1,
) -> tuple[float, float]:
    """Convert HJ caps to per-line ``(C_self, C_mutual)`` in F/cm.

    Mirrors :c:func:`coupled_microstrip_to_cap_matrix` (decomp
    address ``0x0804ecac``). For the symmetric coupled-pair
    (``mode=1``):

    .. code-block:: text

        Ce = Cp + Cf + Cf'                 (even mode, in-phase drive)
        Co = Cp + Cf + Cga + Cgd           (odd  mode, anti-phase)
        C_self   = Ce
        C_mutual = (Co - Ce) / 2

    For ``mode != 1`` the binary uses an alternate sum that
    corresponds to a non-symmetric layout (e.g. asymmetric strip
    pair). Both forms preserve the canonical even/odd → matrix
    identity ``Cm = (Co − Ce) / 2``.

    Returns:
        ``(C_self, C_mutual)`` in F/cm.
    """
    c = coupled_microstrip_caps_hj(W_cm, s_cm, h_cm, eps_r)
    if mode == 1:
        Ce = c.Cp + c.Cf + c.Cf_prime
        Co = c.Cp + c.Cf + c.Cga + c.Cgd
    else:
        # Alternate decomposition the binary uses for non-symmetric
        # geometries (decomp lines 745–746).
        Ce = 2.0 * c.Cf_prime + c.Cp
        Co = c.Cp + 2.0 * c.Cga + 2.0 * c.Cgd
    C_self = Ce
    C_mutual = 0.5 * (Co - Ce)
    return C_self, C_mutual


def even_odd_impedances(
    W_cm: float,
    s_cm: float,
    h_cm: float,
    eps_r: float,
) -> tuple[float, float]:
    """Return ``(Z_even, Z_odd)`` in Ω for the coupled pair.

    Convenience wrapper combining :func:`coupled_microstrip_caps_hj`
    with the standard relations ``Z = sqrt(L/C) ≈ 1/(c · sqrt(eps_eff_mode) · C_mode)``.
    """
    c = coupled_microstrip_caps_hj(W_cm, s_cm, h_cm, eps_r)
    Ce = c.Cp + c.Cf + c.Cf_prime
    Co = c.Cp + c.Cf + c.Cga + c.Cgd
    Wh = W_cm / h_cm
    eps_eff_e = _eps_eff(Wh, eps_r)
    # Odd-mode effective permittivity is reduced because half the
    # field is in the air gap; HJ approximate it via Ce/Co cap ratio.
    eps_eff_o = eps_eff_e * (Ce / Co)
    Z_e = math.sqrt(eps_eff_e) / (C0_CM * Ce)
    Z_o = math.sqrt(eps_eff_o) / (C0_CM * Co)
    return Z_e, Z_o
