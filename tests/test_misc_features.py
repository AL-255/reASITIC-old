"""Tests for FFT Green's grid, transforms, and the DesignReport."""

import math

import numpy as np
import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.report import design_report
from reasitic.substrate import (
    GreenFFTGrid,
    green_apply,
    setup_green_fft_grid,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Shape transforms ------------------------------------------------------


def test_translate_returns_new_shape(tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=2, tech=tech, metal="m3"
    )
    moved = sp.translate(50.0, 25.0)
    assert moved is not sp
    # Bounding box shifts by (50, 25)
    xmin0, ymin0, _, _ = sp.bounding_box()
    xmin1, ymin1, _, _ = moved.bounding_box()
    assert xmin1 - xmin0 == pytest.approx(50.0)
    assert ymin1 - ymin0 == pytest.approx(25.0)


def test_flip_horizontal_mirrors_x(tech) -> None:
    w = wire("W", length=100, width=10, tech=tech, metal="m3")
    flipped = w.flip_horizontal()
    # After flipping about the origin, endpoint x-coords are negated
    a0 = w.polygons[0].vertices[0]
    a1 = flipped.polygons[0].vertices[0]
    assert a1.x == pytest.approx(2.0 * w.x_origin - a0.x)


def test_flip_vertical_mirrors_y(tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1, tech=tech, metal="m3"
    )
    flipped = sp.flip_vertical()
    a0 = sp.polygons[0].vertices[0]
    a1 = flipped.polygons[0].vertices[0]
    assert a1.y == pytest.approx(2.0 * sp.y_origin - a0.y)


def test_rotate_90_swaps_xy_pattern(tech) -> None:
    """A 90° rotation about the origin maps (x, y) → (-y, x)."""
    w = wire("W", length=100, width=10, tech=tech, metal="m3")
    rotated = w.rotate_xy(math.pi / 2)
    a0 = w.polygons[0].vertices[0]
    a1 = rotated.polygons[0].vertices[0]
    cx, cy = w.x_origin, w.y_origin
    expected_x = cx - (a0.y - cy)
    expected_y = cy + (a0.x - cx)
    assert a1.x == pytest.approx(expected_x, abs=1e-9)
    assert a1.y == pytest.approx(expected_y, abs=1e-9)


def test_rotate_360_returns_to_start(tech) -> None:
    """A full 360° rotation should leave coordinates unchanged."""
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1, tech=tech, metal="m3"
    )
    out = sp.rotate_xy(2 * math.pi)
    for p0, p1 in zip(sp.polygons, out.polygons, strict=True):
        for v0, v1 in zip(p0.vertices, p1.vertices, strict=True):
            assert v0.x == pytest.approx(v1.x, abs=1e-9)
            assert v0.y == pytest.approx(v1.y, abs=1e-9)


# FFT grid -------------------------------------------------------------


def test_fft_grid_setup_returns_correct_shape(tech) -> None:
    grid = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
    assert isinstance(grid, GreenFFTGrid)
    # g_grid is the spatial-domain centred slice; g_fft is the
    # zero-padded (2N, 2N) FFT used for linear convolution.
    assert grid.g_grid.shape == (16, 16)
    assert grid.g_fft.shape == (32, 32)
    assert grid.nx == 16


def test_fft_grid_uses_tech_defaults(tech) -> None:
    grid = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0)
    # BiCMOS.tek specifies fftx=ffty=128
    assert grid.nx == 128
    assert grid.ny == 128


def test_green_apply_returns_correct_shape(tech) -> None:
    grid = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=8, ny=8)
    charge = np.zeros((8, 8))
    charge[4, 4] = 1.0  # delta source at centre
    pot = green_apply(grid, charge)
    assert pot.shape == (8, 8)
    # Convolution of delta with G grid = G grid (cyclic so peak at origin)
    assert math.isfinite(float(pot.max()))


def test_green_apply_rejects_wrong_shape(tech) -> None:
    grid = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=8, ny=8)
    with pytest.raises(ValueError):
        green_apply(grid, np.zeros((4, 4)))


# Design report --------------------------------------------------------


def test_design_report_has_all_fields(tech) -> None:
    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
    assert rpt.name == "L1"
    assert rpt.L_dc_nH > 0
    assert rpt.R_dc_ohm > 0
    assert rpt.metal_area_um2 > 0
    assert rpt.n_segments == 12
    assert rpt.self_resonance_ghz is not None
    assert len(rpt.points) == 3
    text = rpt.format_text()
    assert "L1" in text
    assert "f_SR" in text


def test_design_report_format_text_lines(tech) -> None:
    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=2, tech=tech, metal="m3"
    )
    rpt = design_report(sp, tech, freqs_ghz=[2.0])
    text = rpt.format_text()
    # Header + L_dc + R_dc + Area + Geometry + f_SR + blank + col header + 1 row
    assert text.count("\n") >= 8