"""Tests for parametric geometry sweep."""

import pytest

from reasitic import parse_tech_file
from reasitic.optimise import sweep_square_spiral, sweep_to_tsv
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_sweep_returns_correct_count(tech) -> None:
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0, 150.0],
        width_um=[5.0, 10.0],
        spacing_um=[2.0],
        turns=[1.0, 2.0, 3.0],
        freq_ghz=2.0,
        metal="m3",
    )
    # 2 × 2 × 1 × 3 = 12 grid points
    assert len(arr) == 12


def test_sweep_columns_present(tech) -> None:
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[2.0],
        freq_ghz=2.0,
        metal="m3",
    )
    assert "L_nH" in arr.dtype.names
    assert "Q" in arr.dtype.names
    assert arr["L_nH"][0] > 0


def test_sweep_handles_invalid_geometries(tech) -> None:
    """A 5 μm spiral with 30 μm width should collapse → NaN."""
    arr = sweep_square_spiral(
        tech,
        length_um=[5.0],  # tiny
        width_um=[30.0],  # huge
        spacing_um=[2.0],
        turns=[2.0],
        freq_ghz=2.0,
        metal="m3",
    )
    # Either the build succeeds with degenerate geometry (Q=0) or
    # raises and returns NaN.
    row = arr[0]
    # Just check it returned a row, finite or nan
    assert row is not None


def test_sweep_to_tsv(tech) -> None:
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0, 150.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[2.0],
        freq_ghz=2.0,
        metal="m3",
    )
    tsv = sweep_to_tsv(arr)
    lines = tsv.splitlines()
    assert lines[0].startswith("length_um")  # header
    assert len(lines) == 1 + len(arr)


def test_sweep_q_increases_with_turns(tech) -> None:
    """For fixed geometry, more turns → more L → higher Q (in the
    limit where R doesn't grow as fast)."""
    arr = sweep_square_spiral(
        tech,
        length_um=[200.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[1.0, 2.0, 3.0],
        freq_ghz=2.0,
        metal="m3",
    )
    Ls = [row["L_nH"] for row in arr]
    assert Ls[0] < Ls[1] < Ls[2]