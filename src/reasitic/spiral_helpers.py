"""Spiral geometry / cell-sizing helper functions.

Mirrors a cluster of small spiral-parameterisation helpers from the
binary that the OptSq / OptPoly inner loops invoke per iteration:

* :func:`spiral_max_n`            ↔ ``spiral_FindMaxN`` (decomp ``0x08072a80``)
* :func:`spiral_radius_for_n`     ↔ ``spiral_radius_for_N`` (``0x0806c608``)
* :func:`spiral_turn_position`    ↔ ``spiral_turn_position_recursive`` (``0x080943ac``)
* :func:`wire_position_periodic_fold` ↔ ``wire_position_periodic_fold`` (``0x08094370``)
* :func:`segment_pair_distance_metric` ↔ ``segment_pair_distance_metric`` (``0x08094a5c``)

The spiral-type encoding is the binary's case-table:

* ``0``  / ``3`` / ``5`` / ``0x10`` / ``0x12`` — square / symmetric-square
                                                  / rectangular variants
* ``1``  / ``0x11`` / ``0x14``                  — polygon spiral, symmetric
                                                  polygon, etc.

For the canonical Python-side calls a handful of named-string
aliases (``"square"``, ``"polygon"``, ...) are accepted so callers
don't need to remember the magic codes.
"""

from __future__ import annotations

import math

# Spiral-type code tables (mirrors decomp case statements)
_SQUARE_LIKE = (0, 3, 5, 0x10, 0x12)
_POLYGON_LIKE = (1, 0x11, 0x14)

_NAME_TO_CODE = {
    "square": 0,
    "rect": 0,
    "rectangle": 0,
    "symsq": 3,
    "symmetric_square": 3,
    "spiral": 1,
    "polygon": 1,
    "sympoly": 0x11,
    "symmetric_polygon": 0x11,
}


def _resolve_type(spiral_type: int | str) -> int:
    if isinstance(spiral_type, int):
        return spiral_type
    code = _NAME_TO_CODE.get(spiral_type.lower())
    if code is None:
        raise ValueError(
            f"unknown spiral type {spiral_type!r}; "
            f"choose from {sorted(_NAME_TO_CODE)}"
        )
    return code


def spiral_max_n(
    *,
    outer_dim_um: float,
    width_um: float,
    spacing_um: float,
    spiral_type: int | str = "square",
    sides: int = 4,
) -> float:
    """Maximum integer turn count that fits the spiral footprint.

    Mirrors ``spiral_FindMaxN`` (decomp ``0x08072a80``):

    * Square (type 0): ``N = round(L / (1 + 2(W + S)))`` with a
      Q1-quartic refinement for fractional turns.
    * Polygon (type 1): ``N = (L − W) · cos(π/sides) / (S + W) − 2``.

    Args:
        outer_dim_um:  Outer-edge length / radius in μm.
        width_um:      Trace width in μm.
        spacing_um:    Edge-to-edge spacing in μm.
        spiral_type:   ``"square"`` or ``"polygon"`` (or the binary's
                       integer code).
        sides:         Polygon side count for polygon spirals.

    Returns:
        The maximum (possibly fractional) ``N``. Returns ``-1.0`` if
        the spiral type is unrecognised, matching the binary's
        error-path return value.
    """
    code = _resolve_type(spiral_type)
    L = float(outer_dim_um)
    W = float(width_um)
    S = float(spacing_um)
    if code == 0:
        # Square: linear formula with a quartile refinement
        pitch = W + S
        x = L / (1.0 + 2.0 * pitch)
        n_int = round(x)
        # Q1 refinement: round(x*4) - 4*round(x), then divide by 4
        q1 = round(x * 4.0) - 4.0 * n_int
        return float(n_int + q1 * 0.25 - 0.25)
    if code == 1:
        if sides <= 0:
            raise ValueError("sides must be positive for polygon spirals")
        cos_factor = math.cos(math.pi / float(sides))
        return float(((L - W) * cos_factor) / (S + W) - 2.0)
    return -1.0


def spiral_radius_for_n(
    *,
    outer_dim_um: float,
    width_um: float,
    spacing_um: float,
    sides: int = 4,
    spiral_type: int | str = "square",
) -> float:
    """Inverse of :func:`spiral_max_n` — given the parameters, return
    the corner-rounded radius.

    Mirrors ``spiral_radius_for_N`` (decomp ``0x0806c608``).
    Square-like cases use ``r = 0.5 · (L + W) / (W + S)``; polygon-
    like cases use ``r = L · cos(π/sides) / (W + S)``.

    The result is then quantised on a 1/sides grid:
    ``r = round(r) + round((r − round(r)) · sides) / sides``,
    which is the binary's quirky mid-fractional-turn snap. For the
    ``0x10 / 0x11`` symmetric-rect variants the result is fully
    rounded to an integer at the end (no fractional turns allowed).
    """
    code = _resolve_type(spiral_type)
    L = float(outer_dim_um)
    W = float(width_um)
    S = float(spacing_um)
    if code in _SQUARE_LIKE:
        r = 0.5 * (L + W) / (W + S)
    elif code in _POLYGON_LIKE:
        if sides <= 0:
            raise ValueError("sides must be positive for polygon spirals")
        r = L * math.cos(math.pi / float(sides)) / (W + S)
    else:
        return 1e15
    # Mid-fractional-turn snap on a 1/sides grid
    base = round(r)
    frac = round((r - base) * sides) / float(sides) if sides > 0 else 0.0
    r = base + frac
    if code - 0x10 < 2:  # 0x10, 0x11 — symmetric-rect / symmetric-poly
        return float(round(r))
    return float(r)


def spiral_turn_position(
    *,
    i: int,
    outer_dim_um: float,
    width_um: float,
    spacing_um: float,
    fold_size: int,
) -> float:
    """Position of the ``i``-th wire turn, with reflection across the fold.

    Mirrors ``spiral_turn_position_recursive`` (decomp ``0x080943ac``):

    * If ``fold_size < i``, recurse with the reflected index
      ``(2·fold_size − i) + 1`` and negate.
    * Otherwise return ``0.5 · (outer_dim − W) − (W + S) · (i − 1)``.

    Used by the symmetric-spiral builders to place each turn at the
    right offset.
    """
    if fold_size < i:
        inner = spiral_turn_position(
            i=(fold_size * 2 - i) + 1,
            outer_dim_um=outer_dim_um,
            width_um=width_um,
            spacing_um=spacing_um,
            fold_size=fold_size,
        )
        return -inner
    return 0.5 * (outer_dim_um - width_um) - (width_um + spacing_um) * (i - 1)


def wire_position_periodic_fold(
    *,
    i: int,
    outer_dim_um: float,
    width_um: float,
    spacing_um: float,
    fold_size: int,
) -> float:
    """1-D position-folding helper for the wire-discretisation pass.

    Mirrors ``wire_position_periodic_fold`` (decomp ``0x08094370``).
    Reflects ``i`` across the fold centre until it lands in
    ``[0, fold_size]``, then returns
    ``(outer − W) − (W + S) · 2 · (i − 1)``.
    """
    while fold_size < i:
        i = (fold_size * 2 - i) + 1
    return (outer_dim_um - width_um) - (width_um + spacing_um) * 2.0 * (i - 1)


def segment_pair_distance_metric(
    seg: object,
) -> int:
    """Cheap integer distance metric used to sort segment pairs.

    Mirrors ``segment_pair_distance_metric`` (decomp ``0x08094a5c``):

    .. code-block:: text

        metric = ((seg[0x10] − seg[8]) // 1000)
               + ((seg[0xc]  − seg[4]) ·  1000)

    The decomp reads four ``int`` fields from a 32-byte segment
    record. The Python equivalent picks the same fields off any
    object that exposes integer-coercible ``a.x``, ``a.y``, ``b.x``,
    ``b.y`` attributes (e.g. our :class:`reasitic.geometry.Segment`).
    """
    a_x = int(seg.a.x)  # type: ignore[attr-defined]
    a_y = int(seg.a.y)  # type: ignore[attr-defined]
    b_x = int(seg.b.x)  # type: ignore[attr-defined]
    b_y = int(seg.b.y)  # type: ignore[attr-defined]
    return (b_x - a_x) // 1000 + (b_y - a_y) * 1000
