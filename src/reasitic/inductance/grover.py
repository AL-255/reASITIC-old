"""Closed-form partial-inductance formulas of F. W. Grover.

These are the same expressions that the binary evaluates in
``grover_segment_self_inductance``, ``mutual_inductance_4corner_grover``,
and ``coupled_wire_self_inductance_grover`` (decompiled output:
``decomp/output/asitic_kernel.c`` lines 5650, 4010, 19). The
binary computes everything in extended precision using x87 ``f2xm1``
/ ``fscale`` / ``fpatan`` intrinsics. We just call the libm
functions; ``float`` is IEEE-754 binary64 which is sufficient for
all but the most aggressive cancellation paths (Grover's are not
those).

Conventions:

* Lengths are passed in **microns**.
* The closed forms internally convert to **cm** (multiplying by
  ``1e-4``) because Grover's tables are tabulated in those units.
* Returns inductance in **nH**.

Reference:
    F. W. Grover, *Inductance Calculations: Working Formulas and
    Tables*, Dover, 1946. Sections on parallel filaments and
    rectangular bars (Tables 24, 25, formulas 25.4, 7.16).

The Greenhouse formulation used by ASITIC computes the total
inductance of a planar coil as the sum of self-inductances of each
straight segment plus all pairwise mutual inductances. This module
provides the per-segment primitives; the summation lives in
``inductance.partial``.
"""

from __future__ import annotations

import math

from reasitic.units import UM_TO_CM


def rectangular_bar_self_inductance(
    length_um: float, width_um: float, thickness_um: float
) -> float:
    """Self-inductance of a rectangular conductor bar.

    .. math::

        L = 2\\ell\\,\\Bigl[
            \\ln\\!\\bigl(\\tfrac{2\\ell}{W+T}\\bigr)
            + 0.50049
            + \\frac{W+T}{3\\ell}
          \\Bigr]

    where ``ℓ``, ``W``, ``T`` are in cm and the result is in nH.
    The constant ``0.50049`` is Grover's value for the GMD correction
    of a thin rectangular cross-section. This is the exact formula
    used by the original ASITIC binary in ``cmd_inductance_compute``
    (decomp ``asitic_repl.c:1417``).
    """
    if length_um <= 1e-6:
        return 0.0
    L = length_um * UM_TO_CM
    wt = (width_um + thickness_um) * UM_TO_CM
    if wt <= 0:
        return 0.0
    return 2.0 * L * (
        math.log(2.0 * L / wt) + 0.50049 + wt / (3.0 * L)
    )


def segment_self_inductance(length_um: float, radius_um: float) -> float:
    """Self-inductance of a single straight round wire (Grover §7.4).

    .. math::

        L = 2 \\ell\\, \\Bigl[ \\sinh^{-1}(\\ell/r)
                              + r/\\ell - \\sqrt{1 + (r/\\ell)^2}
                       \\Bigr]

    where ``ℓ`` is length in cm, ``r`` is the equivalent round-wire
    radius in cm, and the result is in nH.

    Mirrors the decompiled ``grover_segment_self_inductance`` at
    ``0x08064308``.

    Example:
        >>> from reasitic.inductance import segment_self_inductance
        >>> round(segment_self_inductance(100.0, 0.5), 4)
        0.0999
    """
    if length_um < 1e-6:
        return 0.0
    L = length_um * UM_TO_CM
    r = max(radius_um * UM_TO_CM, 1e-12)
    z = L / r
    inv_z = 1.0 / z
    asinh_z = math.log(z + math.sqrt(z * z + 1.0))
    return 2.0 * L * (asinh_z + inv_z - math.sqrt(1.0 + inv_z * inv_z))


def coupled_wire_self_inductance(
    width_um: float, thickness_um: float, separation_um: float
) -> float:
    """Self-inductance of a rectangular bar of width ``width_um``,
    thickness ``thickness_um``, with a parallel-bar separation of
    ``separation_um`` (the latter affects the GMD via the proximity
    correction).

    Mirrors the decompiled ``coupled_wire_self_inductance_grover`` at
    ``0x0804cb90`` (Grover Table 24).

    Parameters and result are in microns / nH.
    """
    if width_um <= 0 or thickness_um <= 0:
        return 0.0
    # Convert all lengths to cm
    w = width_um * UM_TO_CM
    h = thickness_um * UM_TO_CM
    s = max(separation_um * UM_TO_CM, 1e-12 * w)

    a = w / h
    b = s / h
    a2 = a * a
    a3 = a2 * a
    b2 = b * b

    # Auxiliary terms
    R1 = math.sqrt(a2 + 1.0)
    R2 = math.sqrt(b2 + 1.0)
    R3 = math.sqrt(a2 + b2)
    R4 = math.sqrt(b2 + 1.0 + a2)

    # The Grover §24 formula (recovered from the decomp): a single
    # composite expression in ln/atan terms. We build it piecewise
    # to track the original structure.
    LN2 = math.log(2.0)

    L_a = LN2 * ((R4 + 1.0) / R3)
    L_b = LN2 * ((b + R4) / R1)
    L_c = LN2 * ((a + R4) / R2)
    L_60 = a * 60.0

    A1 = math.atan2(b, a * R4)
    A2 = math.atan2(a, b * R4)
    A3 = math.atan2(a * b, R4)

    # The original kernel groups this in nested doubles; group it
    # into a clearer sum here.  All coefficients are taken verbatim
    # from the decompiled output.
    term1 = a3 * (LN2 * ((b + R3) / a) - L_b) / (b * 24.0)
    term2 = a3 * (LN2 * ((R1 + 1.0) / a) - L_a) / (b2 * 24.0)
    term3 = a * (R3 - R4) / 20.0
    term4 = (1.0 - R2) / (b2 * 60.0 * a)
    term5 = a * (R1 - R4) / (b2 * 20.0)
    term6 = (LN2 * (a + R1) - L_c) / (b2 * 24.0)
    term7 = L_c * 0.25
    term8 = (a * L_b) / (4.0 * b)
    term9 = a * L_a * 0.25
    term10 = (R2 - R4) / (a * 20.0)
    term11 = (b2 * (b - R2)) / L_60
    term12 = (b2 * (LN2 * ((a + R3) / b) - L_c)) / 24.0
    term13 = (LN2 * (b + R2) - L_b) / ((a * b) * 24.0)
    term14 = (LN2 * ((R2 + 1.0) / b) - L_a) * b2 / (a * 24.0)
    term15 = (R4 - R3) * b2 / (a * 60.0)
    term16 = -(A1 * a2) / (b * 6.0)
    term17 = -(b * A2) / 6.0
    term18 = -A3 / (b * 6.0)
    term19 = (R4 - R1) / (b2 * L_60)
    term20 = ((a - R3) + (R4 - R1)) * a3 / (b2 * 60.0)

    inner = (
        term1 + term2 + term3 + term4 + term5 + term6
        + term7 + term8 + term9 + term10 + term11 + term12 + term13
        + term14 + term15 + term16 + term17 + term18 + term19 + term20
    )
    # Final scaling: 8 * w in cm gives result in 0.1 nH·cm? No —
    # Grover's tables in this layout return microhenries; to convert
    # to nH multiply by 1000. The decompiled code returns
    # ``result * 8.0 * width`` directly — width is in cm via the
    # 1e-4 scaling so the result is in nH already.
    return inner * 8.0 * w * 1000.0


def perpendicular_segment_mutual(
    length1_um: float,
    length2_um: float,
    *,
    common_distance_um: float = 0.0,
) -> float:
    """Mutual inductance between two perpendicular straight filaments.

    Two filaments meeting at right angles (e.g. adjacent legs of a
    square spiral): segment 1 along the x-axis on ``[0, L1]``,
    segment 2 along the y-axis on ``[0, L2]``, sharing the origin
    if ``common_distance_um`` is zero, otherwise displaced along
    the common axis by that distance.

    For *filamentary* perpendicular wires Maxwell's formula reduces
    to **0** because ``ds₁ · ds₂ = 0``. The binary's
    ``mutual_inductance_orthogonal_segments``
    (``asitic_kernel.c:0x08061b84``) is a closed-form for finite-
    width *bars* — it captures the fringe / GMD contribution that
    appears at corners. For axis-aligned 2-D spirals this term is
    typically <1 % of the total inductance; we return zero here as
    the standard Greenhouse approximation. Callers that need the
    corner correction can substitute their own kernel.
    """
    return 0.0


def mohan_modified_wheeler(
    *,
    n_turns: float,
    d_outer_um: float,
    d_inner_um: float,
    shape: str = "square",
) -> float:
    """Mohan 1999 modified-Wheeler closed-form L estimate.

    Example:
        >>> from reasitic.inductance import mohan_modified_wheeler
        >>> round(mohan_modified_wheeler(
        ...     n_turns=5, d_outer_um=200, d_inner_um=100,
        ... ), 2)
        5.75
        >>> mohan_modified_wheeler(
        ...     n_turns=5, d_outer_um=50, d_inner_um=100,
        ... )
        0.0

    .. math::

        L_\\text{mw} = K_1 \\mu_0 n^2 d_\\text{avg} / (1 + K_2 \\rho)

    where ``ρ = (d_out − d_in) / (d_out + d_in)``,
    ``d_avg = (d_out + d_in) / 2``, and ``(K_1, K_2)`` come from
    Mohan 1999 Table 1:

    * ``square``: K_1 = 2.34, K_2 = 2.75
    * ``hexagonal``: K_1 = 2.33, K_2 = 3.82
    * ``octagonal``: K_1 = 2.25, K_2 = 3.55
    * ``circular``: K_1 = 2.40, K_2 = 1.75

    Returns L in **nH**. Fast first-order estimate, useful for
    sanity-checking the Greenhouse summation.
    """
    coeffs = {
        "square": (2.34, 2.75),
        "hexagonal": (2.33, 3.82),
        "octagonal": (2.25, 3.55),
        "circular": (2.40, 1.75),
    }
    if shape not in coeffs:
        raise ValueError(
            f"unknown shape {shape!r}; choose from {list(coeffs)}"
        )
    K1, K2 = coeffs[shape]
    if d_outer_um <= 0 or d_outer_um <= d_inner_um:
        return 0.0
    rho = (d_outer_um - d_inner_um) / (d_outer_um + d_inner_um)
    d_avg_m = 0.5 * (d_outer_um + d_inner_um) * 1.0e-6
    mu_0 = 4.0e-7 * math.pi
    L_h = K1 * mu_0 * n_turns * n_turns * d_avg_m / (1.0 + K2 * rho)
    return L_h * 1.0e9  # H → nH


def hoer_love_perpendicular_mutual(
    *,
    L1_um: float,
    L2_um: float,
    a_um: float,
    b_um: float,
    c_um: float,
) -> float:
    """Hoer-Love mutual-inductance integral for perpendicular bars.

    Two filaments meeting at a corner: filament 1 from ``(0,0,0)``
    to ``(L1,0,0)``, filament 2 from ``(a, b, c)`` to ``(a, b+L2, c)``.
    For perpendicular *filaments* the dot product is zero so M=0;
    for *finite-width bars* the proximity integral

    .. math::

        M_\\perp = \\frac{\\mu_0}{4\\pi}\\int\\int
                    \\frac{(\\hat{x}\\cdot\\hat{y}) \\,dx\\,dy}
                         {\\sqrt{(x-a)^2 + (y-b)^2 + c^2}}

    is identically zero (the dot-product vanishes element-wise).
    Hoer & Love's 1965 result captures the same vanishing for
    arbitrary 3-D orientations. We provide this function so the
    dispatch surface in :func:`reasitic.inductance.partial._segment_pair_mutual`
    can call it without conditional logic; it always returns 0.

    The non-zero "corner" contribution that the binary's
    ``mutual_inductance_orthogonal_segments`` reports is actually a
    *self-inductance* artifact — the L_self of the bend itself,
    folded into a per-pair lookup. Callers wanting that should add
    a corner-correction term to the diagonal of the partial-L
    matrix, not the off-diagonal.
    """
    return 0.0


def parallel_segment_mutual(
    length1_um: float,
    length2_um: float,
    sep_um: float,
    offset_um: float = 0.0,
) -> float:
    """Mutual inductance between two parallel filamentary segments.

    Both segments lie along the same axis. With segment 1 occupying
    ``[0, L1]`` along the axis and segment 2 occupying
    ``[offset, offset + L2]``, separated by perpendicular distance
    ``d``, the closed form is

    .. math::

        M = \\tfrac{\\mu_0}{4\\pi}\\,
            \\bigl[\\phi(L_1-o) - \\phi(-o) - \\phi(L_1-o-L_2) + \\phi(-o-L_2)\\bigr]

    where ``φ(t) = t·asinh(t/d) − √(t² + d²)`` is the antiderivative
    of the double-integral kernel. ``φ`` is even, so absolute
    values are used.

    The prefactor ``μ₀/(4π)`` evaluates to **1 nH/cm**, hence with
    all lengths in cm the result is in nH directly.

    For two equal-length parallel filaments with no axial offset
    this reduces to the canonical Greenhouse Eq. 8::

        M = 2L·[asinh(L/d) − √(1 + (d/L)²) + d/L]    (nH)
    """
    if length1_um <= 0 or length2_um <= 0:
        return 0.0
    L1 = length1_um * UM_TO_CM
    L2 = length2_um * UM_TO_CM
    d = max(abs(sep_um) * UM_TO_CM, 1e-12)
    o = offset_um * UM_TO_CM

    def phi(t: float) -> float:
        t = abs(t)
        return t * math.asinh(t / d) - math.sqrt(t * t + d * d)

    # F1 = [0, L1], F2 = [o, o + L2]
    return phi(L1 - o) - phi(-o) - phi(L1 - o - L2) + phi(-o - L2)
