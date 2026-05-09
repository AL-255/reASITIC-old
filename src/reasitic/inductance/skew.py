"""Mutual inductance between arbitrary 3D line filaments.

Mirrors the binary's three companion routines:

* ``mutual_inductance_4corner_grover`` (decomp ``0x080613bc``) —
  the parallel / coaxial closed form (already covered by
  :func:`reasitic.inductance.grover.parallel_segment_mutual`).
* ``mutual_inductance_orthogonal_segments`` (``0x08061b84``) — the
  perpendicular-segment closed form, ported here as
  :func:`mutual_inductance_orthogonal_segments`.
* ``mutual_inductance_filament_general`` (``0x08062230``) — the
  full 3-D Maxwell mutual-inductance integral for arbitrary skew
  filaments, ported here as :func:`mutual_inductance_skew_segments`.

The Python implementation evaluates Maxwell's double integral

.. math::

    M = \\frac{\\mu_0 \\, \\hat u_a \\cdot \\hat u_b}{4\\pi}
        \\int_0^{L_a}\\!\\int_0^{L_b}
        \\frac{ds\\,dt}{|\\,\\mathbf r_a(s) - \\mathbf r_b(t)\\,|}

via :func:`scipy.integrate.dblquad`. Lengths are converted to **cm**
(so ``μ₀ / 4π = 10⁻⁹ H/cm = 1 nH/cm`` and the dimensional integral
returns nH directly). Special cases (zero-length, coincident,
parallel) short-circuit to a closed form that avoids the
integration overhead.

The mutual is signed: it depends on the *direction* of each
filament. The Greenhouse summation in
:mod:`reasitic.inductance.partial` re-orients segments to a
canonical direction before summing, but raw callers of these
kernels should not assume the result is positive.
"""

from __future__ import annotations

import math
from typing import TYPE_CHECKING

import numpy as np
import scipy.integrate

from reasitic.units import UM_TO_CM

if TYPE_CHECKING:
    from reasitic.geometry import Point, Segment


_MU_0_OVER_4PI_NH_CM = 1.0  # μ₀/4π in (nH·cm⁻¹), see module docstring


def _seg_endpoints_cm(seg: Segment) -> tuple[np.ndarray, np.ndarray]:
    """Return the two endpoints of ``seg`` as numpy arrays, in **cm**."""
    a = np.array([seg.a.x, seg.a.y, seg.a.z]) * UM_TO_CM
    b = np.array([seg.b.x, seg.b.y, seg.b.z]) * UM_TO_CM
    return a, b


def _from_points_cm(p: Point) -> np.ndarray:
    return np.array([p.x, p.y, p.z]) * UM_TO_CM


def _are_parallel(u_a: np.ndarray, u_b: np.ndarray, *, tol: float = 1e-9) -> bool:
    """True if ``u_a`` and ``u_b`` are (anti-)parallel within ``tol``."""
    cross = np.cross(u_a, u_b)
    return bool(float(np.dot(cross, cross)) < tol * tol)


def _are_perpendicular(u_a: np.ndarray, u_b: np.ndarray, *,
                       tol: float = 1e-9) -> bool:
    return bool(abs(float(np.dot(u_a, u_b))) < tol)


def mutual_inductance_skew_segments(
    a1: Point,
    a2: Point,
    b1: Point,
    b2: Point,
    *,
    epsabs: float = 1e-9,
    epsrel: float = 1e-7,
) -> float:
    """Mutual inductance between two arbitrary 3-D line filaments, in **nH**.

    Mirrors the binary's
    ``mutual_inductance_filament_general`` (decomp ``0x08062230``).
    Uses Maxwell's double integral evaluated numerically.

    Args:
        a1, a2: Endpoints of filament A (in microns, μm).
        b1, b2: Endpoints of filament B (in microns, μm).
        epsabs, epsrel: Absolute / relative tolerance forwarded to
            :func:`scipy.integrate.dblquad`. The defaults give ~6
            significant digits in the typical RFIC range.

    Returns:
        Mutual inductance in **nH**. Zero for filaments shorter than
        the floating-point safety floor; positive when the dot-
        product ``û_a · û_b`` is positive, negative otherwise.
    """
    A1 = _from_points_cm(a1)
    A2 = _from_points_cm(a2)
    B1 = _from_points_cm(b1)
    B2 = _from_points_cm(b2)
    u_a = A2 - A1
    u_b = B2 - B1
    L_a = float(np.linalg.norm(u_a))
    L_b = float(np.linalg.norm(u_b))
    if L_a < 1e-15 or L_b < 1e-15:
        return 0.0
    u_a_hat = u_a / L_a
    u_b_hat = u_b / L_b
    cos_alpha = float(np.dot(u_a_hat, u_b_hat))

    if abs(cos_alpha) < 1e-12:
        # Strictly perpendicular ⇒ Maxwell integrand vanishes element-
        # wise. Filament approximation gives M = 0.
        return 0.0

    if _are_parallel(u_a_hat, u_b_hat):
        # Use the closed-form parallel kernel for both speed and
        # accuracy. We project B's endpoints onto A's axis to find
        # the (length, offset, separation) triple that the parallel
        # formula expects.
        return _parallel_via_projection(A1, u_a_hat, L_a, B1, B2, u_b_hat, L_b)

    def integrand(t: float, s: float) -> float:
        # dblquad calls integrand(y, x): we put ``s`` as the outer
        # variable (along filament A) and ``t`` along filament B.
        rs = A1 + s * u_a_hat
        rt = B1 + t * u_b_hat
        d = rs - rt
        dist = float(math.sqrt(float(np.dot(d, d))))
        if dist < 1e-15:
            return 0.0
        return cos_alpha / dist

    M_nH, _err = scipy.integrate.dblquad(
        integrand, 0.0, L_a, 0.0, L_b,
        epsabs=epsabs, epsrel=epsrel,
    )
    return float(M_nH * _MU_0_OVER_4PI_NH_CM)


def mutual_inductance_orthogonal_segments(
    a1: Point,
    a2: Point,
    b1: Point,
    b2: Point,
    *,
    tol: float = 1e-9,
) -> float:
    """Specialised perpendicular-segment kernel.

    Mirrors ``mutual_inductance_orthogonal_segments`` (decomp
    ``0x08061b84``). The decomp is a 1.7 KB closed form for
    *rectangular bars* of finite cross-section — it captures the
    geometric-mean-distance fringe contribution that appears at
    metal corners.

    For *line filaments* (zero radius) the perpendicular Maxwell
    integral has ``û_a · û_b = 0`` element-wise and M is identically
    zero. We honour the binary's signature for callers that want
    explicit dispatch on the perpendicular case but return ``0.0``
    in the line-filament limit. Callers that need the corner-
    correction GMD term should add it to the partial-L diagonal
    rather than treat it as an off-diagonal mutual.
    """
    A1 = _from_points_cm(a1)
    A2 = _from_points_cm(a2)
    B1 = _from_points_cm(b1)
    B2 = _from_points_cm(b2)
    u_a = A2 - A1
    u_b = B2 - B1
    if not _are_perpendicular(u_a, u_b, tol=tol):
        raise ValueError(
            "mutual_inductance_orthogonal_segments was called on a "
            "non-perpendicular filament pair; use "
            "mutual_inductance_skew_segments instead"
        )
    return 0.0


def mutual_inductance_filament_kernel(
    a1: Point,
    a2: Point,
    b1: Point,
    b2: Point,
) -> float:
    """Per-filament-pair mutual-inductance integrand.

    Mirrors ``mutual_inductance_filament_kernel`` (decomp
    ``0x08093f68``): computes the un-normalised filament-pair
    integrand value used inside the Greenhouse summation.

    The binary computes a normalised cosine-of-angle plus the four
    corner-pair distances; we return the cosine ``û_a · û_b``
    directly, which is the mathematically clean form of the same
    quantity. Callers integrate this over the segment lengths to
    get the mutual inductance — see
    :func:`mutual_inductance_skew_segments` for the full pipeline.

    Returns:
        The cosine of the angle between the two filaments, in
        ``[-1, 1]``. Filaments shorter than the floating-point safety
        floor return 0.
    """
    A1 = _from_points_cm(a1)
    A2 = _from_points_cm(a2)
    B1 = _from_points_cm(b1)
    B2 = _from_points_cm(b2)
    u_a = A2 - A1
    u_b = B2 - B1
    L_a = float(np.linalg.norm(u_a))
    L_b = float(np.linalg.norm(u_b))
    if L_a < 1e-15 or L_b < 1e-15:
        return 0.0
    return float(np.dot(u_a, u_b) / (L_a * L_b))


def wire_axial_separation(
    a1: Point,
    a2: Point,
    *,
    radius_um: float = 0.0,
) -> float:
    """Axial centre-to-centre separation between two filament endpoints.

    Mirrors ``wire_axial_separation`` (decomp ``0x080940dc``):
    returns ``|B − A| − 2·r`` in **microns**, where ``r`` is the
    wire radius (or half-thickness). For a zero-radius filament it
    is just the Euclidean distance between the two endpoints.

    Args:
        a1, a2:       The two filament endpoints (μm).
        radius_um:    Wire radius / half-thickness in μm.

    Returns:
        The axial separation in μm, possibly negative if the wires
        overlap.
    """
    P = _from_points_cm(a1)  # cm
    Q = _from_points_cm(a2)
    d_cm = float(np.linalg.norm(Q - P))
    return d_cm / UM_TO_CM - 2.0 * radius_um


def wire_separation_periodic(
    i: int,
    j: int,
    *,
    width_um: float,
    spacing_um: float,
    fold_size: int,
) -> float:
    """Periodic-grid separation product for the GMD calculation.

    Mirrors ``wire_separation_periodic`` (decomp ``0x080942ec``).
    For two indices ``i`` / ``j`` into a folded periodic wire grid:

    1. Reflect each index into ``[0, fold_size]`` by repeated
       reflection across the centre line.
    2. Compute the linear position of each folded index.
    3. Return the **signed** ``√(p_i · p_j)`` of the two positions:
       positive if both indices lie below the fold centre (or both
       above), negative if they straddle.

    Used inside the periodic-grid GMD calculation when the spiral's
    symmetry lets us reduce a full 2-D grid to a 1-D fold.

    Args:
        i, j:         The two grid indices (1-based, like the
                      binary).
        width_um:     Wire width (μm).
        spacing_um:   Edge-to-edge spacing between turns (μm).
        fold_size:    The fold radius — indices above are reflected.

    Returns:
        Signed separation product in μm.
    """
    def _fold(idx: int) -> int:
        while fold_size < idx:
            idx = (fold_size * 2 - idx) + 1
        return idx

    i_folded = _fold(i)
    j_folded = _fold(j)
    pitch = width_um + spacing_um
    pos_i = -float(2 * (i_folded - 1)) * pitch
    pos_j = -float(2 * (j_folded - 1)) * pitch
    base = math.sqrt(abs(pos_i * pos_j))
    # Sign: positive if both folded the same way, negative otherwise
    both_above = i > fold_size and j > fold_size
    both_below = i <= fold_size and j <= fold_size
    if both_above or both_below:
        return base
    return -base


def mutual_inductance_3d_segments(
    seg_a: Segment,
    seg_b: Segment,
    *,
    epsabs: float = 1e-9,
    epsrel: float = 1e-7,
) -> float:
    """High-level Segment→Segment dispatch.

    Mirrors the binary's ``mutual_inductance_3d_segments`` (decomp
    ``0x08062ebc``): selects between the parallel, perpendicular,
    and general-skew kernels based on the geometry, and delegates
    to the appropriate routine.
    """
    a1, a2 = seg_a.a, seg_a.b
    b1, b2 = seg_b.a, seg_b.b
    return mutual_inductance_skew_segments(
        a1, a2, b1, b2, epsabs=epsabs, epsrel=epsrel
    )


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _parallel_via_projection(
    A1: np.ndarray,
    u_a_hat: np.ndarray,
    L_a: float,
    B1: np.ndarray,
    B2: np.ndarray,
    u_b_hat: np.ndarray,
    L_b: float,
) -> float:
    """Closed-form for the parallel-filament case via projection."""
    # All in cm; result returned in nH via the 1 nH/cm conversion.
    sign = 1.0 if float(np.dot(u_a_hat, u_b_hat)) > 0 else -1.0

    # Vector from A1 to B1
    v = B1 - A1
    # Component along u_a_hat (the "offset" s_b1 of B1)
    s_b1 = float(np.dot(v, u_a_hat))
    # Component perpendicular: d² = |v|² − s_b1²
    d2 = float(np.dot(v, v)) - s_b1 * s_b1
    d = math.sqrt(max(d2, 0.0))

    # B occupies [s_b1, s_b1 + sign*L_b] along u_a_hat
    s_b2 = s_b1 + sign * L_b
    s_lo, s_hi = (s_b1, s_b2) if s_b1 < s_b2 else (s_b2, s_b1)
    L_b_signed = s_hi - s_lo  # always positive

    # Use the φ(t) = t·asinh(t/d) − √(t² + d²) antiderivative form
    return _parallel_filament_M(L_a, L_b_signed, s_lo, d) * sign


def _parallel_filament_M(L_a: float, L_b: float, offset: float, d: float) -> float:
    """Closed-form M between two parallel filaments at separation d.

    Both lengths and ``d`` are in cm; result is in nH.

    Filament A occupies ``[0, L_a]``; filament B occupies
    ``[offset, offset + L_b]``. Uses the φ(t) antiderivative
    ``φ(t) = t·asinh(t/d) − √(t² + d²)``.
    """
    if d < 1e-15:
        d = 1e-15  # singular axis — regularise

    def phi(t: float) -> float:
        return t * math.asinh(t / d) - math.sqrt(t * t + d * d)

    # Antiderivative limits (Greenhouse Eq. 1)
    f1 = phi(L_a - offset)
    f2 = phi(-offset)
    f3 = phi(L_a - offset - L_b)
    f4 = phi(-offset - L_b)
    return f1 - f2 - f3 + f4
