"""Tests for the GDSII layout export via gdstk."""

from __future__ import annotations

from pathlib import Path

import pytest

import reasitic
from reasitic.exports import (
    read_gds,
    read_gds_file,
    write_gds,
    write_gds_file,
)
from tests import _paths

gdstk = pytest.importorskip("gdstk")

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3"
    )


@pytest.fixture
def cap(tech):
    return reasitic.capacitor(
        "PAD", length=50, width=50,
        metal_top="m3", metal_bottom="m2", tech=tech,
    ).translate(80, 80)


# write_gds bytes interface ----------------------------------------------


def test_write_gds_returns_nonempty_bytes(spiral):
    data = write_gds([spiral])
    assert isinstance(data, bytes)
    # GDSII file should start with HEADER record (0x00 0x06 0x00 0x02)
    assert data[:2] == b"\x00\x06"


def test_write_gds_handles_multiple_shapes(spiral, cap):
    data = write_gds([spiral, cap])
    assert isinstance(data, bytes)
    assert len(data) > 100


def test_write_gds_file_creates_file(tmp_path: Path, spiral):
    p = tmp_path / "L1.gds"
    write_gds_file(p, [spiral])
    assert p.exists()
    assert p.stat().st_size > 0


# Round-trip --------------------------------------------------------------


def test_round_trip_preserves_shape_count(tmp_path: Path, spiral, cap, tech):
    p = tmp_path / "out.gds"
    write_gds_file(p, [spiral, cap])
    shapes = read_gds_file(p, tech)
    assert len(shapes) == 2


def test_round_trip_preserves_cell_names(tmp_path: Path, spiral, cap, tech):
    p = tmp_path / "out.gds"
    write_gds_file(p, [spiral, cap])
    shapes = read_gds_file(p, tech)
    names = {s.name for s in shapes}
    assert "L1" in names
    assert "PAD" in names


def test_round_trip_preserves_polygon_count(tmp_path: Path, cap, tech):
    """A capacitor has explicit closed polygons; their count must
    survive the round-trip."""
    p = tmp_path / "out.gds"
    write_gds_file(p, [cap])
    shapes = read_gds_file(p, tech)
    [round_tripped] = shapes
    assert len(round_tripped.polygons) == len(cap.polygons)


def test_round_trip_preserves_metal_assignment(tmp_path: Path, cap, tech):
    """Polygon metal indices should round-trip via the GDS layer field."""
    p = tmp_path / "out.gds"
    write_gds_file(p, [cap])
    shapes = read_gds_file(p, tech)
    metals_in = sorted({p.metal for p in cap.polygons})
    metals_out = sorted({p.metal for p in shapes[0].polygons})
    assert metals_in == metals_out


def test_round_trip_via_bytes(spiral, cap, tech):
    """The bytes-only path must accept what the byte-writer produces."""
    data = write_gds([spiral, cap])
    shapes = read_gds(data, tech)
    assert len(shapes) == 2


def test_round_trip_preserves_polygon_coordinates(tmp_path: Path, cap, tech):
    """A closed polygon's vertices should be recoverable to ~nm."""
    p = tmp_path / "out.gds"
    write_gds_file(p, [cap])
    shapes = read_gds_file(p, tech)
    out_poly = shapes[0].polygons[0]
    in_poly = cap.polygons[0]
    in_xs = sorted([v.x + cap.x_origin for v in in_poly.vertices])
    out_xs = sorted([v.x for v in out_poly.vertices])
    # gdstk has nm precision by default
    assert in_xs[0] == pytest.approx(out_xs[0], abs=1e-3)
    assert in_xs[-1] == pytest.approx(out_xs[-1], abs=1e-3)


# Validation --------------------------------------------------------------


def test_empty_shape_list_writes_empty_lib(tmp_path: Path):
    p = tmp_path / "empty.gds"
    write_gds_file(p, [])
    shapes = read_gds_file(p)
    assert shapes == []


def test_unit_and_precision_settable(tmp_path: Path, cap):
    """gdstk should accept custom unit / precision."""
    p = tmp_path / "out.gds"
    write_gds_file(p, [cap], unit=1e-6, precision=1e-12)
    assert p.exists()
