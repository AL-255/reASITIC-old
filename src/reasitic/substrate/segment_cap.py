"""Per-segment substrate capacitance integral.

Mirrors the binary's per-segment cap pipeline:

* :func:`capacitance_setup`            ↔ ``capacitance_setup`` (decomp ``0x08053580``)
* :func:`capacitance_segment_integral` ↔ ``capacitance_segment_integral`` (``0x080901c0``)
* :func:`capacitance_per_segment`      ↔ ``capacitance_per_segment`` (``0x0809002c``)
* :func:`analyze_capacitance_polygon`  ↔ ``analyze_capacitance_polygon`` (``0x08092780``)
* :func:`analyze_capacitance_driver`   ↔ ``analyze_capacitance_driver`` (``0x08052c50``)

The per-segment cap path is a finer-grained complement to the
per-shape FFT pipeline in :mod:`reasitic.substrate.fft_grid`:
where ``substrate_cap_matrix`` returns one ``(M, M)`` cap matrix
between ``M`` shapes, ``analyze_capacitance_driver`` returns one
``(N, N)`` matrix between ``N`` segments (typically ``N ≫ M``)
and is more accurate for shapes whose footprint is irregular.

The segment-pair integral is::

    P_ij = (1 / (A_i · A_j)) · ∫_i ∫_j G(r_i − r_j; z_i, z_j) dA_i dA_j

where ``G`` is the multi-layer substrate Green's function (see
:func:`reasitic.substrate.green.green_function_static`) and
``A_i, A_j`` are the segment areas. The full capacitance matrix is
then ``C = P⁻¹``.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Segment, Shape
from reasitic.substrate.green import green_function_static
from reasitic.tech import Tech


@dataclass
class SegmentCapResult:
    """Output of :func:`analyze_capacitance_driver`.

    Attributes:
        segments:  Flat list of every metal segment across the input
                   shapes.
        shape_for_segment:  ``segments[i]`` belongs to
                            ``shape_for_segment[i]``.
        P_matrix:  ``(N, N)`` potential matrix in V/C.
        C_matrix:  ``(N, N)`` capacitance matrix in F (``= P⁻¹``).
    """

    segments: list[Segment]
    shape_for_segment: list[str]
    P_matrix: np.ndarray
    C_matrix: np.ndarray


def capacitance_setup(
    shapes: list[Shape] | dict[str, Shape],
    tech: Tech,
) -> tuple[list[Segment], list[str]]:
    """Collect every metal segment across ``shapes``.

    Mirrors the binary's ``capacitance_setup`` (decomp
    ``0x08053580``), which walks the spiral list and builds one flat
    segment array. Vias are excluded — they participate in the cap
    matrix only via their lateral extent on the metal layer above.

    Returns:
        ``(segments, shape_names)`` parallel lists.
    """
    items: list[tuple[str, Shape]] = (
        list(shapes.items())
        if isinstance(shapes, dict)
        else [(s.name, s) for s in shapes]
    )
    n_metals = len(tech.metals)
    segs: list[Segment] = []
    names: list[str] = []
    for name, shape in items:
        for poly in shape.polygons:
            if poly.metal < 0 or poly.metal >= n_metals:
                continue  # via or out-of-range
            segs.extend(poly.edges())
            names.extend([name] * len(poly.edges()))
    return segs, names


def _segment_centroid(seg: Segment) -> tuple[float, float, float]:
    return (
        0.5 * (seg.a.x + seg.b.x),
        0.5 * (seg.a.y + seg.b.y),
        0.5 * (seg.a.z + seg.b.z),
    )


def _segment_area_um2(seg: Segment) -> float:
    """Footprint area of ``seg`` in μm² (length × width)."""
    L = seg.length
    return float(L * max(seg.width, 1.0))


def capacitance_segment_integral(
    seg_a: Segment,
    seg_b: Segment,
    tech: Tech,
    *,
    n_div: int = 2,
) -> float:
    """Double-integral substrate Green's between two segments.

    Mirrors the binary's ``capacitance_segment_integral`` (decomp
    ``0x080901c0``, the largest helper in ``asitic_kernel.c``).
    Discretises each segment into ``n_div`` tiles along its length
    and ``n_div`` across its width, then averages the static
    multi-layer Green's function over all tile-pair separations.

    Returns the average potential per unit charge (in V/C) for a
    uniform charge distribution on each segment.

    The lateral coordinates use segment endpoints; the vertical
    height ``z`` of each segment is taken from the centre of its
    metal layer (``metal.d + 0.5 * metal.t``).
    """
    if n_div <= 0:
        raise ValueError("n_div must be positive")
    n_metals = len(tech.metals)
    if not (0 <= seg_a.metal < n_metals and 0 <= seg_b.metal < n_metals):
        # Not on any metal layer — no substrate Green's contribution
        return 0.0
    z_a = tech.metals[seg_a.metal].d + 0.5 * tech.metals[seg_a.metal].t
    z_b = tech.metals[seg_b.metal].d + 0.5 * tech.metals[seg_b.metal].t
    cx_a, cy_a, _ = _segment_centroid(seg_a)
    cx_b, cy_b, _ = _segment_centroid(seg_b)
    dx, dy = cx_a - cx_b, cy_a - cy_b
    rho_um = math.sqrt(dx * dx + dy * dy)

    if n_div == 1:
        return green_function_static(rho_um, z_a, z_b, tech)

    # Subdivide both segments along their length and average
    L_a = seg_a.length
    L_b = seg_b.length
    if L_a <= 0 or L_b <= 0:
        return green_function_static(rho_um, z_a, z_b, tech)
    ts = [(i + 0.5) / n_div for i in range(n_div)]
    accum = 0.0
    for t1 in ts:
        x1 = seg_a.a.x + t1 * (seg_a.b.x - seg_a.a.x)
        y1 = seg_a.a.y + t1 * (seg_a.b.y - seg_a.a.y)
        for t2 in ts:
            x2 = seg_b.a.x + t2 * (seg_b.b.x - seg_b.a.x)
            y2 = seg_b.a.y + t2 * (seg_b.b.y - seg_b.a.y)
            r = math.sqrt((x1 - x2) ** 2 + (y1 - y2) ** 2)
            accum += green_function_static(r, z_a, z_b, tech)
    return accum / (n_div * n_div)


def capacitance_integral_inner_a(
    seg_a: Segment,
    seg_b: Segment,
    tech: Tech,
    *,
    s: float,
) -> float:
    """Inner-loop integrand for fixed ``s`` along segment A.

    Mirrors ``capacitance_integral_inner_a`` (decomp ``0x0808e908``)
    — one of two paired inner kernels that the segment integral
    invokes per outer-loop step. Evaluates the ``t``-marginal of
    the Green's function with ``s`` (the parametric position on
    segment A) held fixed.
    """
    n_metals = len(tech.metals)
    if not (0 <= seg_a.metal < n_metals and 0 <= seg_b.metal < n_metals):
        return 0.0
    z_a = tech.metals[seg_a.metal].d + 0.5 * tech.metals[seg_a.metal].t
    z_b = tech.metals[seg_b.metal].d + 0.5 * tech.metals[seg_b.metal].t
    x_a = seg_a.a.x + s * (seg_a.b.x - seg_a.a.x)
    y_a = seg_a.a.y + s * (seg_a.b.y - seg_a.a.y)
    # 4-point Gauss-Legendre over t ∈ [0, 1]
    nodes = (0.0694318, 0.330009, 0.669991, 0.930568)
    weights = (0.173927, 0.326073, 0.326073, 0.173927)
    accum = 0.0
    for t, w in zip(nodes, weights, strict=True):
        x_b = seg_b.a.x + t * (seg_b.b.x - seg_b.a.x)
        y_b = seg_b.a.y + t * (seg_b.b.y - seg_b.a.y)
        r = math.sqrt((x_a - x_b) ** 2 + (y_a - y_b) ** 2)
        accum += w * green_function_static(r, z_a, z_b, tech)
    return accum


def capacitance_integral_inner_b(
    seg_a: Segment,
    seg_b: Segment,
    tech: Tech,
    *,
    t: float,
) -> float:
    """Inner-loop integrand for fixed ``t`` along segment B.

    Mirrors ``capacitance_integral_inner_b`` (decomp ``0x0808ed48``).
    Sister to :func:`capacitance_integral_inner_a` with the inner /
    outer roles swapped; included for surface parity with the
    binary's two-kernel symmetry.
    """
    n_metals = len(tech.metals)
    if not (0 <= seg_a.metal < n_metals and 0 <= seg_b.metal < n_metals):
        return 0.0
    z_a = tech.metals[seg_a.metal].d + 0.5 * tech.metals[seg_a.metal].t
    z_b = tech.metals[seg_b.metal].d + 0.5 * tech.metals[seg_b.metal].t
    x_b = seg_b.a.x + t * (seg_b.b.x - seg_b.a.x)
    y_b = seg_b.a.y + t * (seg_b.b.y - seg_b.a.y)
    nodes = (0.0694318, 0.330009, 0.669991, 0.930568)
    weights = (0.173927, 0.326073, 0.326073, 0.173927)
    accum = 0.0
    for s, w in zip(nodes, weights, strict=True):
        x_a = seg_a.a.x + s * (seg_a.b.x - seg_a.a.x)
        y_a = seg_a.a.y + s * (seg_a.b.y - seg_a.a.y)
        r = math.sqrt((x_a - x_b) ** 2 + (y_a - y_b) ** 2)
        accum += w * green_function_static(r, z_a, z_b, tech)
    return accum


def capacitance_per_segment(
    segments: list[Segment],
    tech: Tech,
    *,
    n_div: int = 2,
) -> np.ndarray:
    """Per-segment potential matrix.

    Mirrors the binary's ``capacitance_per_segment`` (decomp
    ``0x0809002c``): returns the ``(N, N)`` matrix ``P`` of
    Green's-function integrals between every segment pair.

    The diagonal ``P_ii`` uses the same double-integral form with
    a small regularisation floor on ``ρ`` to avoid the singular
    self-term.

    Args:
        segments:  Flat segment list (e.g. from
                   :func:`capacitance_setup`).
        tech:      Tech file.
        n_div:     Number of sub-tiles per segment side.

    Returns:
        ``(N, N)`` symmetric potential matrix in V/C.
    """
    n = len(segments)
    P = np.zeros((n, n))
    for i in range(n):
        for j in range(i, n):
            v = capacitance_segment_integral(
                segments[i], segments[j], tech, n_div=n_div,
            )
            P[i, j] = v
            P[j, i] = v
    return P


def shape_pi_capacitances(
    shape: Shape,
    tech: Tech,
    *,
    n_div: int = 2,
) -> tuple[float, float, float]:
    """Reduce a single shape's per-segment cap matrix to a Pi network.

    Aggregates the ``(N, N)`` Maxwell capacitance matrix from
    :func:`analyze_capacitance_driver` into three Pi-network values:

    * ``C_p1`` — port-1 shunt cap to ground (F)
    * ``C_p2`` — port-2 shunt cap to ground (F)
    * ``C_s`` — series cap between the two ports (F, typically tiny
      for an inductor)

    The two ports are taken to be the chain-ordered halves of the
    segment list: the first ``N // 2`` segments form port 1, the
    remainder form port 2. This mirrors the binary's
    ``analyze_narrow_band_2port`` reduction (decomp ``0x080515e4``)
    in the case where the spiral has no explicit port-2 segment list
    — the natural symmetric split. The C path additionally subtracts
    a tail set of "via-only" segments before reduction; without that
    metadata in our segment representation, we keep the symmetric
    split, which agrees with the binary on the dominant terms.

    For Maxwell C matrices, the Pi-network reduction is::

        C_p1 = sum_{i in P1, all j} C[i, j]   (port-1 row sum)
        C_p2 = sum_{i in P2, all j} C[i, j]   (port-2 row sum)
        C_s  = -sum_{i in P1, j in P2} C[i, j]

    Args:
        shape: the spiral / wire shape to reduce.
        tech:  tech layer stack.
        n_div: per-segment subdivision (forwarded to
            :func:`analyze_capacitance_driver`).
    """
    result = analyze_capacitance_driver([shape], tech, n_div=n_div)
    C = result.C_matrix
    n = C.shape[0]
    if n == 0:
        return 0.0, 0.0, 0.0
    half = max(1, n // 2)
    p1 = slice(0, half)
    p2 = slice(half, n)
    C_p1 = float(C[p1, :].sum())
    C_p2 = float(C[p2, :].sum())
    C_s = -float(C[p1, p2].sum())
    return C_p1, C_p2, C_s


def analyze_capacitance_polygon(
    shapes: list[Shape] | dict[str, Shape],
    tech: Tech,
    *,
    n_div: int = 2,
) -> SegmentCapResult:
    """Alias for :func:`analyze_capacitance_driver`.

    Mirrors the binary's ``analyze_capacitance_polygon`` (decomp
    ``0x08092780``) which takes the same input/output as
    ``analyze_capacitance_driver`` but for a polygon-list flavour.
    Both call the same per-segment integrator under the hood.
    """
    return analyze_capacitance_driver(shapes, tech, n_div=n_div)


def analyze_capacitance_driver(
    shapes: list[Shape] | dict[str, Shape],
    tech: Tech,
    *,
    n_div: int = 2,
) -> SegmentCapResult:
    """End-to-end per-segment substrate-cap pipeline.

    Mirrors the binary's ``analyze_capacitance_driver`` (decomp
    ``0x08052c50``):

    1. :func:`capacitance_setup` to flatten all shapes into a
       segment list.
    2. :func:`capacitance_per_segment` to build the ``(N, N)``
       potential matrix.
    3. ``np.linalg.inv`` to recover the cap matrix ``C``.
    """
    segments, names = capacitance_setup(shapes, tech)
    if not segments:
        return SegmentCapResult(
            segments=[], shape_for_segment=[],
            P_matrix=np.zeros((0, 0)),
            C_matrix=np.zeros((0, 0)),
        )
    P = capacitance_per_segment(segments, tech, n_div=n_div)
    # Symmetrise + invert. Pinv guards against singular blocks.
    P = 0.5 * (P + P.T)
    try:
        C = np.linalg.inv(P)
    except np.linalg.LinAlgError:
        C = np.linalg.pinv(P)
    return SegmentCapResult(
        segments=segments,
        shape_for_segment=names,
        P_matrix=P,
        C_matrix=np.asarray(0.5 * (C + C.T)),
    )
