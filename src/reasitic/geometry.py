"""Geometric primitives for ASITIC shapes.

The original C code packs every shape into a 188-byte (``0xbc``)
record with field offsets recovered by Ghidra; here we use plain
dataclasses. The conceptual model preserved is::

    Shape ──> Polygon ──> Polygon ──> ...    (linked list, +0xec next)
              │
              └── per-polygon: vertices, metal layer, edge data

The numerical kernel doesn't actually consume polygon vertices
directly — it consumes a list of *segments* (straight conductor
runs) that get further discretised into *filaments*. Each segment
carries its endpoints, width, thickness, metal layer and direction
unit-vector.

For the closed-form Grover formulas used in the inductance kernels
the segment orientation is captured by its endpoints; width and
thickness come from the metal-layer descriptor.
"""

from __future__ import annotations

import math
from collections.abc import Callable
from dataclasses import dataclass, field

from reasitic.tech import Metal, Tech


@dataclass(frozen=True)
class Point:
    """A 3D point in microns. ``z`` is the metal-layer center height."""

    x: float
    y: float
    z: float = 0.0

    def __add__(self, other: Point) -> Point:
        """Component-wise vector addition."""
        return Point(self.x + other.x, self.y + other.y, self.z + other.z)

    def __sub__(self, other: Point) -> Point:
        """Component-wise vector subtraction."""
        return Point(self.x - other.x, self.y - other.y, self.z - other.z)

    def distance_to(self, other: Point) -> float:
        """3D Euclidean distance to ``other``."""
        dx = self.x - other.x
        dy = self.y - other.y
        dz = self.z - other.z
        return math.sqrt(dx * dx + dy * dy + dz * dz)


@dataclass
class Segment:
    """A straight conductor run between two endpoints.

    ``a`` and ``b`` are the endpoints; ``width`` and ``thickness`` are
    the cross-section dimensions (microns). ``metal`` is the metal
    layer index (resolved against :class:`reasitic.tech.Tech`).
    """

    a: Point
    b: Point
    width: float
    thickness: float
    metal: int

    @property
    def length(self) -> float:
        """Length of the segment in the same units as the endpoints."""
        return self.a.distance_to(self.b)

    @property
    def direction(self) -> tuple[float, float, float]:
        """Unit vector from ``a`` to ``b``. Zero-length segments return ``(0, 0, 0)``."""
        L = self.length
        if L == 0.0:
            return (0.0, 0.0, 0.0)
        return (
            (self.b.x - self.a.x) / L,
            (self.b.y - self.a.y) / L,
            (self.b.z - self.a.z) / L,
        )


@dataclass
class Polygon:
    """A closed polyline on a single metal layer."""

    vertices: list[Point]
    metal: int
    width: float = 0.0
    thickness: float = 0.0

    def edges(self) -> list[Segment]:
        """Return the segments connecting consecutive vertices."""
        segs: list[Segment] = []
        n = len(self.vertices)
        for i in range(n - 1):
            segs.append(
                Segment(
                    a=self.vertices[i],
                    b=self.vertices[i + 1],
                    width=self.width,
                    thickness=self.thickness,
                    metal=self.metal,
                )
            )
        return segs


@dataclass
class Shape:
    """A named structure built up from polygons.

    Mirrors the original C ``Shape`` record (offsets 0x00..0xbc).
    Per-shape parameters (``width``, ``spacing``, ``turns``, etc.)
    are stored verbatim from the build call so downstream code can
    re-emit the original CLI form.
    """

    name: str
    polygons: list[Polygon] = field(default_factory=list)
    # Build parameters retained for re-export / Geom-info display
    width: float = 0.0
    length: float = 0.0
    spacing: float = 0.0
    turns: float = 0.0
    sides: int = 4
    metal: int = 0
    exit_metal: int | None = None
    x_origin: float = 0.0
    y_origin: float = 0.0
    orientation: int = 0  # 1 == cw, -1 == ccw, 0 == as-built
    phase: float = 0.0
    kind: str = ""
    # Polygon-spiral specific: outer-vertex radius used by the builder.
    # Lets downstream code recover the spiral centre (which sits at
    # ``(x_origin + radius - pitch_radial/4, y_origin + radius - pitch_radial/2)``
    # for the binary's coord convention). Default 0.0 = "not a polygon spiral".
    radius: float = 0.0

    def segments(self) -> list[Segment]:
        """Flat list of every polygon edge in the shape."""
        out: list[Segment] = []
        for poly in self.polygons:
            out.extend(poly.edges())
        return out

    def bounding_box(self) -> tuple[float, float, float, float]:
        """Return ``(xmin, ymin, xmax, ymax)`` over all vertices."""
        xs: list[float] = []
        ys: list[float] = []
        for p in self.polygons:
            for v in p.vertices:
                xs.append(v.x)
                ys.append(v.y)
        if not xs:
            return (0.0, 0.0, 0.0, 0.0)
        return (min(xs), min(ys), max(xs), max(ys))

    def translate(self, dx: float, dy: float) -> Shape:
        """Return a copy translated by ``(dx, dy)``."""
        return self._map_vertices(lambda v: Point(v.x + dx, v.y + dy, v.z),
                                  dx_origin=dx, dy_origin=dy)

    def flip_horizontal(self) -> Shape:
        """Mirror across the y-axis through the shape's origin (``x → -x``)."""
        cx = self.x_origin

        def f(v: Point) -> Point:
            return Point(2.0 * cx - v.x, v.y, v.z)

        return self._map_vertices(f)

    def flip_vertical(self) -> Shape:
        """Mirror across the x-axis through the shape's origin (``y → -y``)."""
        cy = self.y_origin

        def f(v: Point) -> Point:
            return Point(v.x, 2.0 * cy - v.y, v.z)

        return self._map_vertices(f)

    def rotate_xy(self, angle_rad: float) -> Shape:
        """Rotate the shape by ``angle_rad`` about its (x_origin, y_origin)."""
        c = math.cos(angle_rad)
        s = math.sin(angle_rad)
        cx, cy = self.x_origin, self.y_origin

        def f(v: Point) -> Point:
            x = v.x - cx
            y = v.y - cy
            return Point(cx + c * x - s * y, cy + s * x + c * y, v.z)

        return self._map_vertices(f)

    def _map_vertices(
        self,
        f: Callable[[Point], Point],
        *,
        dx_origin: float = 0.0,
        dy_origin: float = 0.0,
    ) -> Shape:
        new_polys = [
            Polygon(
                vertices=[f(v) for v in p.vertices],
                metal=p.metal,
                width=p.width,
                thickness=p.thickness,
            )
            for p in self.polygons
        ]
        return Shape(
            name=self.name,
            polygons=new_polys,
            width=self.width,
            length=self.length,
            spacing=self.spacing,
            turns=self.turns,
            sides=self.sides,
            metal=self.metal,
            exit_metal=self.exit_metal,
            x_origin=self.x_origin + dx_origin,
            y_origin=self.y_origin + dy_origin,
            orientation=self.orientation,
            phase=self.phase,
            kind=self.kind,
        )


# Polygon utilities ------------------------------------------------------


def polygon_edge_vectors(
    poly: Polygon,
    *,
    direction: str = "forward",
) -> list[tuple[float, float]]:
    """Return the per-edge ``(dx, dy)`` vectors for a polygon.

    Mirrors the binary's ``forward_diff_2d_inplace`` (decomp address
    ``0x08056198``) and ``backward_diff_2d_inplace`` (``0x08056148``)
    in-place differencing helpers.

    * ``direction="forward"`` returns ``vertices[i+1] - vertices[i]``
      for ``i in 0..N-2``; matches ``forward_diff_2d_inplace`` after
      ``-`` sign flip (the binary stores ``arr[i] -= arr[i+1]``, i.e.
      ``-(next - curr)``; we return the geometric forward edge).
    * ``direction="backward"`` returns ``vertices[i] - vertices[i-1]``
      for ``i in 1..N-1``; matches ``backward_diff_2d_inplace``.
    """
    if direction not in ("forward", "backward"):
        raise ValueError(f"direction must be 'forward' or 'backward', got {direction!r}")
    verts = poly.vertices
    if len(verts) < 2:
        return []
    if direction == "forward":
        return [
            (verts[i + 1].x - verts[i].x, verts[i + 1].y - verts[i].y)
            for i in range(len(verts) - 1)
        ]
    return [
        (verts[i].x - verts[i - 1].x, verts[i].y - verts[i - 1].y)
        for i in range(1, len(verts))
    ]


def shapes_bounding_box(
    shapes: list[Shape] | dict[str, Shape],
    tech: Tech | None = None,
) -> tuple[float, float, float, float]:
    """Return the union bbox ``(x_min, y_min, x_max, y_max)`` of ``shapes``.

    Mirrors the binary's ``compute_overall_bounding_box`` (decomp
    address ``0x08081ed4``). If the input is empty and ``tech`` is
    provided, falls back to the chip outline ``(0, 0, chipx, chipy)``;
    if neither shapes nor tech is supplied, returns the all-zero bbox.

    The world-frame translation ``(x_origin, y_origin)`` of each
    :class:`Shape` is folded into the bounding-box result, matching
    the binary which adds the cell offset to each shape's local bbox.
    """
    items: list[Shape] = (
        list(shapes.values()) if isinstance(shapes, dict) else list(shapes)
    )
    if not items:
        if tech is not None and tech.chip.chipx > 0 and tech.chip.chipy > 0:
            return (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)
        return (0.0, 0.0, 0.0, 0.0)

    x_min = float("+inf")
    y_min = float("+inf")
    x_max = float("-inf")
    y_max = float("-inf")
    for sh in items:
        bx0, by0, bx1, by1 = sh.bounding_box()
        if bx0 == bx1 == by0 == by1 == 0.0:
            continue
        x_min = min(x_min, bx0 + sh.x_origin)
        y_min = min(y_min, by0 + sh.y_origin)
        x_max = max(x_max, bx1 + sh.x_origin)
        y_max = max(y_max, by1 + sh.y_origin)
    if x_min == float("+inf"):
        # Every shape was empty
        if tech is not None and tech.chip.chipx > 0 and tech.chip.chipy > 0:
            return (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)
        return (0.0, 0.0, 0.0, 0.0)
    return (x_min, y_min, x_max, y_max)


def extend_terminal_segment(shape: Shape, *, dx_um: float = 0.0) -> Shape:
    """Extend the tail of ``shape``'s last polygon along its own axis.

    Mirrors ``shape_terminal_segment_extend_unit`` (decomp
    ``0x0805b348``). Walks to the last polygon, normalises the last
    edge's direction vector, then re-projects its endpoint to
    ``length/2 + dx_um`` along that direction.

    The binary uses this when extending a winding terminal so the
    last segment leaves the chip with a fixed unit length plus a
    small ``dx`` offset. Returns a copy; the original is untouched.
    """
    if not shape.polygons:
        return shape
    new_polys = [
        Polygon(
            vertices=list(p.vertices),
            metal=p.metal,
            width=p.width,
            thickness=p.thickness,
        )
        for p in shape.polygons
    ]
    last_poly = new_polys[-1]
    if len(last_poly.vertices) < 2:
        return shape
    a = last_poly.vertices[-2]
    b = last_poly.vertices[-1]
    dx = b.x - a.x
    dy = b.y - a.y
    dz = b.z - a.z
    length = math.sqrt(dx * dx + dy * dy + dz * dz)
    if length < 1e-12:
        return shape
    ux, uy, uz = dx / length, dy / length, dz / length
    new_length = 0.5 * length + dx_um
    new_b = Point(
        a.x + new_length * ux,
        a.y + new_length * uy,
        a.z + new_length * uz,
    )
    last_poly.vertices[-1] = new_b
    return Shape(
        name=shape.name,
        polygons=new_polys,
        width=shape.width,
        length=shape.length,
        spacing=shape.spacing,
        turns=shape.turns,
        sides=shape.sides,
        metal=shape.metal,
        exit_metal=shape.exit_metal,
        x_origin=shape.x_origin,
        y_origin=shape.y_origin,
        orientation=shape.orientation,
        phase=shape.phase,
        kind=shape.kind,
    )


def emit_vias_at_layer_transitions(shape: Shape, tech: Tech) -> Shape:
    """Insert via polygons between adjacent polygons on different metals.

    Mirrors ``shape_emit_vias_at_layer_transitions`` (decomp
    ``0x0805ba2c``). Walks the polygon list pair-wise; whenever two
    adjacent polygons are on different metal layers, looks up the
    via that bridges them and inserts a single-vertex (zero-extent)
    via polygon at the midpoint of the metal-to-metal transition.

    The via is placed on the via index of the matching ``Via``
    record in the tech file (matching ``top``/``bottom`` to the
    adjacent metal indices). If no via record matches, no insertion
    is made for that transition.

    Returns a copy; the original is untouched.
    """
    if len(shape.polygons) < 2:
        return shape
    # Build the via lookup: (top, bottom) → via_index (in tech.vias)
    via_lookup: dict[tuple[int, int], int] = {}
    for vidx, v in enumerate(tech.vias):
        via_lookup[(v.top, v.bottom)] = vidx
        via_lookup[(v.bottom, v.top)] = vidx

    new_polys: list[Polygon] = []
    for i, p in enumerate(shape.polygons):
        new_polys.append(
            Polygon(
                vertices=list(p.vertices),
                metal=p.metal,
                width=p.width,
                thickness=p.thickness,
            )
        )
        if i + 1 >= len(shape.polygons):
            continue
        nxt = shape.polygons[i + 1]
        if p.metal == nxt.metal:
            continue
        # Different metal layers — emit a via polygon
        key = (p.metal, nxt.metal)
        via_idx = via_lookup.get(key)
        if via_idx is None:
            continue
        # Midpoint of the transition: average of last vertex of p and
        # first vertex of nxt
        if not p.vertices or not nxt.vertices:
            continue
        a = p.vertices[-1]
        b = nxt.vertices[0]
        mid = Point(
            0.5 * (a.x + b.x),
            0.5 * (a.y + b.y),
            0.5 * (a.z + b.z),
        )
        # Tag the via polygon with a metal index past the metal-layer
        # count so downstream cap/inductance code can tell it apart
        new_polys.append(
            Polygon(
                vertices=[mid],
                metal=len(tech.metals) + via_idx,
                width=tech.vias[via_idx].width,
                thickness=0.0,
            )
        )
    return Shape(
        name=shape.name,
        polygons=new_polys,
        width=shape.width,
        length=shape.length,
        spacing=shape.spacing,
        turns=shape.turns,
        sides=shape.sides,
        metal=shape.metal,
        exit_metal=shape.exit_metal,
        x_origin=shape.x_origin,
        y_origin=shape.y_origin,
        orientation=shape.orientation,
        phase=shape.phase,
        kind=shape.kind,
    )


def extend_last_segment_to_chip_edge(shape: Shape, tech: Tech) -> Shape:
    """Push the last segment of ``shape`` out to the nearest chip boundary.

    Mirrors ``shape_extend_last_to_chip_edge`` (decomp ``0x0805b154``).
    The binary uses this on the export path so a winding's terminal
    segment sticks out of the chip outline by enough to become a port.

    The decision tree:

    * If the last segment runs in +Y → snap its tail to ``chipy``.
    * If it runs in -Y → snap its tail to ``0``.
    * If it runs in +X → snap its tail to ``chipx``.
    * If it runs in -X → snap its tail to ``0``.

    A copy of the shape is returned; the original is untouched.
    """
    if not shape.polygons:
        return shape
    chipx = tech.chip.chipx
    chipy = tech.chip.chipy
    if chipx <= 0 and chipy <= 0:
        return shape

    new_polys = [
        Polygon(
            vertices=list(p.vertices),
            metal=p.metal,
            width=p.width,
            thickness=p.thickness,
        )
        for p in shape.polygons
    ]
    last_poly = new_polys[-1]
    if len(last_poly.vertices) < 2:
        return shape
    a = last_poly.vertices[-2]
    b = last_poly.vertices[-1]
    dx = b.x - a.x
    dy = b.y - a.y
    eps = 1e-10
    if abs(dy) >= eps:
        # Vertical segment
        new_y = chipy if dy > 0 else 0.0
        last_poly.vertices[-1] = Point(b.x, new_y, b.z)
    elif abs(dx) <= eps:
        # Degenerate — leave it
        return shape
    else:
        new_x = chipx if dx > 0 else 0.0
        last_poly.vertices[-1] = Point(new_x, b.y, b.z)
    return Shape(
        name=shape.name,
        polygons=new_polys,
        width=shape.width,
        length=shape.length,
        spacing=shape.spacing,
        turns=shape.turns,
        sides=shape.sides,
        metal=shape.metal,
        exit_metal=shape.exit_metal,
        x_origin=shape.x_origin,
        y_origin=shape.y_origin,
        orientation=shape.orientation,
        phase=shape.phase,
        kind=shape.kind,
    )


def _closed_poly(
    corners: list[tuple[float, float]],
    *,
    z: float,
    metal: int,
    width: float,
    thickness: float,
) -> Polygon:
    verts = [Point(x, y, z) for x, y in corners]
    if verts and (verts[0].x != verts[-1].x or verts[0].y != verts[-1].y):
        verts.append(verts[0])
    return Polygon(vertices=verts, metal=metal, width=width, thickness=thickness)


def _polygon_record_to_poly(
    corners: list[tuple[float, float]],
    metal_rec: Metal,
    width: float,
) -> Polygon:
    z = metal_rec.d + metal_rec.t * 0.5
    return _closed_poly(
        corners,
        z=z,
        metal=metal_rec.index,
        width=width,
        thickness=metal_rec.t,
    )


def _square_layout_polygons(
    shape: Shape,
    tech: Tech,
    *,
    include_access: bool = True,
    trim_final: bool = True,
) -> list[Polygon]:
    """Return ASITIC display polygons for an SQ/MMSQ winding.

    Direct port of the polygon-emission part of
    ``cmd_square_build_geometry``.  ASITIC's CIF/GDS path stores
    trapezoidal metal ribbons, not centerlines, so exporters use this
    helper while analysis keeps using :meth:`Shape.segments`.
    """
    metal_rec = tech.metals[shape.metal]
    W = shape.width
    S = shape.spacing
    # ``length`` is not a Shape field; recover it from the layout bbox
    # metadata when available, otherwise from the centerline footprint.
    length = shape.length
    if length <= 0.0:
        if shape.polygons:
            bx0, by0, bx1, by1 = shape.bounding_box()
            length = max(bx1 - bx0, by1 - by0)
        else:
            return []
    if length <= 0.0:
        return []
    pitch = W + S
    n_int = int(math.floor(shape.turns))
    frac_side = int(round((shape.turns - n_int) * 4.0))
    polys: list[Polygon] = []
    last_corners: list[tuple[float, float]] | None = None
    last_side = 0

    for turn in range(n_int + 1):
        if turn == n_int and frac_side == 0:
            if last_corners is not None:
                # Binary trims the final side by W/2 when there is no
                # explicit exit-layer segment.
                pass
            break
        if turn > shape.turns:
            break
        inset = pitch * turn
        x0 = shape.x_origin + inset
        y0 = shape.y_origin + inset
        x1 = shape.x_origin + length - inset
        y1 = shape.y_origin + length - inset
        ix0 = x0 + W
        iy0 = y0 + W
        ix1 = x1 - W
        iy1 = y1 - W
        join = W
        top_left_outer_x = shape.x_origin + max(0, turn - 1) * pitch
        top_left_inner_x = top_left_outer_x if turn == 0 else top_left_outer_x + W

        side_polys = [
            [(top_left_outer_x, y1), (x1, y1), (ix1, iy1), (top_left_inner_x, iy1)],
            [(x1, y1), (x1, y0), (ix1, iy0), (ix1, iy1)],
            [(x1, y0), (x0, y0), (ix0, iy0), (ix1, iy0)],
            [
                (x0, y0),
                (x0, y1 - pitch),
                (ix0, y1 - pitch - W),
                (ix0, iy0),
            ],
        ]
        max_sides = 4
        if turn == n_int:
            max_sides = frac_side
        for side in range(max_sides):
            corners = side_polys[side]
            is_final_side = (
                (frac_side == 0 and turn == n_int - 1 and side == 3)
                or (frac_side > 0 and turn == n_int and side == max_sides - 1)
            )
            if is_final_side and not trim_final:
                # No exit / no next turn: the side runs straight to its
                # terminal outer corner without the chamfer that would
                # accommodate the next turn's perpendicular side.
                if side == 0:
                    # Top side: inner-end chamfer becomes the inner edge
                    # at the same x as the outer end.
                    corners = [corners[0], corners[1],
                               (corners[1][0], corners[2][1]), corners[3]]
                elif side == 1:
                    # Right side: bottom-inner chamfer disappears.
                    corners = [corners[0], corners[1],
                               (corners[2][0], corners[1][1]), corners[3]]
                elif side == 2:
                    # Bottom side: left-inner chamfer disappears.
                    corners = [corners[0], corners[1],
                               (corners[1][0], corners[2][1]), corners[3]]
                else:
                    # Left side: top-inner chamfer disappears.
                    corners = [corners[0], corners[1],
                               (corners[2][0], corners[1][1]), corners[3]]
            elif is_final_side and trim_final:
                if side == 0:
                    corners = [corners[0], (corners[1][0] - W, corners[1][1]),
                               corners[2], corners[3]]
                elif side == 1:
                    corners = [corners[0], (corners[1][0], corners[1][1] + W),
                               corners[2], corners[3]]
                elif side == 2:
                    corners = [corners[0], (corners[1][0] + W, corners[1][1]),
                               corners[2], corners[3]]
                else:
                    corners = [corners[0], (corners[1][0], corners[2][1]), corners[2], corners[3]]
            polys.append(_polygon_record_to_poly(corners, metal_rec, W))
            last_corners = corners
            last_side = side

    if include_access and polys:
        access = _square_access_polygons(shape, tech, polys[-1], last_side)
        polys.extend(access)
    return polys


def _square_access_polygons(
    shape: Shape,
    tech: Tech,
    last_poly: Polygon,
    last_side: int,
) -> list[Polygon]:
    exit_idx = shape.exit_metal
    if exit_idx is None:
        exit_idx = shape.metal - 1
    if exit_idx is None or exit_idx < 0 or exit_idx >= len(tech.metals):
        return []
    if exit_idx == shape.metal:
        return []
    via_rec = None
    via_idx = -1
    for i, v in enumerate(tech.vias):
        if {v.top, v.bottom} == {shape.metal, exit_idx}:
            via_rec = v
            via_idx = i
            break
    if via_rec is None:
        return []

    W = shape.width
    half = W * 0.5
    verts = last_poly.vertices
    if len(verts) < 4:
        return []
    # ASITIC places the via cluster at the centre of the terminal trace
    # width and one half-width back from the terminal end.
    xs = [v.x for v in verts[:-1]]
    ys = [v.y for v in verts[:-1]]
    if last_side == 0:       # top side, exits right
        cx, cy = max(xs) - half, (min(ys) + max(ys)) * 0.5
        ux, uy = 1.0, 0.0
    elif last_side == 1:     # right side, exits down
        cx, cy = (min(xs) + max(xs)) * 0.5, min(ys) + half
        ux, uy = 0.0, -1.0
    elif last_side == 2:     # bottom side, exits left
        cx, cy = min(xs) + half, (min(ys) + max(ys)) * 0.5
        ux, uy = -1.0, 0.0
    else:                    # left side, exits up
        cx, cy = (min(xs) + max(xs)) * 0.5, max(ys) - half
        ux, uy = 0.0, 1.0

    out: list[Polygon] = []
    top = tech.metals[shape.metal]
    exit_m = tech.metals[exit_idx]
    pad = [
        (cx - half, cy - half), (cx + half, cy - half),
        (cx + half, cy + half), (cx - half, cy + half),
    ]
    out.append(_polygon_record_to_poly(pad, exit_m, W))
    out.append(_polygon_record_to_poly(pad, top, W))

    overplot = max(via_rec.overplot1, via_rec.overplot2)
    pitch = via_rec.width + via_rec.space
    # Use floor to match the C binary's via-count convention
    # (asitic_repl.c: cmd_square_build_geometry's via cluster sizing
    # gives n = floor((W - 2·op + via_s) / (via_w + via_s))).
    # Verified against gold sq_170 (W=10 → n=4) and trans_200x8x3x3
    # (W=8 → n=3).
    n = max(1, int(math.floor((W - 2.0 * overplot + via_rec.space) / pitch)))
    span = (n - 1) * via_rec.space + n * via_rec.width
    z = 0.0
    via_metal = len(tech.metals) + via_idx
    for i in range(n):
        for j in range(n):
            x0 = cx - span * 0.5 + i * pitch
            y0 = cy - span * 0.5 + j * pitch
            out.append(_closed_poly(
                [(x0, y0), (x0 + via_rec.width, y0),
                 (x0 + via_rec.width, y0 + via_rec.width),
                 (x0, y0 + via_rec.width)],
                z=z,
                metal=via_metal,
                width=via_rec.width,
                thickness=0.0,
            ))

    bx0 = shape.x_origin
    by0 = shape.y_origin
    outer_len = shape.length if shape.length > 0.0 else max(
        shape.bounding_box()[2] - shape.bounding_box()[0],
        shape.bounding_box()[3] - shape.bounding_box()[1],
    )
    bx1 = shape.x_origin + outer_len
    by1 = shape.y_origin + outer_len
    tail_x = cx - ux * half
    tail_y = cy - uy * half
    if abs(ux) > abs(uy):
        outer = bx1 if ux > 0 else bx0
        ext = (outer - tail_x) * (1.0 if ux > 0 else -1.0)
    else:
        outer = by1 if uy > 0 else by0
        ext = (outer - tail_y) * (1.0 if uy > 0 else -1.0)
    lead_len = max(ext + W, 2.0 * W)
    head_x = tail_x + ux * lead_len
    head_y = tail_y + uy * lead_len
    nx = -uy * half
    ny = ux * half
    lead = [
        (tail_x + nx, tail_y + ny),
        (head_x + nx, head_y + ny),
        (head_x - nx, head_y - ny),
        (tail_x - nx, tail_y - ny),
    ]
    out.append(_polygon_record_to_poly(lead, exit_m, W))
    return out


def _polygon_bbox(polys: list[Polygon]) -> tuple[float, float, float, float]:
    """Return (xmin, xmax, ymin, ymax) over all vertices of ``polys``."""
    xs = [v.x for p in polys for v in p.vertices]
    ys = [v.y for p in polys for v in p.vertices]
    return (min(xs), max(xs), min(ys), max(ys))


def _polygon_fliph_apply(
    polys: list[Polygon],
    *,
    y_axis: float | None = None,
) -> list[Polygon]:
    """Mirror Y about a horizontal centerline.

    Mirrors ``cmd_fliph_apply`` (decomp ``0x08078d20``): computes
    ``y_sum = ymin + ymax`` of the bbox and replaces each ``y``
    with ``y_sum - y``. Pass ``y_axis = ymin + ymax`` explicitly
    to mirror about a known axis (useful when the input polygons'
    bbox includes access routing whose post-flip direction is the
    opposite of the desired one).
    """
    if not polys:
        return polys
    if y_axis is None:
        _, _, ymin, ymax = _polygon_bbox(polys)
        y_axis = ymin + ymax
    out: list[Polygon] = []
    for p in polys:
        verts = [Point(v.x, y_axis - v.y, v.z) for v in p.vertices]
        out.append(Polygon(vertices=verts, metal=p.metal,
                           width=p.width, thickness=p.thickness))
    return out


def _polygon_flipv_apply(
    polys: list[Polygon],
    *,
    x_axis: float | None = None,
) -> list[Polygon]:
    """Mirror X about a vertical centerline.

    Mirrors ``cmd_flipv_apply`` (decomp ``0x08078cdc``): computes
    ``x_sum = xmin + xmax`` of the bbox and replaces each ``x``
    with ``x_sum - x``. Pass ``x_axis = xmin + xmax`` explicitly
    when the bbox-derived value would include unwanted offsets.
    """
    if not polys:
        return polys
    if x_axis is None:
        xmin, xmax, _, _ = _polygon_bbox(polys)
        x_axis = xmin + xmax
    out: list[Polygon] = []
    for p in polys:
        verts = [Point(x_axis - v.x, v.y, v.z) for v in p.vertices]
        out.append(Polygon(vertices=verts, metal=p.metal,
                           width=p.width, thickness=p.thickness))
    return out


def _polygons_relayer(polys: list[Polygon], tech: Tech, new_metal: int) -> list[Polygon]:
    """Return ``polys`` with ``metal``, ``thickness`` and vertex ``z``
    fields swapped to ``new_metal``."""
    if new_metal < 0 or new_metal >= len(tech.metals):
        return polys
    m = tech.metals[new_metal]
    z = m.d + m.t * 0.5
    out: list[Polygon] = []
    for p in polys:
        verts = [Point(v.x, v.y, z) for v in p.vertices]
        out.append(Polygon(vertices=verts, metal=new_metal,
                           width=p.width, thickness=m.t))
    return out


def _mmsquare_layout_polygons(shape: Shape, tech: Tech) -> list[Polygon]:
    """Return CIF/GDS-equivalent polygons for an MMSQ multi-metal stack.

    Mirrors ``cmd_mmsquare_build_geometry`` (decomp ``0x0805af5c``):

    1. Build a square spiral on the top metal (``shape.metal``)
       with no exit routing — pure square spiral.
    2. For each metal layer between top and ``shape.exit_metal``
       (inclusive), clone the spiral, swap the metal layer, apply
       ``cmd_fliph_apply`` (Y-mirror about bbox centerline) for
       integer or half-integer turns, then reverse the linked
       list order.

    The C alternates the flip direction between ``fliph`` and
    ``flipv`` for half-integer turns. For integer turns it always
    uses ``fliph``; that's what we implement here. Half-integer
    behaviour is a follow-up.
    """
    if shape.exit_metal is None:
        return _square_layout_polygons(shape, tech, include_access=False)
    top_metal = shape.metal
    bot_metal = shape.exit_metal
    if top_metal <= bot_metal:
        return _square_layout_polygons(shape, tech, include_access=False)

    # Build the top-layer square spiral (no exit access routing — MMSQ
    # forces exit_metal to -1 inside the C cmd_square_build_geometry call)
    top_shape = Shape(
        name=shape.name, polygons=shape.polygons,
        width=shape.width, length=shape.length, spacing=shape.spacing,
        turns=shape.turns, sides=4, metal=top_metal, exit_metal=None,
        x_origin=shape.x_origin, y_origin=shape.y_origin,
        phase=shape.phase, kind="square",
    )
    top_polys = _square_layout_polygons(
        top_shape, tech, include_access=False, trim_final=False,
    )
    out: list[Polygon] = list(top_polys)

    # Build each subsequent metal layer from the top via fliph + reverse
    prev_polys = top_polys
    for layer_idx in range(top_metal - 1, bot_metal - 1, -1):
        flipped = _polygon_fliph_apply(prev_polys)
        flipped = list(reversed(flipped))
        flipped = _polygons_relayer(flipped, tech, layer_idx)
        out.extend(flipped)
        prev_polys = flipped

    return out


def _polygon_spiral_layout_polygons(shape: Shape, tech: Tech) -> list[Polygon]:
    metal_rec = tech.metals[shape.metal]
    sides = shape.sides
    if sides < 3 or shape.radius <= 0.0:
        return []
    R = shape.radius
    W = shape.width
    S = shape.spacing
    cos_half = math.cos(math.pi / sides)
    radial_w = W / cos_half
    radial_step = (W + S) / cos_half / sides
    n_round = int(round(shape.turns))
    loops = int(round(shape.turns + 1.0))
    r = R
    raw: list[list[tuple[float, float]]] = []
    for turn in range(1, loops + 1):
        n_side = sides
        if turn == loops:
            n_side = int(round((shape.turns - n_round) * sides + 1.0 / (2.0 * sides)))
        for i in range(1, n_side + 1):
            a0 = shape.phase + 2.0 * math.pi * (i - 1) / sides
            a1 = shape.phase + 2.0 * math.pi * i / sides
            outer0 = (r * math.cos(a0), r * math.sin(a0))
            inner0 = ((r - radial_w) * math.cos(a0), (r - radial_w) * math.sin(a0))
            r -= radial_step
            outer1 = (r * math.cos(a1), r * math.sin(a1))
            inner1 = ((r - radial_w) * math.cos(a1), (r - radial_w) * math.sin(a1))
            raw.append([outer0, outer1, inner1, inner0])
    if not raw:
        return []
    xs = [x for poly in raw for x, _ in poly]
    ys = [y for poly in raw for _, y in poly]
    dx = shape.x_origin + (max(xs) - min(xs)) * 0.5
    dy = shape.y_origin + (max(ys) - min(ys)) * 0.5
    return [
        _polygon_record_to_poly([(x + dx, y + dy) for x, y in poly], metal_rec, W)
        for poly in raw
    ]


def _ring_layout_polygons(shape: Shape, tech: Tech) -> list[Polygon]:
    metal_rec = tech.metals[shape.metal]
    sides = shape.sides
    if sides < 3 or shape.radius <= 0.0:
        return []
    gap_rad = math.radians(abs(shape.spacing))
    radial_w = shape.width / math.cos(math.pi / sides)
    per_side = (2.0 * math.pi - gap_rad) / (sides - 1)
    start = shape.phase + gap_rad * 0.5
    angles = [start + k * per_side for k in range(sides - 1)]
    angles.append(shape.phase - gap_rad * 0.5)

    outer = [(shape.radius * math.cos(a), shape.radius * math.sin(a)) for a in angles]
    inner_r = shape.radius - radial_w
    inner = [(inner_r * math.cos(a), inner_r * math.sin(a)) for a in angles]
    xs = [x for x, _ in outer + inner]
    ys = [y for _, y in outer + inner]
    dx = shape.x_origin + (max(xs) - min(xs)) * 0.5
    dy = shape.y_origin + (max(ys) - min(ys)) * 0.5
    out: list[Polygon] = []
    for i in range(sides - 1):
        out.append(_polygon_record_to_poly(
            [
                (outer[i][0] + dx, outer[i][1] + dy),
                (outer[i + 1][0] + dx, outer[i + 1][1] + dy),
                (inner[i + 1][0] + dx, inner[i + 1][1] + dy),
                (inner[i][0] + dx, inner[i][1] + dy),
            ],
            metal_rec,
            shape.width,
        ))
    return out


def layout_polygons(shape: Shape, tech: Tech) -> list[Polygon]:
    """Return filled layout polygons matching ASITIC's CIF/GDS geometry."""
    if shape.kind == "square":
        return _square_layout_polygons(shape, tech)
    if shape.kind == "mmsquare":
        return _mmsquare_layout_polygons(shape, tech)
    if shape.kind == "transformer_secondary" or shape.kind == "transformer_primary":
        # Polygons already laid out & adjusted; stored on the shape.
        return list(shape.polygons)
    if shape.kind == "polygon_spiral":
        return _polygon_spiral_layout_polygons(shape, tech)
    if shape.kind == "ring":
        return _ring_layout_polygons(shape, tech)
    if shape.kind == "wire" and shape.polygons and len(shape.polygons[0].vertices) >= 2:
        p = shape.polygons[0]
        a, b = p.vertices[0], p.vertices[-1]
        dx = b.x - a.x
        dy = b.y - a.y
        length = math.hypot(dx, dy)
        if length <= 1e-12:
            return []
        nx = -dy / length * p.width * 0.5
        ny = dx / length * p.width * 0.5
        metal_rec = tech.metals[p.metal]
        return [_polygon_record_to_poly(
            [(a.x + nx, a.y + ny), (b.x + nx, b.y + ny),
             (b.x - nx, b.y - ny), (a.x - nx, a.y - ny)],
            metal_rec,
            p.width,
        )]
    return [
        Polygon(vertices=list(p.vertices), metal=p.metal, width=p.width, thickness=p.thickness)
        for p in shape.polygons
    ]


# Geometry builders ------------------------------------------------------


def _resolve_metal(tech: Tech, metal: int | str) -> Metal:
    if isinstance(metal, str):
        return tech.metal_by_name(metal)
    return tech.metals[metal]


def square_spiral(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metal: int | str = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
    phase: float = 0.0,
) -> Shape:
    """Build a square (4-sided) spiral.

    Mirrors the binary's ``cmd_square_build_geometry`` for the simple
    case (no exit metal, no ILEN inner-bound, no 3D mirroring): each
    turn is one closed square loop, with the spiral collapsing
    inward by ``width + spacing`` per turn. The spiral occupies the
    metal layer ``metal`` (index or tech-file name).

    Parameters are in **microns**. ``turns`` may be fractional;
    integer turns each emit four sides, and the fractional remainder
    contributes ``round(4*frac)`` additional sides on a partial turn.

    The trace is generated as a single connected polyline matching
    ASITIC's ``cmd_square_build_geometry`` (decompiled at ``0x08056670``):

    * centerlines are inset by ``W/2`` from the outer ``length × length``
      bounding box, so the outer metal edge sits exactly at ``±L/2``;
    * the entry lead extends the outermost top-side centerline all the
      way to the left edge (``x = -L/2``) so the spiral can be probed
      at the chip boundary;
    * each successive turn shrinks inward by ``pitch = W + S`` and the
      bottom-left corner of one turn connects to the top-left corner
      of the next via the outer-left side, producing a true Archimedean
      spiral instead of nested closed loops;
    * the very last segment is trimmed by ``1.5 × W`` to leave clearance
      for the exit-via attachment, matching the binary's reference output.

    The Python signature follows ASITIC's documented convention:
    ``(x_origin, y_origin)`` is the **lower-left corner** of the
    spiral's outer bounding box, so the spiral metal occupies
    ``[x_origin, x_origin + length] × [y_origin, y_origin + length]``
    in world coords (with ``phase = 0``).

    Verified vertex-for-vertex against the 1999 ASITIC binary's
    ``LISTSEGS`` output (BiCMOS tech, captured under qemu-i386-static).
    """
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    thickness = metal_rec.t

    # Local corner-anchored frame: spiral occupies [0, length] x [0, length].
    # Phase rotates about the lower-left corner; then translate by
    # (x_origin, y_origin) so the lower-left lands at the user's origin —
    # matching ASITIC's "Origin of spiral is the lower-left corner".
    L = length
    W = width
    halfw = W * 0.5
    pitch = W + spacing

    n_full = math.floor(turns)
    frac = turns - n_full
    n_partial = int(round(4 * frac))

    cphase = math.cos(phase)
    sphase = math.sin(phase)

    def to_world(lx: float, ly: float) -> Point:
        rx = lx * cphase - ly * sphase
        ry = lx * sphase + ly * cphase
        return Point(rx + x_origin, ry + y_origin, z)

    # Centerline corners of turn `k` in the local corner-anchored frame.
    # See ASITIC's cmd_square_build_geometry for the corresponding XFillPolygon
    # corner triples (offsets +0x44 / +0x5c / +0x88 / +0xa0 of the polygon
    # record); here we only need the centerline vertex positions.
    def tl(k: int) -> tuple[float, float]:
        return (halfw + max(0, k - 1) * pitch, L - halfw - k * pitch)

    def tr(k: int) -> tuple[float, float]:
        return (L - halfw - k * pitch, L - halfw - k * pitch)

    def br(k: int) -> tuple[float, float]:
        return (L - halfw - k * pitch, halfw + k * pitch)

    def bl(k: int) -> tuple[float, float]:
        return (halfw + k * pitch, halfw + k * pitch)

    def collapsed(k: int) -> bool:
        # Innermost half-side of turn k must be larger than W/2 for the
        # turn to fit; otherwise the spiral has collapsed and we stop.
        return (L * 0.5 - halfw - k * pitch) <= halfw * 0.5

    verts: list[Point] = []

    # Cap the requested turn count at the geometric limit so we don't emit
    # tracks that have collapsed past the spiral centre.
    n_full_emit = min(n_full, max(0, math.floor((L * 0.5 - halfw) / pitch + 1)))

    if n_full_emit == 0 and n_partial == 0:
        return Shape(
            name=name,
            polygons=[],
            width=width,
            length=length,
            spacing=spacing,
            turns=turns,
            sides=4,
            metal=metal_idx,
            x_origin=x_origin,
            y_origin=y_origin,
            phase=phase,
            kind="square",
        )

    # Entry lead: the outermost top-side centerline starts at x = 0 (the
    # left edge of the bounding box) instead of the inner TL corner. This
    # is the ASITIC convention so a probe / pad can attach at the chip
    # boundary without an extra wire.
    verts.append(to_world(0.0, L - halfw))

    last_seg_dir: tuple[float, float] | None = None

    for k in range(n_full_emit):
        if collapsed(k):
            break
        # Top side completes at TR_k.
        verts.append(to_world(*tr(k)))
        # Right side -> BR_k.
        verts.append(to_world(*br(k)))
        # Bottom side -> BL_k.
        verts.append(to_world(*bl(k)))
        # Left side -> TL of the next turn (for chained spiraling). On the
        # last full turn with no fractional remainder, this is the spiral's
        # exit toward where TL_{k+1} would sit.
        nxt_tl = tl(k + 1)
        verts.append(to_world(*nxt_tl))
        last_seg_dir = (nxt_tl[0] - bl(k)[0], nxt_tl[1] - bl(k)[1])

    # Partial turn (top → right → bottom → left, in that order).
    if n_partial > 0 and not collapsed(n_full_emit):
        k = n_full_emit
        partial_corners = [tr(k), br(k), bl(k), tl(k + 1)]
        prev = (verts[-1].x - x_origin, verts[-1].y - y_origin)  # rough check unused
        anchor = tl(k)
        seq = [tr(k), br(k), bl(k), tl(k + 1)]
        for i in range(n_partial):
            verts.append(to_world(*seq[i]))
            if i == 0:
                last_seg_dir = (seq[i][0] - anchor[0], seq[i][1] - anchor[1])
            else:
                last_seg_dir = (seq[i][0] - seq[i - 1][0], seq[i][1] - seq[i - 1][1])
        del partial_corners, prev

    # Exit-lead trim: ASITIC shortens the final M3 centerline by W/2 so
    # the polygon's outer-end lands exactly at the top of the via cell
    # that drops to the exit metal layer. The polygon corners (after
    # chamfering by the bridge) then match the binary's CIF byte-for-byte.
    if len(verts) >= 2 and last_seg_dir is not None:
        dx, dy = last_seg_dir
        seg_len = math.hypot(dx, dy)
        trim = 0.5 * W
        if seg_len > trim:
            f = (seg_len - trim) / seg_len
            p_prev = verts[-2]
            p_end = verts[-1]
            new_x = p_prev.x + (p_end.x - p_prev.x) * f
            new_y = p_prev.y + (p_end.y - p_prev.y) * f
            verts[-1] = Point(new_x, new_y, p_end.z)

    polygons = [
        Polygon(vertices=verts, metal=metal_idx, width=width, thickness=thickness)
    ]

    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        length=length,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
        kind="square",
    )


def polygon_spiral(
    name: str,
    *,
    radius: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    sides: int = 8,
    metal: int | str = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
    phase: float = 0.0,
) -> Shape:
    """Build an ``n``-sided polygon spiral inscribed in ``radius``.

    Mirrors ASITIC's ``cmd_spiral_build_geometry`` (decompiled at
    ``0x08057248``): the spiral is generated as one connected polyline
    that turns by ``2π/sides`` each step while the radius decreases by
    ``pitch_radial / sides`` per side, where
    ``pitch_radial = (W + S) / cos(π/sides)`` is the turn-to-turn radial
    pitch measured along the polygon's perpendicular bisector.

    The bbox is then centered on ``(x_origin, y_origin)`` (per ASITIC's
    ``shape_translate_inplace_xy`` post-build pass) so the user's origin
    parameter ends up at the spiral centre — matching the documented
    behaviour for ``Spiral (NAME:RADIUS:SIDES:…:XORG:YORG)``.
    """
    if sides < 3:
        raise ValueError("polygon spiral needs at least 3 sides")
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    thickness = metal_rec.t

    half_angle = math.pi / sides
    cos_half = math.cos(half_angle)
    # The "radial half-width" — how much the trace extends inward along
    # the radial direction at each vertex of the polygon (the trace face
    # is perpendicular to the bisector of each side, so along the radial
    # direction the half-width is W / (2·cos(π/sides))).
    radial_half_w = width / (2.0 * cos_half)
    pitch_radial = (width + spacing) / cos_half

    n_full = math.floor(turns)
    frac = turns - n_full
    n_partial_sides = int(round(sides * frac))
    total_sides = n_full * sides + n_partial_sides

    cphase = math.cos(phase)
    sphase = math.sin(phase)

    # Build the centerline polyline in a frame anchored at the spiral
    # center, then bbox-center-shift to (x_origin, y_origin) at the end.
    cx_local: list[float] = []
    cy_local: list[float] = []

    # Centerline radius starts one half-width inside the outer-vertex
    # radius and decrements by pitch_radial per turn (= pitch_radial /
    # sides per side). The first vertex sits exactly on the polygon's
    # outer face at phase angle.
    r_centerline = radius - radial_half_w
    pitch_per_side = pitch_radial / sides

    if r_centerline <= width * 0.5 or total_sides < 1:
        return Shape(
            name=name, polygons=[], width=width, length=radius * 2.0, spacing=spacing,
            turns=turns, sides=sides, metal=metal_idx,
            x_origin=x_origin, y_origin=y_origin, phase=phase,
            kind="polygon_spiral",
        )

    cx_local.append(r_centerline * math.cos(phase))
    cy_local.append(r_centerline * math.sin(phase))
    for k in range(total_sides):
        r_centerline = r_centerline - pitch_per_side
        if r_centerline <= width * 0.5:
            break
        theta = phase + 2.0 * math.pi * (k + 1) / sides
        cx_local.append(r_centerline * math.cos(theta))
        cy_local.append(r_centerline * math.sin(theta))

    # ASITIC's ``shape_translate_inplace_xy`` for polygon spirals shifts
    # the centered polyline so the spiral's first centerline vertex lands
    # at world ``(XORG + 2R - radial_half_w - pitch_radial/4,
    #            YORG + R - pitch_radial/2)``. Equivalently, the spiral's
    # geometric centre lands at ``(XORG + R - pitch_radial/4,
    #                              YORG + R - pitch_radial/2)``.
    #
    # This formula was reverse-engineered from the binary's LISTSEGS
    # output (sp_r80, sp_r100, sp_r120) and matches all three cases
    # vertex-for-vertex.
    dx = x_origin + radius - pitch_radial * 0.25
    dy = y_origin + radius - pitch_radial * 0.5

    verts: list[Point] = [
        Point(x + dx, y + dy, z)
        for x, y in zip(cx_local, cy_local, strict=True)
    ]

    polygons = [
        Polygon(vertices=verts, metal=metal_idx, width=width, thickness=thickness)
    ]
    # phase rotation is already baked into the cos/sin calls above.
    _ = (cphase, sphase)

    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        length=radius * 2.0,
        spacing=spacing,
        turns=turns,
        sides=sides,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
        radius=radius,
        kind="polygon_spiral",
    )


def wire(
    name: str,
    *,
    length: float,
    width: float,
    tech: Tech,
    metal: int | str = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
    phase: float = 0.0,
) -> Shape:
    """Build a single straight wire of length ``length`` on ``metal``.

    Matches ASITIC's ``W NAME=…:LEN=…:WID=…:METAL=…:XORG=…:YORG=…``
    convention: ``(x_origin, y_origin)`` is the **lower-left corner**
    of the wire's bounding box, so the metal occupies
    ``[x_origin, x_origin + length] × [y_origin, y_origin + width]``
    when ``phase=0``. The centerline runs along ``y = y_origin + W/2``.
    """
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    cphase = math.cos(phase)
    sphase = math.sin(phase)

    # Local frame: wire occupies [0, length] × [0, width]; centerline
    # at y = width/2. Apply phase rotation about the lower-left corner,
    # then translate by (x_origin, y_origin).
    halfw = width * 0.5

    def to_world(lx: float, ly: float) -> Point:
        rx = lx * cphase - ly * sphase
        ry = lx * sphase + ly * cphase
        return Point(rx + x_origin, ry + y_origin, z)

    a = to_world(0.0, halfw)
    b = to_world(length, halfw)
    polygons = [
        Polygon(vertices=[a, b], metal=metal_idx, width=width, thickness=metal_rec.t)
    ]
    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        length=length,
        spacing=0.0,
        turns=1.0,
        sides=1,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
        kind="wire",
    )


def via(
    name: str,
    *,
    tech: Tech,
    via_index: int = 0,
    nx: int = 1,
    ny: int = 1,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Build a via cluster of size ``nx`` × ``ny`` at ``(x, y)``.

    Mirrors ``cmd_via_build_geometry`` (``asitic_repl.c:3934``).
    The via record references both metal layers (``top``, ``bottom``)
    via the via-table entry at ``via_index``.
    """
    if via_index < 0 or via_index >= len(tech.vias):
        raise ValueError(f"no via at index {via_index}")
    v = tech.vias[via_index]
    top_metal = tech.metals[v.top]
    bot_metal = tech.metals[v.bottom]
    z_top = top_metal.d + top_metal.t * 0.5
    z_bot = bot_metal.d + bot_metal.t * 0.5
    # A via is represented as a single z-direction segment between
    # the two metal layers' centres. Width × thickness encode the
    # contact dimensions.
    a = Point(x_origin, y_origin, z_bot)
    b = Point(x_origin, y_origin, z_top)
    metal_idx = len(tech.metals) + via_index  # via "metal" index continues past metals
    poly = Polygon(
        vertices=[a, b],
        metal=metal_idx,
        width=v.width * nx + v.space * (nx - 1),
        thickness=v.width * ny + v.space * (ny - 1),
    )
    return Shape(
        name=name,
        polygons=[poly],
        width=v.width,
        length=0.0,
        spacing=v.space,
        turns=1.0,
        sides=1,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="via",
    )


def ring(
    name: str,
    *,
    radius: float,
    width: float,
    gap: float = 0.0,
    sides: int = 32,
    tech: Tech,
    metal: int | str = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
    phase: float = 0.0,
) -> Shape:
    """Build a single closed-ring loop (``Ring``, command id 22).

    A ring is a polygon spiral with exactly one turn — implemented
    as a thin wrapper for clarity, since the binary's REPL exposes
    ``Ring`` as a separate command.
    """
    sh = polygon_spiral(
        name,
        radius=radius,
        width=width,
        spacing=0.0,
        turns=1.0,
        tech=tech,
        sides=sides,
        metal=metal,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
    )
    sh.kind = "ring"
    sh.spacing = gap
    sh.radius = radius
    return sh


def transformer(
    name: str,
    *,
    length: float | None = None,
    width: float | None = None,
    spacing: float | None = None,
    turns: float | None = None,
    primary_length: float | None = None,
    primary_width: float | None = None,
    primary_spacing: float | None = None,
    primary_turns: float | None = None,
    secondary_length: float | None = None,
    secondary_width: float | None = None,
    secondary_spacing: float | None = None,
    secondary_turns: float | None = None,
    tech: Tech,
    metal: int | str | None = None,
    exit_metal: int | str | None = None,
    metal_primary: int | str | None = None,
    metal_secondary: int | str | None = None,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
    which: str = "primary",
) -> Shape:
    """Build a planar two-coil transformer (``Trans``).

    Mirrors ``cmd_trans_build_geometry`` (decomp ``0x080576d4``):
    two square spirals on the same metal (METAL), interleaved by a
    double-pitch + a half-pitch offset so the secondary's tracks
    fit between the primary's. The secondary is built with a flip
    in both axes via ``cmd_flipv_apply`` + ``cmd_fliph_apply``.

    For the canonical ``TRANS PNAME=TP:SNAME=TS:LEN=L:W=W:S=S:N=N``
    case both coils have identical dimensions. The primary's
    internal lower-left corner sits at::

        (XORG + (W + S), YORG + (2W + S))

    and each coil uses an effective spacing of ``W + 2·S`` so the
    inter-turn pitch is ``2·(W + S)`` — leaving room for the
    secondary's interleaved turns.

    The C builder leaves both coils linked and ``CIFSAVE``
    addresses each by name. Use ``which="primary"`` (default) or
    ``which="secondary"`` to pick the coil to materialise.

    Both legacy positional kwargs (``length``, ``width``,
    ``spacing``, ``turns``) and the test-harness primary/secondary
    pair are accepted; missing fields default to the corresponding
    ``primary_*`` value or vice versa.
    """
    # Normalise kwargs: prefer primary_* over generic, fall back to
    # the other side if missing.
    L = primary_length if primary_length is not None else (
        length if length is not None else secondary_length
    )
    W = primary_width if primary_width is not None else (
        width if width is not None else secondary_width
    )
    S = primary_spacing if primary_spacing is not None else (
        spacing if spacing is not None else secondary_spacing
    )
    N = primary_turns if primary_turns is not None else (
        turns if turns is not None else secondary_turns
    )
    if L is None or W is None or S is None or N is None:
        raise ValueError("transformer: must specify length/width/spacing/turns")

    # Metal resolution: prefer 'metal' over the legacy 'metal_primary'.
    coil_metal = metal if metal is not None else metal_primary
    if coil_metal is None:
        raise ValueError("transformer: must specify metal=...")
    coil_idx = _resolve_metal(tech, coil_metal).index
    exit_idx: int | None = None
    if exit_metal is not None:
        exit_idx = _resolve_metal(tech, exit_metal).index
    elif metal_secondary is not None:
        # Legacy 'metal_secondary' was used for the secondary's metal
        # in the earlier (incorrect) port. The C uses ONE metal for
        # both coils with a separate EXIT routing layer. If a caller
        # supplies metal_secondary we assume they meant exit_metal.
        exit_idx = _resolve_metal(tech, metal_secondary).index

    # Both coils share dimensions in the canonical TRANS form, but
    # are placed at different internal origins so their tracks
    # interleave with a single (W + S) gap. Decoded from gold
    # trans_200x8x3x3_m3_m2_*.cif:
    #   primary  internal LL = (XORG + W + S, YORG + 2W + S) = (11, 19)
    #   secondary internal LL = (XORG,        YORG + W)       = (0,  8)
    # Each coil uses spacing = W + 2S so its inter-turn pitch is
    # 2*(W+S) — leaving room for the other coil's interleaved turns.
    primary_x = x_origin + (W + S)
    primary_y = y_origin + (2 * W + S)
    secondary_x = x_origin
    secondary_y = y_origin + W
    coil_spacing = W + 2 * S  # so pitch = W + (W+2S) = 2*(W+S)

    coil_x = primary_x if which == "primary" else secondary_x
    coil_y = primary_y if which == "primary" else secondary_y

    base_sp = square_spiral(
        f"{name}_{which}",
        length=L, width=W, spacing=coil_spacing, turns=N,
        tech=tech, metal=coil_idx,
        x_origin=coil_x, y_origin=coil_y,
    )
    base_shape = Shape(
        name=name, polygons=base_sp.polygons,
        width=W, length=L, spacing=coil_spacing, turns=N, sides=4,
        metal=coil_idx, exit_metal=exit_idx,
        x_origin=coil_x, y_origin=coil_y, kind="square",
    )

    # The C cmd_trans_build_geometry applies a per-coil entry-lead
    # extension. Decoded from asitic_repl.c:3879-3893:
    #
    #     dVar2 = primary.W + (secondary.S' - primary.W) / 2
    #           = (W + S') / 2 = pitch_post_setup / 2 = (W + S)
    #     primary.first_polygon[start corners].x   -= dVar2
    #     secondary.first_polygon[start corners].x += dVar2
    #
    # where ``S'`` is the trans-modified spacing (= W + 2*S; see
    # cmd_trans_create_new at asitic_repl.c:11171). After
    # simplification ``dVar2 = W + S = pitch`` (single-coil pitch).
    # Effect: each coil's outermost top side gets extended outward
    # by pitch on its outer-end (primary on the left, secondary on
    # the right — by symmetry of the double-flip).
    pitch = W + S

    if which == "primary":
        primary_polys = layout_polygons(base_shape, tech)
        primary_polys = _trans_extend_primary_lead(primary_polys, pitch)
        return Shape(
            name=name, polygons=primary_polys,
            width=W, length=L, spacing=coil_spacing, turns=N, sides=4,
            metal=coil_idx, exit_metal=exit_idx,
            x_origin=coil_x, y_origin=coil_y,
            kind="transformer_primary",
        )

    if which != "secondary":
        raise ValueError(f"which must be 'primary' or 'secondary', not {which!r}")

    # Lay out the secondary's basic spiral, then mirror about the
    # SPIRAL's own bbox centerlines (NOT the post-access-routing
    # bbox, which includes the M2 lead extension whose post-flip
    # direction we want to flip too). The spiral occupies the
    # known box ``[coil_x, coil_x+L] × [coil_y, coil_y+L]``.
    base_polys = layout_polygons(base_shape, tech)
    spiral_y_axis = coil_y + (coil_y + L)
    spiral_x_axis = coil_x + (coil_x + L)
    secondary_polys = _polygon_flipv_apply(
        _polygon_fliph_apply(base_polys, y_axis=spiral_y_axis),
        x_axis=spiral_x_axis,
    )
    # The secondary's lead extension is on the post-flip RIGHT end
    # (which was the LEFT end pre-flip; the +dVar2 shift in the C
    # symmetrically extends the secondary outward on its outer end).
    secondary_polys = _trans_extend_secondary_lead(secondary_polys, pitch)

    return Shape(
        name=name, polygons=secondary_polys,
        width=W, length=L, spacing=coil_spacing, turns=N, sides=4,
        metal=coil_idx, exit_metal=exit_idx,
        x_origin=coil_x, y_origin=coil_y,
        kind="transformer_secondary",
    )


def _trans_extend_primary_lead(
    polys: list[Polygon], pitch: float,
) -> list[Polygon]:
    """Extend the primary's outermost top side leftward by ``pitch``.

    Mirrors cmd_trans_build_geometry's primary.first_polygon shift
    (asitic_repl.c:3886-3893). The first polygon emitted by
    ``_square_layout_polygons`` is the outermost top side; its
    "start" corners (left-end outer-y, left-end inner-y, and the
    centerline-start) need to shift left by pitch = W + S.
    """
    if not polys:
        return polys
    out: list[Polygon] = []
    first = polys[0]
    # Find the leftmost x of the first polygon — the "start" corners
    # are the two vertices at min(x).
    xs = [v.x for v in first.vertices]
    xmin = min(xs)
    new_verts = [
        Point(v.x - pitch if abs(v.x - xmin) < 1e-9 else v.x, v.y, v.z)
        for v in first.vertices
    ]
    out.append(Polygon(vertices=new_verts, metal=first.metal,
                       width=first.width, thickness=first.thickness))
    out.extend(polys[1:])
    return out


def _trans_extend_secondary_lead(
    polys: list[Polygon], pitch: float,
) -> list[Polygon]:
    """Extend the secondary's first (post-flip) polygon outward.

    After fliph+flipv the secondary's first polygon is what was the
    last pre-flip — its "start corners" land at the post-flip right
    end. Mirroring the +dVar2 shift in cmd_trans_build_geometry, we
    extend the rightmost x by pitch.
    """
    if not polys:
        return polys
    out: list[Polygon] = []
    first = polys[0]
    xs = [v.x for v in first.vertices]
    xmax = max(xs)
    new_verts = [
        Point(v.x + pitch if abs(v.x - xmax) < 1e-9 else v.x, v.y, v.z)
        for v in first.vertices
    ]
    out.append(Polygon(vertices=new_verts, metal=first.metal,
                       width=first.width, thickness=first.thickness))
    out.extend(polys[1:])
    return out


def symmetric_square(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metal: int | str = 0,
    bridge_metal: int | str | None = None,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Build a symmetric centre-tapped square spiral (``SymSq``).

    A SymSq has two interleaved square coils joined at the centre.
    This implementation builds it as one inductor whose polygon list
    contains both arms; the centre-tap routing is left implicit (no
    explicit bridge segment is emitted).

    Mirrors ``cmd_symsq_build_geometry`` (``asitic_repl.c:0x08059854``).
    """
    if bridge_metal is None:
        bridge_metal = metal
    arm_a = square_spiral(
        f"{name}_a",
        length=length * 0.5,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal,
        x_origin=x_origin - length * 0.25,
        y_origin=y_origin,
    )
    arm_b = square_spiral(
        f"{name}_b",
        length=length * 0.5,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal,
        x_origin=x_origin + length * 0.25,
        y_origin=y_origin,
        phase=math.pi,
    )
    return Shape(
        name=name,
        polygons=arm_a.polygons + arm_b.polygons,
        width=width,
        length=length,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=arm_a.metal,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="symmetric_square",
    )


def capacitor(
    name: str,
    *,
    length: float,
    width: float,
    metal_top: int | str,
    metal_bottom: int | str,
    tech: Tech,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Build a metal-insulator-metal (MIM) capacitor (``Capacitor``).

    Two stacked rectangles on different metal layers. The geometric
    overlap × dielectric thickness gives the MIM capacitance; we
    emit both rectangles as separate polygons so the caller can run
    geometry-only analyses (area, footprint).

    Mirrors ``cmd_capacitor_build_geometry`` in the original.
    """
    top = _resolve_metal(tech, metal_top)
    bot = _resolve_metal(tech, metal_bottom)
    z_top = top.d + top.t * 0.5
    z_bot = bot.d + bot.t * 0.5

    def rect(metal_idx: int, z: float, thickness: float) -> Polygon:
        return Polygon(
            vertices=[
                Point(x_origin, y_origin, z),
                Point(x_origin + length, y_origin, z),
                Point(x_origin + length, y_origin + width, z),
                Point(x_origin, y_origin + width, z),
                Point(x_origin, y_origin, z),
            ],
            metal=metal_idx,
            width=width,
            thickness=thickness,
        )

    polygons = [
        rect(top.index, z_top, top.t),
        rect(bot.index, z_bot, bot.t),
    ]
    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        length=length,
        spacing=0.0,
        turns=1.0,
        sides=4,
        metal=top.index,
        exit_metal=bot.index,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="capacitor",
    )


def symmetric_polygon(
    name: str,
    *,
    radius: float,
    width: float,
    spacing: float,
    turns: float,
    sides: int = 8,
    tech: Tech,
    metal: int | str = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Symmetric centre-tapped polygon spiral (``SymPoly``, case 17).

    Two interleaved polygon spirals with mirrored entry points; the
    centre tap is implicit (no explicit bridge segment is emitted).
    Mirrors ``cmd_sympoly_build_geometry``.
    """
    arm_a = polygon_spiral(
        f"{name}_a",
        radius=radius * 0.5,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=sides,
        tech=tech,
        metal=metal,
        x_origin=x_origin - radius * 0.25,
        y_origin=y_origin,
    )
    arm_b = polygon_spiral(
        f"{name}_b",
        radius=radius * 0.5,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=sides,
        tech=tech,
        metal=metal,
        x_origin=x_origin + radius * 0.25,
        y_origin=y_origin,
        phase=math.pi,
    )
    return Shape(
        name=name,
        polygons=arm_a.polygons + arm_b.polygons,
        width=width,
        length=radius * 2.0,
        spacing=spacing,
        turns=turns,
        sides=sides,
        metal=arm_a.metal,
        x_origin=x_origin,
        y_origin=y_origin,
        radius=radius,
        kind="symmetric_polygon",
    )


def multi_metal_square(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metals: list[int | str] | None = None,
    metal: int | str | None = None,
    exit_metal: int | str | None = None,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Multi-metal series square inductor (``MMSquare``).

    Mirrors ``cmd_mmsquare_build_geometry`` (decomp ``0x0805af5c``):
    builds a square spiral on the top metal, then a Y-mirrored,
    list-reversed copy on each lower metal layer down to and
    including ``exit_metal``. Adjacent layers connect via implicit
    vias at the inner-end of one and the outer-start of the next,
    boosting L for a given footprint by re-using area.

    Two equivalent calling conventions are supported:

    * ``metal="m3", exit_metal="m2"`` — matches the C ASITIC
      ``MMSQ NAME=...:METAL=m3:EXIT=m2`` form. The Python uses
      every metal layer from ``metal`` down to ``exit_metal``
      inclusive.
    * ``metals=[m3, m2]`` — backward-compatible explicit list.

    The basic square-spiral on the top metal is built with
    ``cmd_square_build_geometry``'s exit-routing branch suppressed
    (the C sets ``shape.exit_metal = -1`` before calling
    ``cmd_square_build_geometry``). The full per-layer flip cascade
    is then applied by :func:`_mmsquare_layout_polygons`.
    """
    if metals is not None:
        resolved = [_resolve_metal(tech, m).index for m in metals]
        if len(resolved) < 1:
            raise ValueError("at least one metal layer required")
        top_idx = max(resolved)
        bot_idx = min(resolved)
    elif metal is not None and exit_metal is not None:
        top_idx = _resolve_metal(tech, metal).index
        bot_idx = _resolve_metal(tech, exit_metal).index
    elif metal is not None:
        top_idx = _resolve_metal(tech, metal).index
        bot_idx = top_idx
    else:
        raise ValueError("must pass either metals=[...] or metal=...")

    base = square_spiral(
        f"{name}_top",
        length=length, width=width, spacing=spacing, turns=turns,
        tech=tech, metal=top_idx,
        x_origin=x_origin, y_origin=y_origin,
    )
    return Shape(
        name=name,
        polygons=base.polygons,
        width=width,
        length=length,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=top_idx,
        exit_metal=bot_idx if bot_idx != top_idx else None,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="mmsquare",
    )


def transformer_3d(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metal_top: int | str,
    metal_bottom: int | str,
    via_index: int = 0,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """3-D non-planar mirror-stacked transformer (``3DTrans``).

    Two co-axial square spirals on different metal layers, vertically
    aligned and connected by a via at the centre. The two coils
    share the same chip footprint, so there's no horizontal
    separation as in :func:`transformer`.

    Mirrors the simple-case path of ``cmd_3dtrans_build_geometry``
    (``asitic_repl.c:0x08057d40``). The full binary version supports
    centre-tapped variants and multi-via stacks; this implementation
    is the planar-mirror form.
    """
    primary = square_spiral(
        f"{name}_top",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal_top,
        x_origin=x_origin,
        y_origin=y_origin,
    )
    secondary = square_spiral(
        f"{name}_bot",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal_bottom,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=math.pi,  # mirror so currents oppose at the via
    )
    via_segment = via(
        f"{name}_via",
        tech=tech,
        via_index=via_index,
        nx=1,
        ny=1,
        x_origin=x_origin,
        y_origin=y_origin,
    )
    return Shape(
        name=name,
        polygons=primary.polygons + secondary.polygons + via_segment.polygons,
        width=width,
        length=length,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=primary.metal,
        exit_metal=secondary.metal,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="transformer_3d",
    )


def balun(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metal: int | str = 0,
    metal2: int | str | None = None,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Build a planar balun (``Balun``, command id 5).

    Two stacked counter-wound square coils, typically on adjacent
    metal layers, used for differential-to-single-ended conversion.
    Mirrors ``cmd_balun_build_geometry`` in the original.
    """
    metal2_resolved = metal if metal2 is None else metal2
    coil_a = square_spiral(
        f"{name}_a",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal,
        x_origin=x_origin,
        y_origin=y_origin,
    )
    coil_b = square_spiral(
        f"{name}_b",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal2_resolved,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=math.pi,
    )
    return Shape(
        name=name,
        polygons=coil_a.polygons + coil_b.polygons,
        width=width,
        length=length,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=coil_a.metal,
        exit_metal=coil_b.metal,
        x_origin=x_origin,
        y_origin=y_origin,
        kind="balun",
    )
