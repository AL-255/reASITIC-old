"""Pan / zoom viewport math for the layout view.

Mirrors the world↔screen transformation used by the original ASITIC X11
front-end (see ``decomp/output/asitic_repl.c`` lines ~6920 / 21800):

.. code-block:: c

    /* world coords (μm) → screen coords (px) */
    sx =  (wx + g_pan_x) * g_zoom_scale + g_x11_canvas_width  / 2
    sy = -(wy + g_pan_y) * g_zoom_scale + g_x11_canvas_height / 2

The screen Y axis points down, the world Y axis points up, hence the sign
flip on the Y term. The transformation is implemented here with no
Tkinter dependency so that it can be unit-tested headlessly.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass
class Viewport:
    """A 2-D pan/zoom transform from layout (μm) to canvas (px) coordinates.

    Mirrors the binary's view-state globals: ``zoom`` is
    ``g_zoom_scale`` and ``pan_x`` / ``pan_y`` are ``g_pan_x`` /
    ``g_pan_y``. ``canvas_width`` / ``canvas_height`` track the live
    canvas widget size in pixels (the binary uses
    ``g_x11_canvas_width`` / ``g_x11_canvas_height``).
    """

    canvas_width: int = 800
    canvas_height: int = 600
    zoom: float = 1.0
    pan_x: float = 0.0
    pan_y: float = 0.0

    # ----- Forward transform ---------------------------------------------

    def world_to_screen(self, wx: float, wy: float) -> tuple[float, float]:
        """Map a world-space (μm) point to canvas pixel coordinates."""
        sx = (wx + self.pan_x) * self.zoom + self.canvas_width / 2.0
        sy = -(wy + self.pan_y) * self.zoom + self.canvas_height / 2.0
        return sx, sy

    def screen_to_world(self, sx: float, sy: float) -> tuple[float, float]:
        """Inverse of :meth:`world_to_screen`."""
        wx = (sx - self.canvas_width / 2.0) / self.zoom - self.pan_x
        wy = -(sy - self.canvas_height / 2.0) / self.zoom - self.pan_y
        return wx, wy

    # ----- Mutators ------------------------------------------------------

    def pan_by_pixels(self, dx_px: float, dy_px: float) -> None:
        """Shift the view by ``(dx, dy)`` pixels (pixel-space)."""
        self.pan_x += dx_px / self.zoom
        self.pan_y -= dy_px / self.zoom

    def zoom_at_screen(self, sx: float, sy: float, factor: float) -> None:
        """Multiply ``zoom`` by ``factor``, keeping the world point under
        ``(sx, sy)`` fixed on the canvas (matches the binary's
        ``cmd_scale_clamp_view`` zoom behaviour)."""
        if factor <= 0.0:
            raise ValueError("zoom factor must be positive")
        wx, wy = self.screen_to_world(sx, sy)
        self.zoom *= factor
        # After scaling, push pan so that (wx, wy) maps back to (sx, sy).
        new_sx, new_sy = self.world_to_screen(wx, wy)
        self.pan_x += (sx - new_sx) / self.zoom
        self.pan_y -= (sy - new_sy) / self.zoom

    def fit_bbox(self, x_min: float, y_min: float, x_max: float, y_max: float,
                 *, margin: float = 0.05) -> None:
        """Set ``zoom`` and ``pan`` so the bbox fits the canvas with margin."""
        if x_max <= x_min or y_max <= y_min:
            return
        bw = (x_max - x_min) * (1.0 + 2 * margin)
        bh = (y_max - y_min) * (1.0 + 2 * margin)
        sx = self.canvas_width / bw
        sy = self.canvas_height / bh
        self.zoom = min(sx, sy)
        cx = 0.5 * (x_min + x_max)
        cy = 0.5 * (y_min + y_max)
        self.pan_x = -cx
        self.pan_y = -cy

    def reset(self) -> None:
        """Reset to identity (zoom=1, pan=0)."""
        self.zoom = 1.0
        self.pan_x = 0.0
        self.pan_y = 0.0

    def world_bbox(self) -> tuple[float, float, float, float]:
        """Return the current world-space (x_min, y_min, x_max, y_max)."""
        x0, y0 = self.screen_to_world(0, self.canvas_height)
        x1, y1 = self.screen_to_world(self.canvas_width, 0)
        return x0, y0, x1, y1
