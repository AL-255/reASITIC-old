"""Tk Canvas renderer for layout shapes.

Mirrors the pipeline in ``xui_render_layout_view`` /
``xui_redraw_substrate_polygons`` (see ``decomp/output/asitic_repl.c``
~22217 / 22825):

1. Clear the canvas (X11 ``XClearWindow``).
2. Draw the chip outline (``xui_draw_chip_outline``).
3. Draw the snap/view grid (``xui_draw_grid_or_ruler``).
4. For every shape, fill each polygon stroke with the metal colour and
   stamp the shape name at its centroid (``xui_draw_string_at_world``).
5. Highlight the currently-selected shape with a thick border
   (``xui_draw_zoom_box_around_current_shape``).

Tkinter takes the role of the X11 GC + pixmap pair; the
:class:`~reasitic.gui.viewport.Viewport` handles world↔screen.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from reasitic.geometry import Point, Polygon, Shape
from reasitic.gui.colors import metal_color
from reasitic.gui.viewport import Viewport
from reasitic.tech import Tech

if TYPE_CHECKING:
    from tkinter import Canvas


# Tag used for every drawn item so we can wipe the layer in one call
LAYOUT_TAG = "layout"
GRID_TAG = "grid"
CHIP_TAG = "chip"
SELECTION_TAG = "selection"


def _metal_name(tech: Tech, idx: int) -> str:
    if 0 <= idx < len(tech.metals):
        return tech.metals[idx].name
    return ""


def draw_chip_outline(canvas: Canvas, tech: Tech, vp: Viewport) -> None:
    """Draw the rectangular chip boundary on the canvas."""
    canvas.delete(CHIP_TAG)
    cx = tech.chip.chipx
    cy = tech.chip.chipy
    if cx <= 0 or cy <= 0:
        return
    x0, y0 = vp.world_to_screen(0.0, 0.0)
    x1, y1 = vp.world_to_screen(cx, cy)
    canvas.create_rectangle(x0, y0, x1, y1, outline="#bbbbbb",
                            dash=(2, 4), width=1, tags=CHIP_TAG)


def draw_grid(canvas: Canvas, vp: Viewport, *,
              step_um: float, color: str = "#2c2c2c") -> None:
    """Stamp a regular grid of points over the visible world bbox.

    Mirrors ``xui_draw_grid_or_ruler`` minus the ruler labels (those
    show up in the dedicated dimension-overlay path on selection).
    """
    canvas.delete(GRID_TAG)
    if step_um <= 0:
        return
    x0, y0, x1, y1 = vp.world_bbox()
    # Snap to multiples of step_um
    import math
    gx0 = math.floor(x0 / step_um) * step_um
    gy0 = math.floor(y0 / step_um) * step_um
    nx = math.ceil((x1 - gx0) / step_um) + 1
    ny = math.ceil((y1 - gy0) / step_um) + 1
    # Cap density so we don't drown the canvas in dots
    if nx * ny > 8000:
        return
    for ix in range(nx):
        wx = gx0 + ix * step_um
        for iy in range(ny):
            wy = gy0 + iy * step_um
            sx, sy = vp.world_to_screen(wx, wy)
            canvas.create_oval(sx - 0.5, sy - 0.5, sx + 0.5, sy + 0.5,
                               fill=color, outline="", tags=GRID_TAG)


def draw_polygon(canvas: Canvas, poly: Polygon, vp: Viewport,
                 color: str, *, tags: tuple[str, ...] = ()) -> None:
    """Render a single polygon onto the canvas as a filled stroke band."""
    if len(poly.vertices) < 2:
        return
    pts: list[float] = []
    for v in poly.vertices:
        sx, sy = vp.world_to_screen(v.x, v.y)
        pts.extend((sx, sy))
    # Open polylines (a wire trace) are rendered as a thick line; closed
    # polygons (filled vias / capacitor plates) are filled.
    if _is_closed(poly):
        canvas.create_polygon(*pts, fill=color, outline=color, width=1,
                              tags=tags)
    else:
        # Width in pixels — use the band width from the polygon's metal
        # layer when known; otherwise keep a 2 px stroke.
        line_w = max(1.0, poly.width * vp.zoom)
        canvas.create_line(*pts, fill=color, width=line_w,
                           capstyle="butt", joinstyle="miter", tags=tags)


def _is_closed(poly: Polygon) -> bool:
    if len(poly.vertices) < 3:
        return False
    a, b = poly.vertices[0], poly.vertices[-1]
    return abs(a.x - b.x) < 1e-9 and abs(a.y - b.y) < 1e-9


def shape_centroid(shape: Shape) -> Point:
    """Return the centroid of ``shape``'s vertices (μm)."""
    xs: list[float] = []
    ys: list[float] = []
    for poly in shape.polygons:
        for v in poly.vertices:
            xs.append(v.x)
            ys.append(v.y)
    if not xs:
        return Point(0.0, 0.0, 0.0)
    return Point(sum(xs) / len(xs), sum(ys) / len(ys), 0.0)


def draw_shape(canvas: Canvas, shape: Shape, tech: Tech, vp: Viewport,
               *, label: bool = True,
               extra_tags: tuple[str, ...] = ()) -> None:
    """Render every polygon of ``shape`` plus a name label."""
    base_tags = (LAYOUT_TAG, f"shape:{shape.name}", *extra_tags)
    for poly in shape.polygons:
        col = metal_color(tech, _metal_name(tech, poly.metal))
        draw_polygon(canvas, poly, vp, col, tags=base_tags)
    if label and shape.name:
        c = shape_centroid(shape)
        sx, sy = vp.world_to_screen(c.x, c.y)
        canvas.create_text(sx, sy, text=shape.name, fill="#dddddd",
                           font=("TkDefaultFont", 9), tags=base_tags)


def draw_selection(canvas: Canvas, shape: Shape, vp: Viewport) -> None:
    """Highlight ``shape`` with a thick yellow bbox."""
    canvas.delete(SELECTION_TAG)
    x0, y0, x1, y1 = shape.bounding_box()
    if x0 == x1 == y0 == y1 == 0.0:
        return
    sx0, sy0 = vp.world_to_screen(x0, y0)
    sx1, sy1 = vp.world_to_screen(x1, y1)
    # Tk's coords don't enforce ordering, but the bbox is rendered the
    # same regardless.
    canvas.create_rectangle(sx0, sy0, sx1, sy1, outline="#ffd54a",
                            width=2, tags=SELECTION_TAG)


def render_all(canvas: Canvas, tech: Tech | None,
               shapes: dict[str, Shape],
               vp: Viewport,
               *, grid_step_um: float = 0.0,
               selected: str | None = None) -> None:
    """Top-level redraw — wipe existing layout, draw chip + grid + shapes."""
    canvas.delete(LAYOUT_TAG)
    canvas.delete(GRID_TAG)
    canvas.delete(CHIP_TAG)
    canvas.delete(SELECTION_TAG)
    if tech is not None:
        draw_chip_outline(canvas, tech, vp)
    if grid_step_um > 0 and tech is not None:
        draw_grid(canvas, vp, step_um=grid_step_um)
    if tech is None:
        return
    for shape in shapes.values():
        draw_shape(canvas, shape, tech, vp)
    if selected and selected in shapes:
        draw_selection(canvas, shapes[selected], vp)
