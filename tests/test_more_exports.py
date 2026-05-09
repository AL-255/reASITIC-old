"""Tests for Tek 4014 binary, CSV export."""

from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
)
from reasitic.exports import write_tek4014, write_tek4014_file
from reasitic.optimise import (
    sweep_square_spiral,
    sweep_to_csv,
    sweep_to_tsv,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Tek 4014 -------------------------------------------------------------


def test_tek4014_returns_bytes(tech) -> None:
    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=2, tech=tech, metal="m3"
    )
    data = write_tek4014([sp])
    assert isinstance(data, bytes)
    # Starts with GS = 0x1D (graphics-mode entry)
    assert data[0] == 0x1D
    # Ends with US = 0x1F
    assert data[-1] == 0x1F


def test_tek4014_empty_shape_list_returns_empty() -> None:
    assert write_tek4014([]) == b""


def test_tek4014_writes_to_file(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "L1", length=100, width=10, spacing=2, turns=1, tech=tech, metal="m3"
    )
    out = tmp_path / "L1.tek"
    write_tek4014_file(out, [sp])
    data = out.read_bytes()
    assert len(data) > 0
    assert data[0] == 0x1D


def test_tek4014_addressed_vector_bytes_in_range(tech) -> None:
    """The 4-byte addressed-vector format uses specific bit ranges:
    HiY = 0x20–0x3F, LoY = 0x60–0x7F, HiX = 0x20–0x3F, LoX = 0x40–0x5F."""
    sp = square_spiral(
        "L", length=100, width=10, spacing=2, turns=1, tech=tech, metal="m3"
    )
    data = write_tek4014([sp])
    # Skip the leading GS byte
    body = data[1:-1]
    # Bytes come in groups of 4
    for i in range(0, len(body), 4):
        if i + 3 >= len(body):
            break
        hi_y, lo_y, hi_x, lo_x = body[i:i + 4]
        # Skip GS bytes that delimit polygons
        if hi_y == 0x1D:
            continue
        assert 0x20 <= hi_y <= 0x3F or hi_y == 0x1D
        assert 0x60 <= lo_y <= 0x7F or lo_y == 0x1D
        assert 0x20 <= hi_x <= 0x3F or hi_x == 0x1D
        assert 0x40 <= lo_x <= 0x5F or lo_x == 0x1D


# CSV / TSV ------------------------------------------------------------


def test_sweep_to_csv_uses_commas(tech) -> None:
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0, 150.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[2.0, 3.0],
        freq_ghz=2.0,
        metal="m3",
    )
    csv = sweep_to_csv(arr)
    lines = csv.splitlines()
    # Header has 6 columns separated by commas
    assert lines[0].count(",") == 5
    assert "length_um,width_um" in lines[0]


def test_sweep_to_tsv_uses_tabs(tech) -> None:
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[2.0],
        freq_ghz=2.0,
        metal="m3",
    )
    tsv = sweep_to_tsv(arr)
    assert "\t" in tsv
    assert "," not in tsv.split("\n")[0]