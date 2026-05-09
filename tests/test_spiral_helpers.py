"""Tests for spiral / cell-sizing helper ports."""

from __future__ import annotations

import math

import pytest

from reasitic.geometry import Point, Segment
from reasitic.spiral_helpers import (
    segment_pair_distance_metric,
    spiral_max_n,
    spiral_radius_for_n,
    spiral_turn_position,
    wire_position_periodic_fold,
)

# spiral_max_n -----------------------------------------------------------


class TestSpiralMaxN:
    def test_square_simple_geometry(self):
        """A 200×200 square with W=10, S=2 should fit ~16 turns."""
        n = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        assert math.isfinite(n)
        # Expected ~ L/(1+2(W+S)) = 200/25 = 8
        assert 5 < n < 15

    def test_polygon_uses_cosine(self):
        """Polygon with sides=8 should differ from square."""
        n_sq = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        n_oct = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type="polygon", sides=8,
        )
        assert n_sq != n_oct

    def test_unknown_spiral_type_raises(self):
        with pytest.raises(ValueError):
            spiral_max_n(
                outer_dim_um=200, width_um=10, spacing_um=2,
                spiral_type="zigzag",
            )

    def test_int_code_works(self):
        """The binary's integer code should also be accepted."""
        n_str = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        n_int = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type=0,  # SQUARE
        )
        assert n_str == pytest.approx(n_int)

    def test_unknown_int_returns_minus_one(self):
        """The decomp returns -1.0 on an unknown spiral_type code."""
        n = spiral_max_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type=99,
        )
        assert n == -1.0


# spiral_radius_for_n ----------------------------------------------------


class TestSpiralRadiusForN:
    def test_square_formula(self):
        r = spiral_radius_for_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        assert math.isfinite(r) and r > 0

    def test_polygon_formula(self):
        r = spiral_radius_for_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            sides=6, spiral_type="polygon",
        )
        assert math.isfinite(r) and r > 0

    def test_unknown_returns_huge(self):
        """The decomp returns 1e15 on unknown integer codes."""
        r = spiral_radius_for_n(
            outer_dim_um=200, width_um=10, spacing_um=2,
            spiral_type=99,
        )
        assert r == 1e15

    def test_polygon_zero_sides_raises(self):
        with pytest.raises(ValueError):
            spiral_radius_for_n(
                outer_dim_um=200, width_um=10, spacing_um=2,
                sides=0, spiral_type="polygon",
            )

    def test_radius_grows_with_outer_dim(self):
        r_small = spiral_radius_for_n(
            outer_dim_um=100, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        r_big = spiral_radius_for_n(
            outer_dim_um=400, width_um=10, spacing_um=2,
            spiral_type="square",
        )
        assert r_big > r_small


# spiral_turn_position ---------------------------------------------------


class TestSpiralTurnPosition:
    def test_first_turn_at_outer_edge(self):
        """i=1 with no fold gives 0.5*(L−W)."""
        p = spiral_turn_position(
            i=1, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        assert p == pytest.approx(0.5 * (200 - 10))

    def test_turn_decreases_inward(self):
        """Each subsequent turn shifts inward by (W + S)."""
        p1 = spiral_turn_position(
            i=1, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=20,
        )
        p2 = spiral_turn_position(
            i=2, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=20,
        )
        assert p1 - p2 == pytest.approx(12.0)  # W + S

    def test_recursion_negates_above_fold(self):
        """i above fold_size triggers reflection + negation."""
        p_below = spiral_turn_position(
            i=5, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        p_above = spiral_turn_position(
            i=15, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        # Reflected: (10*2 − 15) + 1 = 6, the turn at i=6 is below fold
        p_reflect = spiral_turn_position(
            i=6, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        assert p_above == pytest.approx(-p_reflect)
        assert p_above != pytest.approx(p_below)


# wire_position_periodic_fold --------------------------------------------


class TestWirePositionPeriodicFold:
    def test_within_fold_no_reflection(self):
        p = wire_position_periodic_fold(
            i=3, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        # outer−W − (W+S)·2·(i−1) = 200 − 10 − 12·2·2 = 142
        assert p == pytest.approx(142.0)

    def test_above_fold_reflects(self):
        p = wire_position_periodic_fold(
            i=15, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        # i=15 > 10 → reflect to 6, then evaluate
        expected = wire_position_periodic_fold(
            i=6, outer_dim_um=200, width_um=10, spacing_um=2,
            fold_size=10,
        )
        assert p == pytest.approx(expected)


# segment_pair_distance_metric -------------------------------------------


class TestSegmentPairDistanceMetric:
    def test_returns_int(self):
        seg = Segment(
            a=Point(100, 200, 0), b=Point(150, 350, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        m = segment_pair_distance_metric(seg)
        assert isinstance(m, int)

    def test_formula_matches_decomp(self):
        """((bx − ax) // 1000) + (by − ay) * 1000."""
        seg = Segment(
            a=Point(2000, 1000, 0), b=Point(5000, 4000, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        m = segment_pair_distance_metric(seg)
        # bx − ax = 3000 → //1000 = 3
        # by − ay = 3000 → ·1000 = 3,000,000
        assert m == 3 + 3_000_000

    def test_zero_segment_returns_zero(self):
        seg = Segment(
            a=Point(100, 100, 0), b=Point(100, 100, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        assert segment_pair_distance_metric(seg) == 0
