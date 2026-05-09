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
(1974).

The per-pair dispatch mirrors the binary's ``check_segments_intersect``
(decomp ``0x08061110``) and ``mutual_inductance_3d_segments``
(``0x08062ebc``):

* perpendicular pairs (``|û_a · û_b| < 1e-10``) → 0
* axis-aligned parallel pairs → closed-form Grover 4-corner via
  :func:`reasitic.inductance.grover.parallel_segment_mutual`
* general parallel-not-axis-aligned and skew pairs → Maxwell double
  integral via :func:`reasitic.inductance.skew.mutual_inductance_skew_segments`

The skew kernel internally short-circuits exactly-parallel pairs to
its own closed form, so the only pairs that hit the numerical
integrator are genuinely non-parallel ones (typical only for
polygon spirals and 3D / multi-metal structures).
"""

from __future__ import annotations

import math

from reasitic.geometry import Point, Segment, Shape
from reasitic.inductance.grover import (
    parallel_segment_mutual,
    rectangular_bar_self_inductance,
)
from reasitic.inductance.skew import mutual_inductance_skew_segments


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


_PERP_DOT_TOL = 1e-10


def _segment_pair_mutual(a: Segment, b: Segment) -> float:
    """Signed mutual-inductance contribution from one segment pair.

    Mirrors the C dispatch in ``check_segments_intersect``
    (``asitic_kernel.c:3882``) followed by the geometry classifier
    in ``mutual_inductance_3d_segments`` (``:4875``):

    1. If ``|û_a · û_b| < 1e-10`` (perpendicular), contribute 0.
       The C path early-returns before classification.
    2. Try the axis-aligned-parallel closed form first. Manhattan
       spirals — which are the bulk of ASITIC use — flow entirely
       through this fast path.
    3. Otherwise delegate to :func:`mutual_inductance_skew_segments`
       which handles parallel-non-axis-aligned (closed form) and
       general skew (Maxwell double integral).

    Co-linear segments (zero perpendicular separation) are suppressed
    to match the binary's intra-shape chain handling.
    """
    dx_a = a.b.x - a.a.x
    dy_a = a.b.y - a.a.y
    dz_a = a.b.z - a.a.z
    dx_b = b.b.x - b.a.x
    dy_b = b.b.y - b.a.y
    dz_b = b.b.z - b.a.z
    L_a_sq = dx_a * dx_a + dy_a * dy_a + dz_a * dz_a
    L_b_sq = dx_b * dx_b + dy_b * dy_b + dz_b * dz_b
    if L_a_sq < 1e-24 or L_b_sq < 1e-24:
        return 0.0
    L_a = math.sqrt(L_a_sq)
    L_b = math.sqrt(L_b_sq)
    cos_alpha = (dx_a * dx_b + dy_a * dy_b + dz_a * dz_b) / (L_a * L_b)
    if abs(cos_alpha) < _PERP_DOT_TOL:
        return 0.0

    try:
        ax_a, _ = _axis_of(a)
    except ValueError:
        ax_a = -1
    pair = _parallel_axis_pair(a, b, ax_a) if ax_a >= 0 else None
    if pair is not None:
        L1, L2, sep, offset, sign = pair
        if sep < 1e-12:
            # Co-linear continuation; suppressed.
            return 0.0
        return sign * parallel_segment_mutual(L1, L2, sep, offset)

    # General path: parallel-non-axis-aligned + skew.
    return mutual_inductance_skew_segments(a.a, a.b, b.a, b.b)


def compute_self_inductance(shape: Shape) -> float:
    """Total self-inductance (in nH) of a shape.

    Uses Greenhouse partial-inductance summation. Mutual terms are
    routed through :func:`_segment_pair_mutual`, which dispatches to
    the axis-aligned-parallel closed form for Manhattan spirals and
    to the general skew kernel for polygon / 3D geometry.
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

    Mirrors the binary's ``cmd_coupling_compute``
    (``asitic_repl.c:1478``) — parallel, perpendicular, and general
    skew geometries are all handled via :func:`_segment_pair_mutual`.
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
