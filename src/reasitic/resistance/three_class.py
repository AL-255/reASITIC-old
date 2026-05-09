"""Three-class material-weighted DC-resistance accumulator.

Mirrors the binary's ``compute_dc_resistance_3metal_constants``
(``decomp/output/asitic_kernel.c:763``, address ``0x0804ed64``).

The function walks every polygon edge of ``shape`` and accumulates
three weighted resistance buckets ``R_a / R_b / R_c`` keyed by a
fixed table of small constants. The original docstring describes
them only as "three material constants -- one per metal class"; the
constants are tabulated in the binary as:

* ``c1 = 5.6e-17``, ``c2 = 5.3e-17`` — bucket A multipliers
* ``c1 = 5.6e-17``, ``c2 = 2.8e-17`` — bucket B multipliers
* ``c1 = 4.0e-17``, ``c2 = 1.9e-17`` — bucket C multipliers

The bucket formulas are::

    R_a += R_seg * 5.3e-17 + 2*L * 5.6e-17
    R_b += R_seg * 2.8e-17 + 2*L * 5.6e-17
    R_c += R_seg * 1.9e-17 + 2*L * 4.0e-17

where ``R_seg = rsh * L`` is the conventional sheet-resistance form
(in Ω) and ``L`` is the segment length (in μm — converted to cm via
the binary's per-segment storage convention; here we expose both
buckets so callers can pick the unit system that matches the
metric they are deriving). The numeric semantics of the buckets are
not documented in the binary; preserving the exact formula keeps
parity with the binary's downstream consumers (it is one of the
inputs to a substrate-coupled R reporting path).
"""

from __future__ import annotations

from dataclasses import dataclass

from reasitic.geometry import Shape
from reasitic.resistance.dc import segment_dc_resistance
from reasitic.tech import Tech

# Per-bucket constants from the decomp tables (decomp lines 789-793)
_C_A_LEN = 5.6e-17
_C_A_R = 5.3e-17
_C_B_LEN = 5.6e-17
_C_B_R = 2.8e-17
_C_C_LEN = 4.0e-17
_C_C_R = 1.9e-17


@dataclass(frozen=True)
class ThreeClassResistance:
    """Three weighted DC-resistance accumulator buckets."""

    R_a: float
    R_b: float
    R_c: float


def three_class_resistance(shape: Shape, tech: Tech) -> ThreeClassResistance:
    """Three-class material-weighted DC-resistance accumulator.

    Returns a :class:`ThreeClassResistance` triple ``(R_a, R_b, R_c)``
    with each bucket combining a length term and a sheet-resistance
    term per the binary's fixed weight table.

    Parameters
    ----------
    shape:
        The geometry to walk. The function visits every segment of
        every polygon.
    tech:
        Tech file the shape was built against. Used to look up each
        segment's metal sheet resistance.
    """
    R_a = 0.0
    R_b = 0.0
    R_c = 0.0
    for poly in shape.polygons:
        for seg in poly.edges():
            length = _segment_length(seg)
            R_seg = segment_dc_resistance(seg, tech)
            two_L = 2.0 * length
            R_a += R_seg * _C_A_R + two_L * _C_A_LEN
            R_b += R_seg * _C_B_R + two_L * _C_B_LEN
            R_c += R_seg * _C_C_R + two_L * _C_C_LEN
    return ThreeClassResistance(R_a=R_a, R_b=R_b, R_c=R_c)


def _segment_length(seg: object) -> float:
    """Length of a Segment in μm — duplicated locally to avoid a
    circular import with the inductance kernel."""
    a = seg.a  # type: ignore[attr-defined]
    b = seg.b  # type: ignore[attr-defined]
    dx: float = b.x - a.x
    dy: float = b.y - a.y
    dz: float = b.z - a.z
    return float((dx * dx + dy * dy + dz * dz) ** 0.5)
