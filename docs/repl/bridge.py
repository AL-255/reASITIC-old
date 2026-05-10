"""In-browser REPL bridge between the JS UI and the reasitic library.

The JS side:
  * loads a .tek tech file and calls ``load_tech(text)`` once;
  * calls ``build_shape(spec)`` whenever the user changes parameters;
  * calls ``analyze_*`` and ``export_*`` for the action buttons.

Each public function returns a plain dict / str so PyProxy.toJs can hand
it to JavaScript without surprises.
"""

from __future__ import annotations

import io
import math
import sys
import traceback

import reasitic
from reasitic.exports.spice import write_spice_subckt
from reasitic.network import (
    linear_freqs,
    pi_model_at_freq,
    self_resonance,
    two_port_sweep,
    write_touchstone,
)


# Global state — single tech and single shape at a time keeps the UI simple.
STATE: dict = {"tech": None, "shape": None, "tech_text": ""}


def load_tech(text: str) -> dict:
    """Parse a .tek file from raw text and stash it in module state."""
    tech = reasitic.parse_tech(text)
    STATE["tech"] = tech
    STATE["tech_text"] = text
    metals = [
        {"index": m.index, "name": m.name or f"m{m.index}", "color": m.color, "t": m.t, "rsh": m.rsh}
        for m in tech.metals
    ]
    vias = [
        {"index": i, "name": v.name or f"via{i}", "top": v.top, "bottom": v.bottom,
         "width": v.width, "space": v.space}
        for i, v in enumerate(tech.vias)
    ]
    return {
        "metals": metals,
        "vias": vias,
        "n_layers": len(tech.layers),
        "n_vias": len(tech.vias),
        "chip": {"chipx": tech.chip.chipx, "chipy": tech.chip.chipy},
    }


def _resolve_metal_color(tech, metal_idx: int) -> tuple[str, str]:
    """(name, color) for a metal index."""
    for m in tech.metals:
        if m.index == metal_idx:
            return (m.name or f"m{metal_idx}", m.color or "white")
    return (f"m{metal_idx}", "white")


def _perpendicular(p_start, p_end) -> tuple[float, float]:
    """Unit perpendicular to the segment ``p_start → p_end`` (rotated
    90° CCW). Returns ``(0, 0)`` for zero-length segments."""
    dx = p_end.x - p_start.x
    dy = p_end.y - p_start.y
    L = math.hypot(dx, dy)
    if L == 0:
        return (0.0, 0.0)
    return (-dy / L, dx / L)


def _miter_offset(perp_in, perp_out) -> tuple[float, float]:
    """Offset vector at a centerline corner so a stroke of half-width 1
    hits the miter point — the intersection of the two perpendicular-
    offset lines of the incoming and outgoing segments.

    Closed-form: ``(perp_in + perp_out) / (1 + perp_in · perp_out)``.
    """
    sx = perp_in[0] + perp_out[0]
    sy = perp_in[1] + perp_out[1]
    denom = 1.0 + perp_in[0] * perp_out[0] + perp_in[1] * perp_out[1]
    if abs(denom) < 1e-9:
        # 180° reversal: treat as a butt cap (no extension).
        return perp_in
    return (sx / denom, sy / denom)


def _miter_corners(
    prev_a, a, b, next_b, width: float
) -> list[list[float]]:
    """Return the 4 corners of a segment's fat-trace polygon using
    miter joins at each end.

    For an interior segment of a polyline, the miter point at each end
    is the intersection of the perpendicular ±W/2 offset lines of the
    two adjacent segments. For 90° bends this reduces to the chamfered-
    corner formula; for arbitrary bend angles (n-gon spirals, oblique
    transitions) the miter naturally produces the exact ASITIC outer-
    vertex / inner-vertex polygon corners.

    Pass ``prev_a = None`` for the first segment of an open polyline
    and ``next_b = None`` for the last; the corresponding end uses a
    butt cap (perpendicular offset only).
    """
    perp_ab = _perpendicular(a, b)
    if perp_ab == (0.0, 0.0):
        return []
    half_w = width * 0.5

    if prev_a is None:
        miter_a = perp_ab
    else:
        miter_a = _miter_offset(_perpendicular(prev_a, a), perp_ab)

    if next_b is None:
        miter_b = perp_ab
    else:
        miter_b = _miter_offset(perp_ab, _perpendicular(b, next_b))

    return [
        [a.x + miter_a[0] * half_w, a.y + miter_a[1] * half_w],  # v1: outer-start
        [b.x + miter_b[0] * half_w, b.y + miter_b[1] * half_w],  # v2: outer-end
        [b.x - miter_b[0] * half_w, b.y - miter_b[1] * half_w],  # v3: inner-end
        [a.x - miter_a[0] * half_w, a.y - miter_a[1] * half_w],  # v4: inner-start
    ]


def _shape_to_payload(shape) -> dict:
    """Convert a Shape into a JSON-friendly payload for draw.js.

    The payload carries two parallel descriptions of each metal trace:

    * ``points`` per polygon — the ASITIC-style centerline polyline
      (used for fat-stroke rendering with miter joins).
    * ``segment_polys`` per polygon — one filled 4-corner rectangle
      per centerline segment, computed by offsetting the centerline
      ±W/2 perpendicular. This matches the CIF's per-side ``P``
      records and is what draw.js uses to render the metal layer.
    """
    tech = STATE["tech"]
    polys = []
    for p in shape.polygons:
        name, color = _resolve_metal_color(tech, p.metal)
        verts = list(p.vertices)
        is_closed = (
            len(verts) >= 3
            and abs(verts[0].x - verts[-1].x) < 1e-9
            and abs(verts[0].y - verts[-1].y) < 1e-9
        )
        # CAPACITOR and similar "filled" shapes use a closed polygon
        # whose vertices ARE the metal boundary, with the polygon's
        # ``width`` field set to the full plate dimension (matching the
        # bounding-box span). Spirals / rings store the trace width,
        # which is small compared to the bbox. Use that ratio to
        # discriminate: when ``polygon.width`` rivals the bbox extent
        # we emit the vertex list directly as a single filled polygon.
        if is_closed and verts:
            bx = max(v.x for v in verts) - min(v.x for v in verts)
            by = max(v.y for v in verts) - min(v.y for v in verts)
            min_bbox = min(bx, by)
        else:
            min_bbox = 0.0
        # Filled shape: closed polygon whose width covers the full
        # short-axis extent (capacitor plates set ``width = WID``).
        # Spirals and rings have ``width`` ≪ min_bbox so they fall
        # through to the fat-trace path.
        is_filled = is_closed and p.width >= min_bbox - 1e-6

        if is_filled:
            polys.append({
                "metal": p.metal, "metal_name": name, "color": color,
                "width": p.width, "thickness": p.thickness,
                "points": [[v.x, v.y, v.z] for v in verts],
                "segment_polys": [
                    [[v.x, v.y] for v in verts[:-1]]
                ],
            })
            continue
        n_seg = len(verts) - 1
        seg_polys = []
        for i in range(n_seg):
            a, b = verts[i], verts[i + 1]
            # For an open polyline, the very first / last segment has a
            # butt-capped end (no neighbour to miter against). For a
            # closed polygon (centerline returns to start), every joint
            # is mitered including the wrap-around at index 0.
            if is_closed:
                prev_a = verts[(i - 1) % n_seg] if n_seg > 0 else None
                next_b = verts[(i + 2) % n_seg] if n_seg > 0 else None
            else:
                prev_a = verts[i - 1] if i > 0 else None
                next_b = verts[i + 2] if i + 2 < len(verts) else None
            corners = _miter_corners(prev_a, a, b, next_b, p.width)
            if not corners:
                continue
            seg_polys.append(corners)
        polys.append(
            {
                "metal": p.metal,
                "metal_name": name,
                "color": color,
                "width": p.width,
                "thickness": p.thickness,
                "points": [[v.x, v.y, v.z] for v in p.vertices],
                "segment_polys": seg_polys,
            }
        )

    # Endpoints of the very first and very last segment of the spiral are the
    # natural port locations. For wires the two polygon endpoints suffice.
    ports = []
    if shape.polygons:
        first = shape.polygons[0].vertices
        last = shape.polygons[-1].vertices
        if first:
            ports.append({"x": first[0].x, "y": first[0].y})
        if last:
            ports.append({"x": last[-1].x, "y": last[-1].y})

    bx0, by0, bx1, by1 = shape.bounding_box()
    # For a wire (1 segment), Shape.bounding_box only sees the centerline,
    # so the y-extent collapses. Inflate by W/2 so the rendered viewBox
    # actually shows the metal.
    halfw = max((p.width for p in shape.polygons), default=0.0) * 0.5
    if bx0 == bx1 and by0 == by1:
        bx0 -= halfw or 1.0
        bx1 += halfw or 1.0
        by0 -= halfw or 1.0
        by1 += halfw or 1.0
    else:
        bx0 -= halfw
        bx1 += halfw
        by0 -= halfw
        by1 += halfw
    return {
        "name": shape.name,
        "bbox": [bx0, by0, bx1, by1],
        "polygons": polys,
        "ports": ports,
        "metal_index": shape.metal,
        "turns": shape.turns,
        "width": shape.width,
        "spacing": shape.spacing,
        "sides": shape.sides,
    }


def _add_access_routing(payload: dict, shape, exit_metal_name: str) -> None:
    """Append the via cluster, overlap pads, and exit-lead trace to a
    shape's payload, faithfully reproducing what ASITIC emits when the
    user supplies an EXIT layer on a spiral.

    Mirrors ``cmd_square_build_geometry``'s post-loop access-routing
    block (decompiled at ``0x08056670``):

    1. Look up the via that connects the spiral's metal layer to the
       requested exit layer.
    2. Compute the via cluster size (an n×n grid where n is dictated by
       the trace width and via design rules: ``floor((W − 2·overplot +
       space) / (width + space))``) and emit each via cell as a tiny
       polygon on the via layer.
    3. Emit the M-overlap pads on both metal layers (a W×W square at
       the via centre).
    4. Emit the exit-lead trace on the exit metal — a W-wide rectangle
       continuing the spiral's last segment in its own direction so the
       inner port can be probed at a different layer without crossing
       any spiral metal.
    """
    tech = STATE["tech"]
    if tech is None:
        return
    polys = shape.polygons
    if not polys:
        return

    # Use the very last centerline segment to determine direction +
    # via-attachment position.
    last_poly = polys[-1]
    if len(last_poly.vertices) < 2:
        return
    cl_end = last_poly.vertices[-1]
    cl_pre = last_poly.vertices[-2]
    dx = cl_end.x - cl_pre.x
    dy = cl_end.y - cl_pre.y
    L = math.hypot(dx, dy)
    if L == 0:
        return
    ux = dx / L
    uy = dy / L
    halfw = shape.width * 0.5

    # Resolve metals.
    spiral_m = None
    exit_m = None
    for m in tech.metals:
        if m.index == shape.metal:
            spiral_m = m
        if (m.name or f"m{m.index}").lower() == exit_metal_name.lower():
            exit_m = m
    if spiral_m is None or exit_m is None or spiral_m.index == exit_m.index:
        return

    # Look up the via that bridges these two metal layers.
    via = None
    for v in tech.vias:
        if {v.top, v.bottom} == {spiral_m.index, exit_m.index}:
            via = v
            break
    if via is None:
        return

    # Via centre lands one half-width *back* from the spiral's
    # centerline tip — i.e. inside the spiral metal, not past it. The
    # M3 overlap pad then extends from cl_end backward by W (so its
    # outer edge sits flush with cl_end and overlaps the inner half of
    # the terminal trapezoid). This matches ASITIC's reference output.
    cx = cl_end.x - ux * halfw
    cy = cl_end.y - uy * halfw

    # Cluster size from design rules. Use the floor convention to match
    # the reference output (4×4 for the BiCMOS-VIA3-on-W=10 case).
    overplot = max(via.overplot1, via.overplot2)
    pitch = via.width + via.space
    if pitch <= 0:
        return
    n = max(1, int(math.floor((shape.width - 2 * overplot + via.space) / pitch)))

    # Position a regular n×n grid centred on (cx, cy). The grid spans
    # ((n-1)·space + n·width) on a side; offset each cell by the same
    # half-extent the binary uses.
    span = (n - 1) * via.space + n * via.width
    cell0 = -span * 0.5

    via_color = via.color or "white"
    exit_color = exit_m.color or "white"

    # M-overlap pads (one box on each metal). ASITIC sizes these to W×W
    # centred at the via centre.
    pad_corners = [
        [cx - halfw, cy - halfw],
        [cx + halfw, cy - halfw],
        [cx + halfw, cy + halfw],
        [cx - halfw, cy + halfw],
    ]
    payload["polygons"].append({
        "metal": exit_m.index,
        "metal_name": exit_m.name or f"m{exit_m.index}",
        "color": exit_color,
        "width": shape.width,
        "thickness": exit_m.t,
        "points": [[cx, cy, 0.0]],
        "segment_polys": [pad_corners],
    })
    payload["polygons"].append({
        "metal": spiral_m.index,
        "metal_name": spiral_m.name or f"m{spiral_m.index}",
        "color": spiral_m.color or "white",
        "width": shape.width,
        "thickness": spiral_m.t,
        "points": [[cx, cy, 0.0]],
        "segment_polys": [pad_corners],
    })

    # Via cells.
    via_cells = []
    for i in range(n):
        for j in range(n):
            x0 = cx + cell0 + i * pitch
            y0 = cy + cell0 + j * pitch
            via_cells.append([
                [x0, y0],
                [x0 + via.width, y0],
                [x0 + via.width, y0 + via.width],
                [x0, y0 + via.width],
            ])
    payload["polygons"].append({
        "metal": -1,  # via, not a metal
        "metal_name": via.name or f"via{via.index}",
        "color": via_color,
        "width": via.width,
        "thickness": 0.0,
        "points": [[cx, cy, 0.0]],
        "segment_polys": via_cells,
    })

    # Exit-lead trace on the exit metal. The binary extends the lead so
    # its outer edge sits exactly W past the spiral's outer-metal bbox
    # in the lead direction:
    #   lead_L = (spiral_outer_edge_in_dir − cl_end_in_dir) + W
    # Reverse-engineered from the captured CIFs (sq_170, sq_120, sq_200,
    # sq_260, sq_300) — matches all five vertex-for-vertex.
    all_x: list[float] = []
    all_y: list[float] = []
    for p in polys:
        for v in p.vertices:
            all_x.append(v.x); all_y.append(v.y)
    halfW = shape.width * 0.5
    spiral_xmin = min(all_x) - halfW
    spiral_xmax = max(all_x) + halfW
    spiral_ymin = min(all_y) - halfW
    spiral_ymax = max(all_y) + halfW

    # The lead's tail starts at cl_end - W (one trace-width back from
    # the spiral tip) so it overlaps the M3 metal under the via pad.
    tail_x = cl_end.x - ux * shape.width
    tail_y = cl_end.y - uy * shape.width

    if abs(ux) > abs(uy):
        outer_edge = spiral_xmax if ux > 0 else spiral_xmin
        ext = (outer_edge - tail_x) * (1.0 if ux > 0 else -1.0)
    else:
        outer_edge = spiral_ymax if uy > 0 else spiral_ymin
        ext = (outer_edge - tail_y) * (1.0 if uy > 0 else -1.0)
    lead_L = max(ext + shape.width, shape.width * 2.0)
    head_x = tail_x + ux * lead_L
    head_y = tail_y + uy * lead_L
    # Perpendicular for the W-wide trace.
    nx = -uy * halfw
    ny = ux * halfw
    lead_corners = [
        [tail_x + nx, tail_y + ny],   # tail outer-near
        [head_x + nx, head_y + ny],   # head outer-far
        [head_x - nx, head_y - ny],   # head inner-far
        [tail_x - nx, tail_y - ny],   # tail inner-near
    ]
    payload["polygons"].append({
        "metal": exit_m.index,
        "metal_name": exit_m.name or f"m{exit_m.index}",
        "color": exit_color,
        "width": shape.width,
        "thickness": exit_m.t,
        "points": [[cx, cy, 0.0], [head_x, head_y, 0.0]],
        "segment_polys": [lead_corners],
    })

    # Move the exit-port marker to the head of the lead.
    if payload.get("ports"):
        payload["ports"][-1] = {"x": head_x, "y": head_y}


def _resolve_metal(metal_arg) -> tuple[int, str, str, float]:
    """Look up a metal by name or index. Returns (idx, name, color, thickness)."""
    tech = STATE["tech"]
    if tech is None:
        raise RuntimeError("Load a tech file first.")
    for m in tech.metals:
        nm = m.name or f"m{m.index}"
        if nm.lower() == str(metal_arg).lower() or str(m.index) == str(metal_arg):
            return m.index, nm, m.color or "white", m.t
    raise ValueError(f"unknown metal: {metal_arg}")


def _build_ring(
    name: str, *, radius: float, width: float, gap_deg: float,
    sides: int, metal, x_origin: float, y_origin: float,
    phase: float, orient: float,
):
    """Direct port of ``cmd_ring_build_geometry`` (asitic_repl.c:5811).

    Emits ``sides - 1`` segment polygons whose four corners exactly match
    the C binary's CIF output. Returns (analysis_shape, payload).
    """
    tech = STATE["tech"]
    metal_idx, metal_name, metal_color, metal_t = _resolve_metal(metal)

    # ORIENT (degrees) folded into phase to match ASITIC convention.
    total_phase = phase + math.radians(orient)
    gap_rad = math.radians(abs(gap_deg))

    cos_half = math.cos(math.pi / sides)
    dvar4 = width / cos_half  # radial trace width
    per_side = (2.0 * math.pi - gap_rad) / (sides - 1)
    start = gap_rad * 0.5 + total_phase

    # Vertex angles: sides-1 sweep angles + the special end-angle that
    # closes the ring just before the gap.
    n_seg = sides - 1
    angles = [start + k * per_side for k in range(n_seg)]
    angles.append(total_phase - gap_rad * 0.5)

    R_outer = radius
    R_inner = radius - dvar4
    R_cl = radius - dvar4 * 0.5

    raw_outer = [(R_outer * math.cos(a), R_outer * math.sin(a)) for a in angles]
    raw_inner = [(R_inner * math.cos(a), R_inner * math.sin(a)) for a in angles]
    raw_cl = [(R_cl * math.cos(a), R_cl * math.sin(a)) for a in angles]

    # bbox over polygon corners (outer + inner; CL never extends further).
    xs = [p[0] for p in raw_outer + raw_inner]
    ys = [p[1] for p in raw_outer + raw_inner]
    bbox_w_half = (max(xs) - min(xs)) * 0.5
    bbox_h_half = (max(ys) - min(ys)) * 0.5

    def shift(p):
        return (p[0] + bbox_w_half + x_origin, p[1] + bbox_h_half + y_origin)

    outer = [shift(p) for p in raw_outer]
    inner = [shift(p) for p in raw_inner]
    cl = [shift(p) for p in raw_cl]

    seg_polys = []
    for k in range(n_seg):
        seg_polys.append([
            list(outer[k]),
            list(outer[k + 1]),
            list(inner[k + 1]),
            list(inner[k]),
        ])

    poly = {
        "metal": metal_idx,
        "metal_name": metal_name,
        "color": metal_color,
        "width": width,
        "thickness": metal_t,
        "points": [[x, y, 0.0] for x, y in cl],
        "segment_polys": seg_polys,
    }

    all_pts = [list(p) for p in outer + inner]
    bbox = [
        min(p[0] for p in all_pts),
        min(p[1] for p in all_pts),
        max(p[0] for p in all_pts),
        max(p[1] for p in all_pts),
    ]

    # Build a Shape for the analysis side. The current reasitic.ring is
    # gap-less, so just hand it the same radius/sides — analysis values
    # will be approximate but the rendered geometry is exact.
    sh = reasitic.ring(
        name, radius=radius, width=width, sides=sides,
        tech=tech, metal=metal_idx,
        x_origin=x_origin + bbox_w_half - radius,
        y_origin=y_origin + bbox_h_half - radius,
        phase=total_phase,
    )

    payload = {
        "name": name,
        "bbox": bbox,
        "polygons": [poly],
        "ports": [],
        "metal_index": metal_idx,
        "turns": 1.0,
        "width": width,
        "spacing": 0.0,
        "sides": sides,
    }
    return sh, payload


def _layout_polys_to_payload(shape, name: str) -> dict:
    """Convert a Shape with C-faithful CIF polygons into a draw.js payload.

    Used by the builders whose ``layout_polygons`` output IS the canonical
    CIF emission (SYMSQ, SYMPOLY, BALUN, MMSQ, TRANS, VIA): each polygon
    in the layout is a single closed quad/box, not a fat-stroke
    centerline. We pack one polygon per ``layout_polygons`` entry, with
    the polygon's vertices verbatim as a single ``segment_polys`` quad.
    """
    from reasitic.geometry import layout_polygons
    tech = STATE["tech"]
    polys_raw = layout_polygons(shape, tech)
    poly_payload: list[dict] = []
    all_x: list[float] = []
    all_y: list[float] = []
    for p in polys_raw:
        if p.metal >= len(tech.metals):
            via_idx = p.metal - len(tech.metals)
            via = tech.vias[via_idx] if 0 <= via_idx < len(tech.vias) else None
            mname = via.name if via else f"via{via_idx}"
            mcolor = (via.color if via else None) or "white"
            metal_idx = -1
        else:
            m = tech.metals[p.metal]
            mname = m.name or f"m{p.metal}"
            mcolor = m.color or "white"
            metal_idx = p.metal
        verts = list(p.vertices)
        # Drop the duplicated closing vertex if present.
        if (len(verts) >= 2
                and abs(verts[0].x - verts[-1].x) < 1e-9
                and abs(verts[0].y - verts[-1].y) < 1e-9):
            verts = verts[:-1]
        corners = [[v.x, v.y] for v in verts]
        for x, y in corners:
            all_x.append(x); all_y.append(y)
        poly_payload.append({
            "metal": metal_idx,
            "metal_name": mname,
            "color": mcolor,
            "width": p.width,
            "thickness": p.thickness,
            "points": [[v.x, v.y, v.z] for v in verts],
            "segment_polys": [corners] if corners else [],
        })

    bbox = ([min(all_x), min(all_y), max(all_x), max(all_y)]
            if all_x else [0.0, 0.0, 1.0, 1.0])
    return {
        "name": name,
        "bbox": bbox,
        "polygons": poly_payload,
        "ports": [],
        "metal_index": shape.metal,
        "turns": shape.turns,
        "width": shape.width,
        "spacing": shape.spacing,
        "sides": shape.sides,
    }


def build_shape(spec: dict) -> dict:
    """Build a Shape from the JS-side parameter dict and return its payload.

    Recognised ``kind`` values:

      square_spiral / polygon_spiral / ring / wire / capacitor / via
      symmetric_square / symmetric_polygon / multi_metal_square
      transformer_primary / transformer_secondary
      balun_primary / balun_secondary

    Other keys (all per-shape; only relevant ones are read):
      name, metal, exit_metal, secondary_metal, metal_bottom
      width, length, radius, ilen, spacing, turns, sides, gap, n_via_x, n_via_y, via_index
      x_origin, y_origin, phase, orient
    """
    tech = STATE["tech"]
    if tech is None:
        raise RuntimeError("Load a tech file first.")

    kind = spec.get("kind", "square_spiral")
    name = spec.get("name", "L1")
    metal = spec.get("metal", tech.metals[-1].name or 0)
    exit_metal = spec.get("exit_metal") or None
    width = float(spec.get("width", 10.0))
    length = float(spec.get("length", 170.0))
    spacing = float(spec.get("spacing", 3.0))
    turns = float(spec.get("turns", 2.0))
    sides = int(spec.get("sides", 8))
    radius = float(spec.get("radius", 100.0))
    ilen = float(spec.get("ilen", 0.0))
    x_origin = float(spec.get("x_origin", 0.0))
    y_origin = float(spec.get("y_origin", 0.0))
    phase = float(spec.get("phase", 0.0))
    orient = float(spec.get("orient", 0.0))
    secondary_metal = spec.get("secondary_metal") or None
    # Combine ORIENT (degrees, ASITIC convention) with PHASE (radians)
    # into the single ``phase`` argument the Python builder accepts.
    total_phase = phase + math.radians(orient)

    common = dict(
        tech=tech, metal=metal,
        x_origin=x_origin, y_origin=y_origin,
        phase=total_phase,
    )

    if kind == "square_spiral":
        sh = reasitic.square_spiral(
            name, length=length, width=width, spacing=spacing,
            turns=turns, **common,
        )
    elif kind == "wire":
        sh = reasitic.wire(
            name, length=length, width=width, **common,
        )
    elif kind == "ring":
        # Ring: direct CIF-equivalent builder that reproduces
        # cmd_ring_build_geometry's segment polygons byte-for-byte.
        gap_deg = float(spec.get("gap", 0.0))
        n_sides = sides if sides >= 3 else 16
        ring_radius = float(spec.get("radius", length))
        sh, ring_payload = _build_ring(
            name, radius=ring_radius, width=width, gap_deg=gap_deg,
            sides=n_sides, metal=metal, x_origin=x_origin,
            y_origin=y_origin, phase=total_phase, orient=orient,
        )
        STATE["shape"] = sh
        return ring_payload
    elif kind == "capacitor":
        metal_bottom = spec.get("metal_bottom", metal)
        sh = reasitic.capacitor(
            name, length=length, width=width,
            metal_top=metal, metal_bottom=metal_bottom,
            tech=tech,
            x_origin=x_origin,
            y_origin=y_origin,
        )
    elif kind == "polygon_spiral":
        sh = reasitic.polygon_spiral(
            name, radius=radius, width=width, spacing=spacing,
            turns=turns, sides=sides if sides >= 3 else 8,
            tech=tech, metal=metal,
            x_origin=x_origin, y_origin=y_origin, phase=total_phase,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind == "symmetric_square":
        sh = reasitic.symmetric_square(
            name, length=length, width=width, spacing=spacing,
            turns=turns, ilen=ilen if ilen > 0 else (width + spacing),
            tech=tech, primary_metal=metal,
            exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind == "symmetric_polygon":
        sh = reasitic.symmetric_polygon(
            name, radius=radius, width=width, spacing=spacing,
            turns=turns, ilen=ilen if ilen > 0 else (width + spacing),
            sides=sides if sides >= 4 else 8,
            tech=tech, primary_metal=metal,
            exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind == "multi_metal_square":
        sh = reasitic.multi_metal_square(
            name, length=length, width=width, spacing=spacing,
            turns=turns, tech=tech,
            metal=metal, exit_metal=exit_metal if exit_metal else metal,
            x_origin=x_origin, y_origin=y_origin,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind in ("transformer_primary", "transformer_secondary"):
        which = "primary" if kind == "transformer_primary" else "secondary"
        sh = reasitic.transformer(
            name, length=length, width=width, spacing=spacing,
            turns=turns, tech=tech,
            metal=metal, exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin, which=which,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind in ("balun_primary", "balun_secondary"):
        which = "primary" if kind == "balun_primary" else "secondary"
        sh = reasitic.balun(
            name, length=length, width=width, spacing=spacing,
            turns=turns, tech=tech, primary_metal=metal,
            secondary_metal=secondary_metal if secondary_metal else metal,
            exit_metal=exit_metal if exit_metal else (secondary_metal or metal),
            x_origin=x_origin, y_origin=y_origin, which=which,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    elif kind == "via":
        nx = int(spec.get("n_via_x", 1))
        ny = int(spec.get("n_via_y", nx))
        via_index = int(spec.get("via_index", 0))
        sh = reasitic.via(
            name, tech=tech, via_index=via_index, nx=nx, ny=ny,
            x_origin=x_origin, y_origin=y_origin,
        )
        STATE["shape"] = sh
        return _layout_polys_to_payload(sh, name)
    else:
        raise ValueError(f"unknown shape kind: {kind}")

    STATE["shape"] = sh
    payload = _shape_to_payload(sh)
    # ASITIC defaults the EXIT layer to the metal one slot below the
    # spiral's METAL when the user doesn't specify EXIT explicitly.
    # We replicate that here so non-EXIT spiral commands still get the
    # via + access-lead the binary emits by default.
    effective_exit = exit_metal
    # ASITIC's SQ command always adds a via + exit lead by default;
    # the SP / SYMSQ commands do NOT — they only build the spiral
    # metal unless the user explicitly supplies an exit layer.
    if not effective_exit and kind == "square_spiral":
        spiral_metal_idx = sh.metal
        for m in tech.metals:
            if m.index == spiral_metal_idx - 1:
                effective_exit = m.name or f"m{m.index}"
                break
    if effective_exit:
        _add_access_routing(payload, sh, effective_exit)
        # Refresh bbox to include the via + exit-lead extras.
        all_x: list[float] = []
        all_y: list[float] = []
        for p in payload["polygons"]:
            for sp in p.get("segment_polys", []):
                for x, y in sp:
                    all_x.append(x); all_y.append(y)
        if all_x and all_y:
            payload["bbox"] = [min(all_x), min(all_y), max(all_x), max(all_y)]
    return payload


# --- Analysis -------------------------------------------------------------

def _require() -> tuple:
    sh = STATE["shape"]
    tech = STATE["tech"]
    if sh is None or tech is None:
        raise RuntimeError("Build a shape first.")
    return sh, tech


def analyze_lrq(freq_ghz: float) -> dict:
    sh, tech = _require()
    L = reasitic.compute_self_inductance(sh)
    R_dc = reasitic.compute_dc_resistance(sh, tech)
    R_ac = reasitic.compute_ac_resistance(sh, tech, freq_ghz)
    Q = reasitic.metal_only_q(sh, tech, freq_ghz)
    n_segs = len(sh.segments())
    total_len = sum(s.length for s in sh.segments())
    return {
        "freq_ghz": freq_ghz,
        "L_nH": L,
        "R_dc_ohm": R_dc,
        "R_ac_ohm": R_ac,
        "Q": Q,
        "n_segments": n_segs,
        "total_length_um": total_len,
    }


def analyze_pi(freq_ghz: float) -> dict:
    sh, tech = _require()
    pi = pi_model_at_freq(sh, tech, freq_ghz)
    return {
        "freq_ghz": freq_ghz,
        "L_nH": pi.L_nH,
        "R_series": pi.R_series,
        "C_p1_fF": pi.C_p1_fF,
        "C_p2_fF": pi.C_p2_fF,
        "g_p1": pi.g_p1,
        "g_p2": pi.g_p2,
    }


def analyze_sweep(f1: float, f2: float, step: float) -> dict:
    sh, tech = _require()
    if step <= 0:
        raise ValueError("Sweep step must be > 0")
    if f2 <= f1:
        raise ValueError("Sweep f2 must be > f1")
    fs = linear_freqs(f1, f2, step)
    sweep = two_port_sweep(sh, tech, fs)
    s11 = []
    s21 = []
    s12 = []
    s22 = []
    for f, S in zip(fs, sweep.S, strict=True):
        s11.append(abs(S[0, 0]))
        s12.append(abs(S[0, 1]))
        s21.append(abs(S[1, 0]))
        s22.append(abs(S[1, 1]))
    # Self-resonance on best-effort basis
    sr_freq = None
    try:
        sr = self_resonance(sh, tech, f_start=f1, f_stop=f2)
        if sr and getattr(sr, "f_self_res", None):
            sr_freq = sr.f_self_res
    except Exception:
        sr_freq = None
    return {
        "freqs_ghz": list(fs),
        "abs_S11": s11,
        "abs_S12": s12,
        "abs_S21": s21,
        "abs_S22": s22,
        "self_resonance_ghz": sr_freq,
    }


def export_s2p(f1: float, f2: float, step: float) -> str:
    sh, tech = _require()
    fs = linear_freqs(f1, f2, step)
    sweep = two_port_sweep(sh, tech, fs)
    pts = sweep.to_touchstone_points(param="S")
    return write_touchstone(pts, param="S", fmt="MA", z0_ohm=50.0)


def export_spice(freq_ghz: float) -> str:
    sh, tech = _require()
    return write_spice_subckt(sh, tech, freq_ghz)


def geom_info() -> dict:
    sh, tech = _require()
    n_segs = len(sh.segments())
    total_len = sum(s.length for s in sh.segments())
    metal_name, _ = _resolve_metal_color(tech, sh.metal)
    return {
        "name": sh.name,
        "metal": metal_name,
        "metal_index": sh.metal,
        "turns": sh.turns,
        "width_um": sh.width,
        "spacing_um": sh.spacing,
        "sides": sh.sides,
        "n_polygons": len(sh.polygons),
        "n_segments": n_segs,
        "total_segment_length_um": total_len,
        "bbox": list(sh.bounding_box()),
    }


# --- Free-form REPL ------------------------------------------------------

def run_repl(source: str) -> dict:
    """Execute user Python with `shape`, `tech`, and `reasitic` in scope.

    Captures stdout/stderr; returns {"stdout": ..., "stderr": ..., "ok": bool}.
    """
    g = {
        "__name__": "__repl__",
        "reasitic": reasitic,
        "shape": STATE["shape"],
        "tech": STATE["tech"],
        "math": math,
    }
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    ok = True
    try:
        exec(compile(source, "<repl>", "exec"), g)
    except BaseException:
        ok = False
        traceback.print_exc(file=err_buf)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    # If the user reassigned shape, sync it.
    if "shape" in g and g["shape"] is not None:
        STATE["shape"] = g["shape"]
    return {"ok": ok, "stdout": out_buf.getvalue(), "stderr": err_buf.getvalue()}


def version_info() -> str:
    return reasitic.summary()


def current_shape_payload():
    """Return the draw.js payload for the currently bound shape, or None."""
    sh = STATE["shape"]
    if sh is None or STATE["tech"] is None:
        return None
    return _shape_to_payload(sh)
