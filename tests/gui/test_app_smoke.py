"""Smoke test: spawn the Tk GUI, drive a few commands, close it.

Auto-skips when Tk is unavailable (e.g. no DISPLAY on a CI box that
doesn't have Xvfb).
"""

from __future__ import annotations

import os
import sys

import pytest

from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


def _tk_available() -> bool:
    if sys.platform.startswith("linux") and not os.environ.get("DISPLAY"):
        return False
    try:
        import tkinter

        # Try to actually create a root — on macOS / WSL Tk can be
        # importable but fail to talk to a server.
        tkinter.Tk().destroy()
    except Exception:
        return False
    return True


pytestmark = pytest.mark.skipif(
    not _tk_available(),
    reason="Tk display unavailable (set DISPLAY or run under xvfb-run)",
)


def test_app_starts_and_renders_tech_then_a_spiral():
    from reasitic.gui.app import GuiApp

    app = GuiApp(width=900, height=600)
    try:
        app._run(f"load-tech {_BICMOS}")
        assert app.repl.tech is not None
        assert app.repl.tech.chip.chipx > 0

        app._run("SQ NAME=L1:LEN=170:W=10:S=3:N=2:METAL=m3")
        assert "L1" in app.repl.shapes

        app.action_fit()
        # We should have a non-trivial zoom now
        assert app.viewport.zoom > 0
        # The fit should have positioned us on the spiral's bbox
        x0, y0, x1, y1 = app.repl.shapes["L1"].bounding_box()
        cx = 0.5 * (x0 + x1)
        cy = 0.5 * (y0 + y1)
        sx, sy = app.viewport.world_to_screen(cx, cy)
        assert abs(sx - app.viewport.canvas_width / 2.0) < 5.0
        assert abs(sy - app.viewport.canvas_height / 2.0) < 5.0

        # Toggle the grid on then off — should not raise
        app.action_toggle_grid()
        app.refresh_view()
        app.action_toggle_grid()
        app.refresh_view()

        # Pan via mouse synth
        app.viewport.pan_by_pixels(20, -10)
        app.refresh_view()
    finally:
        app.root.destroy()


def test_app_handles_zoom_at_center():
    from reasitic.gui.app import GuiApp

    app = GuiApp()
    try:
        app._zoom_centre(2.0)
        assert app.viewport.zoom == pytest.approx(2.0)
        app._zoom_centre(0.5)
        assert app.viewport.zoom == pytest.approx(1.0)
    finally:
        app.root.destroy()