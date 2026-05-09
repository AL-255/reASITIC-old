"""Edge-case tests for the filament solver."""

import math
from pathlib import Path

import pytest

from reasitic import (
    Shape,
    parse_tech_file,
    square_spiral,
)
from reasitic.geometry import Point, Segment
from reasitic.inductance import (
    auto_filament_subdivisions,
    build_inductance_matrix,
    filament_grid,
    solve_inductance_matrix,
    solve_inductance_mna,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_filament_grid_zero_thickness(tech) -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0),
        width=10, thickness=0.001, metal=0,
    )
    fils = filament_grid(seg, n_w=2, n_t=1)
    assert len(fils) == 2
    for f in fils:
        assert math.isclose(f.thickness, 0.001)


def test_filament_grid_high_subdivision(tech) -> None:
    """4×4 = 16 sub-filaments still work."""
    seg = Segment(
        a=Point(0, 0, 0), b=Point(200, 0, 0),
        width=20, thickness=8, metal=2,
    )
    fils = filament_grid(seg, n_w=4, n_t=4)
    assert len(fils) == 16


def test_inductance_matrix_zero_for_empty() -> None:
    M = build_inductance_matrix([])
    assert M.shape == (0, 0)


def test_solve_converges_with_increasing_subdivision(tech) -> None:
    """L should converge as n_w increases. Check 1×1 vs 2×1 differ
    by < 20% (the proximity correction is finite but bounded)."""
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3",
    )
    L_1x1, _ = solve_inductance_mna(sp, tech, 0.001, n_w=1, n_t=1)
    L_2x1, _ = solve_inductance_mna(sp, tech, 0.001, n_w=2, n_t=1)
    # 2x1 typically captures slightly more proximity effect; should
    # be within ±20% of 1x1
    assert abs(L_2x1 - L_1x1) / max(abs(L_1x1), 1e-12) < 0.20


def test_auto_filament_subdivisions_high_freq() -> None:
    """At high frequency, auto subdivisions should hit the cap."""
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0),
        width=50, thickness=20, metal=2,
    )
    n_w, n_t = auto_filament_subdivisions(
        seg, rsh_ohm_per_sq=0.001, freq_ghz=50.0, n_max=8
    )
    assert n_w == 8 or n_t == 8


def test_solve_via_segment_returns_finite(tech) -> None:
    """A z-axis segment (via) shouldn't crash the solver."""
    from reasitic import via
    v = via("V", tech=tech, via_index=0)
    L, R = solve_inductance_matrix(v, tech, freq_ghz=1.0)
    assert math.isfinite(L)
    assert math.isfinite(R)


def test_solve_single_polygon_finite(tech) -> None:
    """A single-polygon shape (1 turn ring) should solve finitely."""
    from reasitic import ring
    r = ring("R", radius=50, width=5, sides=8, tech=tech, metal="m3")
    L, _R = solve_inductance_mna(r, tech, freq_ghz=1.0)
    assert math.isfinite(L)
    assert L > 0


def test_solve_empty_shape_returns_zero(tech) -> None:
    L, R = solve_inductance_mna(Shape(name="empty"), tech, freq_ghz=1.0)
    assert L == 0.0
    assert R == 0.0


def test_solve_at_zero_frequency(tech) -> None:
    """The solver's DC branch should still produce a sane R."""
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal="m3",
    )
    L, R = solve_inductance_mna(sp, tech, freq_ghz=0.0)
    assert math.isfinite(R)
    # L is undefined at DC; treated as 0 in our convention
    assert L == 0.0
