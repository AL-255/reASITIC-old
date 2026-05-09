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
    spacing: float = 0.0
    turns: float = 0.0
    sides: int = 4
    metal: int = 0
    exit_metal: int | None = None
    x_origin: float = 0.0
    y_origin: float = 0.0
    orientation: int = 0  # 1 == cw, -1 == ccw, 0 == as-built
    phase: float = 0.0

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
            spacing=self.spacing,
            turns=self.turns,
            sides=self.sides,
            metal=self.metal,
            exit_metal=self.exit_metal,
            x_origin=self.x_origin + dx_origin,
            y_origin=self.y_origin + dy_origin,
            orientation=self.orientation,
            phase=self.phase,
        )


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

    Parameters are in **microns**. ``turns`` may be fractional —
    it controls how many quarter-segments are emitted on the
    innermost partial turn.
    """
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    thickness = metal_rec.t

    polygons: list[Polygon] = []

    # Outer half-side starts at length/2; each successive turn shrinks
    # by (width + spacing).
    outer_half = length * 0.5
    pitch = width + spacing

    # Number of full turns and a fractional remainder (0..1)
    n_full = math.floor(turns)
    frac = turns - n_full

    # Phase rotates the spiral in-plane by `phase` radians; for square
    # the entry edge is normally on the right (-x) side of the outer ring.
    cphase = math.cos(phase)
    sphase = math.sin(phase)

    def rot(px: float, py: float) -> tuple[float, float]:
        return (px * cphase - py * sphase, px * sphase + py * cphase)

    def add_loop(half: float, partial_turn: float) -> bool:
        """Append a closed loop (or partial loop) at half-side ``half``.

        Returns True if added; False if the inner radius collapsed.
        """
        if half <= width * 0.5:
            return False
        # Vertices of a square loop, traced clockwise starting at the
        # right side. Each side is one polygon segment.
        # Right, top, left, bottom — corner offsets:
        corners = [
            (+half, -half),  # bottom-right
            (+half, +half),  # top-right
            (-half, +half),  # top-left
            (-half, -half),  # bottom-left
            (+half, -half),  # close
        ]
        if partial_turn >= 1.0 - 1e-12:
            verts = corners
        else:
            # Use only the leading `4 * partial_turn` segments
            n_seg = max(1, round(4 * partial_turn))
            verts = corners[: n_seg + 1]
        pts = []
        for cx, cy in verts:
            rx, ry = rot(cx + x_origin, cy + y_origin)
            pts.append(Point(rx, ry, z))
        polygons.append(
            Polygon(vertices=pts, metal=metal_idx, width=width, thickness=thickness)
        )
        return True

    half = outer_half
    for _ in range(n_full):
        if not add_loop(half, 1.0):
            break
        half -= pitch
    if frac > 0:
        add_loop(half, frac)

    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
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

    Each turn is a regular ``sides``-gon; consecutive turns are
    offset radially by ``width + spacing`` measured along the
    perpendicular bisector of each side.
    """
    if sides < 3:
        raise ValueError("polygon spiral needs at least 3 sides")
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    thickness = metal_rec.t

    polygons: list[Polygon] = []

    n_full = math.floor(turns)
    frac = turns - n_full
    pitch_radial = (width + spacing) / math.cos(math.pi / sides)

    def add_loop(r: float, partial_turn: float) -> bool:
        if r <= width * 0.5:
            return False
        # Vertex positions: regular polygon centered at origin, first
        # vertex at angle ``phase``.
        n_full_sides = sides
        verts: list[Point] = []
        n_seg = (
            n_full_sides
            if partial_turn >= 1.0 - 1e-12
            else max(1, round(n_full_sides * partial_turn))
        )
        for k in range(n_seg + 1):
            theta = phase + 2.0 * math.pi * k / sides
            vx = x_origin + r * math.cos(theta)
            vy = y_origin + r * math.sin(theta)
            verts.append(Point(vx, vy, z))
        polygons.append(
            Polygon(vertices=verts, metal=metal_idx, width=width, thickness=thickness)
        )
        return True

    r = radius
    for _ in range(n_full):
        if not add_loop(r, 1.0):
            break
        r -= pitch_radial
    if frac > 0:
        add_loop(r, frac)

    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=sides,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
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
    """Build a single straight wire of length ``length`` on ``metal``."""
    metal_rec = _resolve_metal(tech, metal)
    metal_idx = metal_rec.index
    z = metal_rec.d + metal_rec.t * 0.5
    cphase = math.cos(phase)
    sphase = math.sin(phase)

    half = length * 0.5
    a = Point(x_origin - half * cphase, y_origin - half * sphase, z)
    b = Point(x_origin + half * cphase, y_origin + half * sphase, z)
    polygons = [
        Polygon(vertices=[a, b], metal=metal_idx, width=width, thickness=metal_rec.t)
    ]
    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        spacing=0.0,
        turns=1.0,
        sides=1,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
        phase=phase,
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
        spacing=v.space,
        turns=1.0,
        sides=1,
        metal=metal_idx,
        x_origin=x_origin,
        y_origin=y_origin,
    )


def ring(
    name: str,
    *,
    radius: float,
    width: float,
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
    return polygon_spiral(
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


def transformer(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metal_primary: int | str = 0,
    metal_secondary: int | str | None = None,
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Build a planar two-coil transformer (``Trans``).

    Mirrors the simple-case behaviour of ``cmd_trans_build_geometry``
    (``asitic_repl.c:3861``): two interleaved square spirals, the
    second flipped horizontally and vertically. Returns a single
    Shape whose polygon list contains both coils.
    """
    primary = square_spiral(
        f"{name}_pri",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=metal_primary,
        x_origin=x_origin,
        y_origin=y_origin,
    )
    secondary_metal = (
        metal_secondary if metal_secondary is not None else metal_primary
    )
    secondary = square_spiral(
        f"{name}_sec",
        length=length,
        width=width,
        spacing=spacing,
        turns=turns,
        tech=tech,
        metal=secondary_metal,
        x_origin=x_origin + length + spacing * 2.0,
        y_origin=y_origin,
        phase=math.pi,  # rotate 180° so currents oppose
    )
    return Shape(
        name=name,
        polygons=primary.polygons + secondary.polygons,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=primary.metal,
        exit_metal=secondary.metal,
        x_origin=x_origin,
        y_origin=y_origin,
    )


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
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=arm_a.metal,
        x_origin=x_origin,
        y_origin=y_origin,
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

    half_x = length * 0.5
    half_y = width * 0.5

    def rect(metal_idx: int, z: float, thickness: float) -> Polygon:
        return Polygon(
            vertices=[
                Point(x_origin - half_x, y_origin - half_y, z),
                Point(x_origin + half_x, y_origin - half_y, z),
                Point(x_origin + half_x, y_origin + half_y, z),
                Point(x_origin - half_x, y_origin + half_y, z),
                Point(x_origin - half_x, y_origin - half_y, z),
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
        spacing=0.0,
        turns=1.0,
        sides=4,
        metal=top.index,
        exit_metal=bot.index,
        x_origin=x_origin,
        y_origin=y_origin,
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
        spacing=spacing,
        turns=turns,
        sides=sides,
        metal=arm_a.metal,
        x_origin=x_origin,
        y_origin=y_origin,
    )


def multi_metal_square(
    name: str,
    *,
    length: float,
    width: float,
    spacing: float,
    turns: float,
    tech: Tech,
    metals: list[int | str],
    x_origin: float = 0.0,
    y_origin: float = 0.0,
) -> Shape:
    """Multi-metal series square inductor (``MMSquare``, case 18).

    Stacks ``len(metals)`` square spirals (each on a different metal
    layer), connected in series by implicit vias. Boosts L for a
    given footprint by reusing area on multiple layers.

    Mirrors ``cmd_mmsq_build_geometry``.
    """
    if not metals:
        raise ValueError("at least one metal layer required")
    polygons: list[Polygon] = []
    metal_indices: list[int] = []
    for i, m in enumerate(metals):
        sp = square_spiral(
            f"{name}_{i}",
            length=length,
            width=width,
            spacing=spacing,
            turns=turns,
            tech=tech,
            metal=m,
            x_origin=x_origin,
            y_origin=y_origin,
        )
        polygons.extend(sp.polygons)
        metal_indices.append(sp.metal)
    return Shape(
        name=name,
        polygons=polygons,
        width=width,
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=metal_indices[0],
        exit_metal=metal_indices[-1] if len(metal_indices) > 1 else None,
        x_origin=x_origin,
        y_origin=y_origin,
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
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=primary.metal,
        exit_metal=secondary.metal,
        x_origin=x_origin,
        y_origin=y_origin,
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
        spacing=spacing,
        turns=turns,
        sides=4,
        metal=coil_a.metal,
        exit_metal=coil_b.metal,
        x_origin=x_origin,
        y_origin=y_origin,
    )
