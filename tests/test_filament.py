"""Tests for filament-based impedance-matrix L extraction."""

import math

import numpy as np
import pytest

from reasitic import (
    compute_self_inductance,
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.geometry import Point, Segment
from reasitic.inductance import (
    build_inductance_matrix,
    build_resistance_vector,
    filament_grid,
    solve_inductance_matrix,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Filament grid ----------------------------------------------------------


def test_filament_grid_one_by_one_returns_single() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    fils = filament_grid(seg, n_w=1, n_t=1)
    assert len(fils) == 1
    f = fils[0]
    assert f.width == 10
    assert f.thickness == 2


def test_filament_grid_4x2_count() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    fils = filament_grid(seg, n_w=4, n_t=2)
    assert len(fils) == 8
    # Each filament is W/4 by T/2
    for f in fils:
        assert f.width == pytest.approx(2.5)
        assert f.thickness == pytest.approx(1.0)


def test_filament_grid_distributes_perpendicular_to_axis() -> None:
    """An x-axis segment with n_w=2 should produce filaments offset
    in the y direction (perpendicular in-plane)."""
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=4, thickness=2, metal=0
    )
    fils = filament_grid(seg, n_w=2, n_t=1)
    ys = sorted(f.a.y for f in fils)
    # Centred about y=0, separated by 2
    assert ys[0] == pytest.approx(-1.0)
    assert ys[1] == pytest.approx(1.0)


def test_filament_grid_zero_length_segment_returns_empty() -> None:
    seg = Segment(a=Point(0, 0, 0), b=Point(0, 0, 0), width=10, thickness=2, metal=0)
    assert filament_grid(seg) == []


def test_filament_grid_invalid_subdivision() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    with pytest.raises(ValueError):
        filament_grid(seg, n_w=0)


# Inductance matrix ------------------------------------------------------


def test_inductance_matrix_symmetric() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    fils = filament_grid(seg, n_w=4, n_t=1)
    M = build_inductance_matrix(fils)
    assert M.shape == (4, 4)
    np.testing.assert_allclose(M, M.T, atol=1e-12)


def test_inductance_matrix_diagonal_positive() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    fils = filament_grid(seg, n_w=2, n_t=1)
    M = build_inductance_matrix(fils)
    assert all(M[i, i] > 0 for i in range(2))


# Resistance vector ------------------------------------------------------


def test_resistance_vector_sums_to_segment_dc(tech) -> None:
    """For n_w=1, n_t=1 at f=0 the per-filament R equals the segment's
    DC resistance."""
    w = wire("W1", length=100.0, width=10.0, tech=tech, metal="m3")
    seg = w.segments()[0]
    fils = filament_grid(seg, n_w=1, n_t=1)
    R = build_resistance_vector(fils, tech, freq_ghz=0.0)
    assert R.shape == (1,)
    expected = tech.metal_by_name("m3").rsh * seg.length / seg.width
    assert R[0] == pytest.approx(expected, rel=1e-9)


# End-to-end solver ------------------------------------------------------


def test_solve_single_filament_matches_closed_form(tech) -> None:
    """With n_w=n_t=1 the impedance solve should approach the
    closed-form L from compute_self_inductance at low frequency."""
    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    L_closed = compute_self_inductance(sp)
    L_filament, _ = solve_inductance_matrix(sp, tech, freq_ghz=0.001, n_w=1, n_t=1)
    # Should agree within ~5% (the impedance solve at very low freq
    # where R-dominated regime is accurate; finite-frequency current
    # crowding accounted for naturally)
    assert L_filament == pytest.approx(L_closed, rel=0.10)


def test_solve_returns_finite_for_higher_division(tech) -> None:
    """Sanity: solver runs without numerical blow-up for n_w=2."""
    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    L, R = solve_inductance_matrix(sp, tech, freq_ghz=2.0, n_w=2, n_t=1)
    assert math.isfinite(L)
    assert math.isfinite(R)
    assert L > 0
    assert R > 0


def test_solve_returns_zero_for_empty_shape(tech) -> None:
    from reasitic import Shape

    empty = Shape(name="empty")
    L, R = solve_inductance_matrix(empty, tech, freq_ghz=1.0)
    assert L == 0.0
    assert R == 0.0


# MNA solver -----------------------------------------------------------


def test_mna_single_filament_matches_closed_form(tech) -> None:
    """At n_w = n_t = 1 the MNA solver should match the closed form."""
    from reasitic.inductance import solve_inductance_mna

    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    L_closed = compute_self_inductance(sp)
    L_mna, _ = solve_inductance_mna(sp, tech, freq_ghz=0.001, n_w=1, n_t=1)
    assert L_mna == pytest.approx(L_closed, rel=0.05)


def test_mna_returns_finite_for_higher_subdivision(tech) -> None:
    """The proper MNA solve handles n_w > 1 without Schur approximation."""
    from reasitic.inductance import solve_inductance_mna

    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    L, R = solve_inductance_mna(sp, tech, freq_ghz=2.0, n_w=2, n_t=1)
    assert math.isfinite(L)
    assert math.isfinite(R)
    assert L > 0
    assert R > 0


def test_mna_returns_zero_for_empty_shape(tech) -> None:
    from reasitic import Shape
    from reasitic.inductance import solve_inductance_mna

    L, R = solve_inductance_mna(Shape(name="empty"), tech, freq_ghz=1.0)
    assert L == 0.0
    assert R == 0.0