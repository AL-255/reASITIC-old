"""Greenhouse partial-inductance summation.

Total inductance of a planar coil is the sum of the per-segment
self-inductances plus all signed pairwise mutual inductances:

.. math::

    L_\\text{total} = \\sum_i L_i + \\sum_{i \\neq j} \\sigma_{ij} M_{ij}

The sign ``σ_ij`` is +1 when the two segments carry current in the
same direction along their common axis, -1 when they oppose, and 0
when they are perpendicular (parallel-segment Grover formula yields
zero in that case anyway). Reference: H. M. Greenhouse, "Design of
Planar Rectangular Microelectronic Inductors," IEEE Trans. PHP-10
(1974). The ASITIC binary uses the same formulation as the leaf
case of ``compute_mutual_inductance`` for spirals whose segments
are all axis-aligned.

This module currently handles axis-aligned (square / Manhattan)
spirals. Polygon spirals with non-orthogonal segments require the
full 3D Grover formula (planned in
``inductance.grover.general_segment_mutual``).
"""

from __future__ import annotations

import math

from reasitic.geometry import Point, Segment, Shape
from reasitic.inductance.grover import (
    parallel_segment_mutual,
    rectangular_bar_self_inductance,
)


def _axis_of(seg: Segment) -> tuple[int, float]:
    """Return ``(axis, sign)`` for an axis-aligned segment.

    ``axis`` is 0/1/2 for x/y/z; ``sign`` is +1 or -1 depending on
    whether ``b`` is greater or less than ``a`` along that axis.
    Raises ``ValueError`` for non-axis-aligned segments.
    """
    dx = seg.b.x - seg.a.x
    dy = seg.b.y - seg.a.y
    dz = seg.b.z - seg.a.z
    nonzero = sum(abs(v) > 1e-9 for v in (dx, dy, dz))
    if nonzero == 0:
        raise ValueError("zero-length segment")
    if nonzero != 1:
        raise ValueError("segment is not axis-aligned")
    if abs(dx) > 1e-9:
        return 0, math.copysign(1.0, dx)
    if abs(dy) > 1e-9:
        return 1, math.copysign(1.0, dy)
    return 2, math.copysign(1.0, dz)




def _parallel_axis_pair(
    a: Segment, b: Segment, axis: int
) -> tuple[float, float, float, float, float] | None:
    """Project two segments onto a shared axis.

    Returns ``(L1, L2, sep, offset, sign)`` ready to feed
    :func:`parallel_segment_mutual`, or ``None`` if the segments are
    not parallel on the same axis. ``sign`` is +1 when both segments
    run in the same direction along ``axis``, -1 when opposite.
    """
    try:
        ax_a, sgn_a = _axis_of(a)
        ax_b, sgn_b = _axis_of(b)
    except ValueError:
        return None
    if ax_a != axis or ax_b != axis:
        return None

    pa0 = _coord(a.a, axis)
    pa1 = _coord(a.b, axis)
    pb0 = _coord(b.a, axis)
    pb1 = _coord(b.b, axis)

    # Re-orient so each segment runs in +axis direction
    if sgn_a < 0:
        pa0, pa1 = pa1, pa0
    if sgn_b < 0:
        pb0, pb1 = pb1, pb0

    L1 = pa1 - pa0
    L2 = pb1 - pb0

    # Perpendicular separation: sqrt of squared distances on the
    # other two axes (both endpoints of A are at the same off-axis
    # coordinate by axis-aligned construction)
    other_axes = [i for i in range(3) if i != axis]
    sep_sq = 0.0
    for i in other_axes:
        ca = _coord(a.a, i)
        cb = _coord(b.a, i)
        sep_sq += (ca - cb) ** 2
    sep = math.sqrt(sep_sq)

    # Offset from start of A to start of B, measured along axis
    offset = pb0 - pa0

    sign = sgn_a * sgn_b
    return (L1, L2, sep, offset, sign)


def _coord(p: Point, axis: int) -> float:
    return p.x if axis == 0 else (p.y if axis == 1 else p.z)


def _segment_pair_mutual(a: Segment, b: Segment) -> float:
    """Signed mutual-inductance contribution from one parallel pair.

    Returns the value already multiplied by ``σ_ij`` (the orientation
    sign). For non-parallel or coincident-axis pairs, returns 0.
    """
    try:
        ax_a, _ = _axis_of(a)
    except ValueError:
        return 0.0
    pair = _parallel_axis_pair(a, b, ax_a)
    if pair is None:
        return 0.0
    L1, L2, sep, offset, sign = pair
    if sep < 1e-12:
        # Co-linear continuation; suppressed (matches the binary's
        # behaviour for shape-internal segment chains).
        return 0.0
    M = parallel_segment_mutual(L1, L2, sep, offset)
    return sign * M


def compute_self_inductance(shape: Shape) -> float:
    """Total self-inductance (in nH) of a planar Manhattan shape.

    Uses Greenhouse partial-inductance summation. Falls back to
    self-only when segments are non-orthogonal or the geometry is
    multi-layer (mutual inductance for those cases is implemented in
    a follow-up kernel).
    """
    segs = shape.segments()
    if not segs:
        return 0.0

    L = 0.0
    # Self terms — use the same rectangular-bar formula as the binary.
    for s in segs:
        if s.length <= 0:
            continue
        L += rectangular_bar_self_inductance(s.length, s.width, s.thickness)

    # Mutual terms — axis-aligned only for now.
    n = len(segs)
    for i in range(n):
        for j in range(i + 1, n):
            L += 2.0 * _segment_pair_mutual(segs[i], segs[j])

    return L


def compute_mutual_inductance(shape_a: Shape, shape_b: Shape) -> float:
    """Mutual inductance between two distinct shapes, in nH.

    Sums the signed Greenhouse mutual contribution over every
    cross-pair of segments. The double-counting factor of 2 used in
    the self case does **not** apply here because each (i, j) pair
    appears exactly once.

    Mirrors the leaf-case dispatch of the binary's
    ``cmd_coupling_compute`` (``asitic_repl.c:1478``) for parallel /
    Manhattan geometries.
    """
    M = 0.0
    for sa in shape_a.segments():
        for sb in shape_b.segments():
            M += _segment_pair_mutual(sa, sb)
    return M


def coupling_coefficient(shape_a: Shape, shape_b: Shape) -> float:
    """Magnetic coupling coefficient ``k = M / sqrt(L₁·L₂)``.

    Returns 0 if either self-inductance is non-positive. The result
    is dimensionless and lies in (-1, +1) for physically realisable
    geometries.
    """
    M = compute_mutual_inductance(shape_a, shape_b)
    L1 = compute_self_inductance(shape_a)
    L2 = compute_self_inductance(shape_b)
    if L1 <= 0 or L2 <= 0:
        return 0.0
    return M / math.sqrt(L1 * L2)
