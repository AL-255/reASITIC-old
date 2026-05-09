"""DC resistance per polygon / shape.

Per-segment formula:

.. math::

    R = \\rho_\\text{sh} \\cdot \\frac{L}{W}

where ``ρ_sh`` is the metal layer's sheet resistance (Ω/sq), ``L`` is
the segment length and ``W`` its width. The total DC resistance of
a shape is the sum over its segments. Vias contribute the
per-via-cell resistance from the tech file.

This mirrors the simplest path through ``compute_dc_resistance_per_polygon``
(``asitic_kernel.c:267``) — that decompiled function additionally
splits the sum into "primary" / "secondary" buckets at a tap point and
computes microstrip capacitances; the bare resistance summation is
all we need for the standard ``Res`` REPL command.
"""

from __future__ import annotations

from reasitic.geometry import Segment, Shape
from reasitic.tech import Tech


def segment_dc_resistance(segment: Segment, tech: Tech) -> float:
    """Return the DC resistance of one segment in Ω.

    Resolves the metal layer from ``tech`` to read its sheet
    resistance. Zero-length or zero-width segments contribute 0.
    """
    if segment.length <= 0 or segment.width <= 0:
        return 0.0
    if segment.metal < 0 or segment.metal >= len(tech.metals):
        # Out-of-range metal index: treat as zero contribution rather
        # than silently using rsh from a wrong layer.
        return 0.0
    rsh = tech.metals[segment.metal].rsh
    return rsh * segment.length / segment.width


def compute_dc_resistance(shape: Shape, tech: Tech) -> float:
    """Return the total DC resistance of ``shape`` in Ω.

    Sums :func:`segment_dc_resistance` over every segment, treating
    the spiral as a single series chain (which is correct for the
    standard one-port self-resistance reported by ASITIC's ``Res``
    command).
    """
    return sum(segment_dc_resistance(s, tech) for s in shape.segments())
