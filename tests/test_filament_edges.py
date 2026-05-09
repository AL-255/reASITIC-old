"""Edge-case + branch-coverage tests for the filament solver."""

from __future__ import annotations

import math

import numpy as np
import pytest

import reasitic
from reasitic import (
    Shape,
    parse_tech_file,
    square_spiral,
)
from reasitic.geometry import Point, Polygon, Segment
from reasitic.inductance import (
    Filament,
    auto_filament_subdivisions,
    build_inductance_matrix,
    filament_grid,
    solve_inductance_matrix,
    solve_inductance_mna,
)
from reasitic.inductance.filament import _filament_pair_m
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


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
# _filament_pair_m -------------------------------------------------------


class TestFilamentPairM:
    def test_too_close_returns_zero(self):
        """Filaments with separation < 1e-4 μm should return 0
        (the singular-pair guard at line 199)."""
        a = Filament(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        # Sub-Angstrom separation
        b = Filament(
            a=Point(0, 1e-12, 0), b=Point(100, 1e-12, 0),
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        assert _filament_pair_m(a, b) == 0.0

    def test_perpendicular_returns_zero(self):
        """Non-parallel pair (perpendicular) → not handled by the
        Greenhouse summation here, returns 0."""
        a = Filament(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        b = Filament(
            a=Point(50, 0, 0), b=Point(50, 100, 0),
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        assert _filament_pair_m(a, b) == 0.0

    def test_zero_length_filament_returns_zero(self):
        a = Filament(
            a=Point(0, 0, 0), b=Point(0, 0, 0),  # zero length
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        b = Filament(
            a=Point(0, 10, 0), b=Point(100, 10, 0),
            width=1.0, thickness=1.0, metal=0, parent_segment=0,
        )
        assert _filament_pair_m(a, b) == 0.0


# solve_inductance_mna ---------------------------------------------------


class TestSolveInductanceMna:
    def test_empty_shape_returns_zeros(self, tech):
        empty = Shape(name="EMPTY")
        L, R = solve_inductance_mna(empty, tech, freq_ghz=2.0)
        assert L == 0.0
        assert R == 0.0

    def test_zero_length_segments_returns_zeros(self, tech):
        """A shape with all-zero-length segments has no filaments."""
        sh = Shape(
            name="ZERO",
            polygons=[
                Polygon(
                    vertices=[
                        Point(0, 0, 0), Point(0, 0, 0), Point(0, 0, 0),
                    ],
                    metal=0,
                )
            ],
        )
        L, R = solve_inductance_mna(sh, tech, freq_ghz=2.0)
        assert L == 0.0
        assert R == 0.0

    def test_dc_path_works(self, tech):
        """freq_ghz = 0 takes the DC branch (real-valued solve).

        At DC the imaginary-part of Z is zero so L_eff_nH is reported
        as 0 by design; only R is meaningful.
        """
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        L, R = solve_inductance_mna(sp, tech, freq_ghz=0.0)
        # DC: L is reported as 0 (imag(Z)/omega → 0/0 sentinel)
        assert L == 0.0
        # R is the DC sheet-resistance sum
        assert R > 0

    def test_dc_lstsq_fallback_when_solve_raises(self, tech, monkeypatch):
        """Force np.linalg.solve to raise so the lstsq fallback runs."""
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        # Patch np.linalg.solve to always raise
        from reasitic.inductance import filament as fil

        original_solve = np.linalg.solve

        def _bad_solve(A, b):
            raise np.linalg.LinAlgError("forced singular")

        monkeypatch.setattr(fil.np.linalg, "solve", _bad_solve)
        L, R = solve_inductance_mna(sp, tech, freq_ghz=0.0)
        # The lstsq fallback should still produce finite values
        assert np.isfinite(L)
        assert np.isfinite(R)
        # Restore (for any other tests sharing the monkeypatch)
        monkeypatch.setattr(fil.np.linalg, "solve", original_solve)

    def test_ac_lstsq_fallback_when_solve_raises(self, tech, monkeypatch):
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        from reasitic.inductance import filament as fil

        def _bad_solve(A, b):
            raise np.linalg.LinAlgError("forced singular")

        monkeypatch.setattr(fil.np.linalg, "solve", _bad_solve)
        L, R = solve_inductance_mna(sp, tech, freq_ghz=2.0)
        assert np.isfinite(L)
        assert np.isfinite(R)


# solve_inductance_matrix ----------------------------------------------


class TestSolveInductanceMatrix:
    def test_empty_shape_returns_zeros(self, tech):
        empty = Shape(name="EMPTY")
        L, R = solve_inductance_matrix(empty, tech, freq_ghz=2.0)
        assert L == 0.0
        assert R == 0.0

    def test_zero_length_segments_returns_zeros(self, tech):
        sh = Shape(
            name="ZERO",
            polygons=[
                Polygon(
                    vertices=[
                        Point(0, 0, 0), Point(0, 0, 0), Point(0, 0, 0),
                    ],
                    metal=0,
                )
            ],
        )
        L, R = solve_inductance_matrix(sh, tech, freq_ghz=2.0)
        assert L == 0.0
        assert R == 0.0

    def test_subdivided_path_with_inv_fallback(self, tech, monkeypatch):
        """With n_w·n_t > 1 the per-parent inv() is invoked. Patch
        np.linalg.inv to always raise so the fallback continue branch
        is hit."""
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        from reasitic.inductance import filament as fil

        def _bad_inv(M):
            raise np.linalg.LinAlgError("forced singular")

        monkeypatch.setattr(fil.np.linalg, "inv", _bad_inv)
        # Should not raise — the function should fall through the
        # `continue` branch instead of inverting.
        L, R = solve_inductance_matrix(
            sp, tech, freq_ghz=2.0, n_w=2, n_t=1,
        )
        assert np.isfinite(L)
        assert np.isfinite(R)

    def test_subdivided_path_normal(self, tech):
        """Sanity: the n_w=2 path produces finite results normally."""
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        L, R = solve_inductance_matrix(
            sp, tech, freq_ghz=2.0, n_w=2, n_t=2,
        )
        assert L > 0
        assert R > 0
