"""Unit tests for the pan/zoom math (no Tk dep, runs headlessly)."""

import pytest

from reasitic.gui.viewport import Viewport


def test_world_to_screen_round_trip():
    vp = Viewport(canvas_width=800, canvas_height=600, zoom=2.0,
                  pan_x=10.0, pan_y=-5.0)
    for wx, wy in [(0, 0), (100, 50), (-30, 200), (1234.5, -678.9)]:
        sx, sy = vp.world_to_screen(wx, wy)
        wx2, wy2 = vp.screen_to_world(sx, sy)
        assert wx2 == pytest.approx(wx, abs=1e-9)
        assert wy2 == pytest.approx(wy, abs=1e-9)


def test_origin_world_maps_to_centre_with_zero_pan():
    vp = Viewport(canvas_width=400, canvas_height=300)
    sx, sy = vp.world_to_screen(0.0, 0.0)
    assert sx == pytest.approx(200.0)
    assert sy == pytest.approx(150.0)


def test_zoom_at_screen_keeps_anchor_fixed():
    vp = Viewport(canvas_width=800, canvas_height=600, zoom=1.0)
    sx, sy = 600, 400
    wx, wy = vp.screen_to_world(sx, sy)
    vp.zoom_at_screen(sx, sy, 2.5)
    sx2, sy2 = vp.world_to_screen(wx, wy)
    assert sx2 == pytest.approx(sx, abs=1e-6)
    assert sy2 == pytest.approx(sy, abs=1e-6)
    assert vp.zoom == pytest.approx(2.5)


def test_zoom_factor_must_be_positive():
    vp = Viewport()
    with pytest.raises(ValueError):
        vp.zoom_at_screen(0, 0, 0.0)
    with pytest.raises(ValueError):
        vp.zoom_at_screen(0, 0, -1.0)


def test_pan_by_pixels_adjusts_world_origin():
    vp = Viewport(canvas_width=400, canvas_height=400, zoom=2.0)
    vp.pan_by_pixels(100, -50)
    # 100px / 2 = 50μm in X, -50px / 2 = +25μm in Y (Y axis is flipped)
    assert vp.pan_x == pytest.approx(50.0)
    assert vp.pan_y == pytest.approx(25.0)


def test_fit_bbox_centres_on_bbox():
    vp = Viewport(canvas_width=600, canvas_height=400)
    vp.fit_bbox(100, 200, 300, 400)
    # Centre of bbox is (200, 300); should map to canvas centre.
    sx, sy = vp.world_to_screen(200.0, 300.0)
    assert sx == pytest.approx(300.0, abs=0.5)
    assert sy == pytest.approx(200.0, abs=0.5)


def test_fit_bbox_uses_smaller_axis_to_avoid_clipping():
    vp = Viewport(canvas_width=400, canvas_height=400)
    # 1:4 aspect bbox into a square canvas: zoom must be set by Y axis
    vp.fit_bbox(0, 0, 100, 400)
    # With margin=0.05 → effective height 440 → zoom 400/440 ≈ 0.909
    assert 0.85 < vp.zoom < 0.95


def test_fit_bbox_ignores_degenerate():
    vp = Viewport(canvas_width=400, canvas_height=400, zoom=1.5)
    vp.fit_bbox(10, 10, 10, 10)  # zero-size — no-op
    assert vp.zoom == pytest.approx(1.5)


def test_reset_brings_view_to_identity():
    vp = Viewport(zoom=4.2, pan_x=999.0, pan_y=-12.3)
    vp.reset()
    assert vp.zoom == 1.0
    assert vp.pan_x == 0.0
    assert vp.pan_y == 0.0


def test_world_bbox_matches_pixel_corners():
    vp = Viewport(canvas_width=400, canvas_height=300, zoom=2.0)
    x0, y0, x1, y1 = vp.world_bbox()
    # Bottom-left pixel (0, h) → world (-w/(2z), -h/(2z))
    assert x0 == pytest.approx(-100.0)
    assert y0 == pytest.approx(-75.0)
    assert x1 == pytest.approx(100.0)
    assert y1 == pytest.approx(75.0)
