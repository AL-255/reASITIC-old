"""Shunt capacitance from metal traces to substrate ground.

For each polygon on metal layer ``m`` we model the capacitance to
the substrate's bulk ground as a parallel-plate cap

.. math::

    C_p = \\varepsilon_0 \\varepsilon_r \\, A / h

with ``A`` the polygon's footprint area, ``h`` the vertical distance
from the metal centreline to the bottom of the layer stack, and
``ε_r`` the layer-stack-averaged relative permittivity. This is a
textbook approximation; the binary's full Green's-function path
captures lateral coupling that this stub ignores.

The fringe correction adds the standard 0.5·ε₀·(perimeter) term
(Yuan & Trick 1982).

Mirrors the simpler half of ``coupled_microstrip_caps_hj``
(``asitic_kernel.c:0x0804df6c``).
"""

from __future__ import annotations

from reasitic.geometry import Point, Shape
from reasitic.tech import Tech
from reasitic.units import EPS_0, UM_TO_M


def parallel_plate_cap_per_area(eps_r: float, h_um: float) -> float:
    """C/A in F/μm² for a parallel-plate cap of dielectric ``eps_r``
    and thickness ``h`` (μm)."""
    if h_um <= 0:
        return float("inf")
    return EPS_0 * eps_r / (h_um * UM_TO_M)


def _polygon_signed_area(vertices: list[Point]) -> float:
    """Shoelace area of a 2D polygon (xy plane) in μm²."""
    n = len(vertices)
    if n < 3:
        return 0.0
    area = 0.0
    for i in range(n - 1):
        v_i = vertices[i]
        v_j = vertices[i + 1]
        area += v_i.x * v_j.y - v_j.x * v_i.y
    return 0.5 * area


def _polygon_perimeter(vertices: list[Point]) -> float:
    if len(vertices) < 2:
        return 0.0
    total = 0.0
    for i in range(len(vertices) - 1):
        total += vertices[i].distance_to(vertices[i + 1])
    return total


def shape_shunt_capacitance(shape: Shape, tech: Tech) -> float:
    """Total shunt capacitance from ``shape`` to substrate ground, in F.

    For each polygon we model the path from its metal-layer
    centreline down to the substrate ground as a stack of series
    parallel-plate caps, one per dielectric layer between the metal
    and the ground:

    .. math::

        \\frac{1}{C_\\text{path}} = \\sum_k \\frac{h_k}{\\varepsilon_0
                                                   \\varepsilon_{r,k} A}

    so the equivalent ``ε_eff = h_total / Σ (h_k / ε_{r,k})`` only
    averages layers actually in the path to ground (rather than
    every substrate layer in the tech file as the previous version
    did). The fringe term keeps the same Yuan–Trick form on
    ``ε_eff``.

    Mirrors the simpler half of ``coupled_microstrip_caps_hj``
    (``asitic_kernel.c:0x0804df6c``).
    """
    if not tech.layers:
        return 0.0
    total_C = 0.0
    for poly in shape.polygons:
        if poly.metal < 0 or poly.metal >= len(tech.metals):
            continue
        m = tech.metals[poly.metal]
        if m.layer >= len(tech.layers):
            continue
        # Stack of layers strictly below the metal's assigned layer
        below = tech.layers[: m.layer]
        # Plus the part of the metal's own layer between ground-side
        # of the layer and the metal centreline.
        own_thickness_below = max(0.0, m.d)
        # Total path height
        h_total = sum(layer.t for layer in below) + own_thickness_below
        if h_total <= 0:
            continue
        # Series-cap effective ε_r over the path-to-ground layers
        inv_eps_total = (
            sum((layer.t / layer.eps) for layer in below if layer.eps > 0)
            + own_thickness_below / max(tech.layers[m.layer].eps, 1.0)
        )
        eps_eff = h_total / inv_eps_total if inv_eps_total > 0 else 1.0
        A_um2 = abs(_polygon_signed_area(poly.vertices))
        C_per_area = parallel_plate_cap_per_area(eps_eff, h_total)
        total_C += C_per_area * A_um2 * (UM_TO_M**2)
        # Fringe term — unchanged
        per_um = _polygon_perimeter(poly.vertices)
        total_C += 0.5 * EPS_0 * eps_eff * per_um * UM_TO_M
    return total_C
