"""Tests for info commands: ListSegs, MetArea, LRMAT."""

import numpy as np
import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.info import (
    format_lr_matrix,
    format_segments,
    list_segments,
    lr_matrix,
    metal_area,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Metal area -------------------------------------------------------------


def test_metal_area_wire_is_zero(tech) -> None:
    """A 2-vertex wire has no enclosed area."""
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    assert metal_area(w) == 0.0


def test_metal_area_square_loop(tech) -> None:
    """A 1-turn 100 μm square spiral has 100×100 = 10000 μm² area
    in the closed loop — the shoelace gives the polygon enclosure."""
    sp = square_spiral(
        "S", length=100, width=10, spacing=3, turns=1, tech=tech, metal="m3"
    )
    area = metal_area(sp)
    # Outer box of 100 × 100 = 10000 μm²
    assert area == pytest.approx(10000.0, rel=1e-6)


# List segments ----------------------------------------------------------


def test_list_segments_counts(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    segs = list_segments(sp)
    # 2 turns × 4 segments per turn = 8
    assert len(segs) == 8
    assert all("length" in s for s in segs)
    assert segs[0]["index"] == 0


def test_format_segments_text_format(tech) -> None:
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = format_segments(w)
    assert "W1" in text
    assert "1 segments" in text
    assert "100" in text  # length


# LRMAT ------------------------------------------------------------------


def test_lr_matrix_shape(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    M = lr_matrix(sp)
    assert M.shape == (8, 8)
    np.testing.assert_allclose(M, M.T, atol=1e-12)


def test_lr_matrix_diagonal_positive(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    M = lr_matrix(sp)
    for i in range(M.shape[0]):
        assert M[i, i] > 0


def test_lr_matrix_sum_matches_self_inductance(tech) -> None:
    """The sum of all (signed) entries of the partial-L matrix is
    the total self-inductance."""
    from reasitic import compute_self_inductance

    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    M = lr_matrix(sp)
    L_sum = float(M.sum())
    L_direct = compute_self_inductance(sp)
    assert L_sum == pytest.approx(L_direct, rel=1e-9)


def test_format_lr_matrix_text(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = format_lr_matrix(sp)
    assert "Partial-inductance matrix" in text
    # 8 rows in the matrix → 9 lines (8 data + 1 header)
    assert text.count("\n") == 9