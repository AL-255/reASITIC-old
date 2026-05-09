"""Tests for the per-segment substrate-cap pipeline."""

from __future__ import annotations

import math

import numpy as np
import pytest

import reasitic
from reasitic.geometry import Point, Segment
from reasitic.substrate import (
    SegmentCapResult,
    analyze_capacitance_driver,
    analyze_capacitance_polygon,
    capacitance_integral_inner_a,
    capacitance_integral_inner_b,
    capacitance_per_segment,
    capacitance_segment_integral,
    capacitance_setup,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def two_caps(tech):
    a = reasitic.capacitor(
        "A", length=20, width=20,
        metal_top="m3", metal_bottom="m2", tech=tech,
    ).translate(50, 50)
    b = reasitic.capacitor(
        "B", length=20, width=20,
        metal_top="m3", metal_bottom="m2", tech=tech,
    ).translate(120, 50)
    return a, b


# capacitance_setup ------------------------------------------------------


class TestCapacitanceSetup:
    def test_flattens_polygons_to_segments(self, tech, two_caps):
        a, _ = two_caps
        segs, names = capacitance_setup([a], tech)
        assert all(isinstance(s, Segment) for s in segs)
        assert all(n == "A" for n in names)
        assert len(segs) == len(names)

    def test_excludes_via_segments(self, tech, two_caps):
        """Vias are skipped in the cap matrix — only metal segments."""
        a, _ = two_caps
        segs, _ = capacitance_setup([a], tech)
        n_metals = len(tech.metals)
        for s in segs:
            assert 0 <= s.metal < n_metals

    def test_dict_input(self, tech, two_caps):
        a, b = two_caps
        _, names = capacitance_setup({"A": a, "B": b}, tech)
        assert set(names) == {"A", "B"}

    def test_empty_input_returns_empty(self, tech):
        segs, names = capacitance_setup([], tech)
        assert segs == []
        assert names == []


# capacitance_segment_integral -------------------------------------------


class TestCapacitanceSegmentIntegral:
    def test_returns_finite(self, tech):
        seg_a = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        seg_b = Segment(
            a=Point(50, 0, 5), b=Point(60, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        v = capacitance_segment_integral(seg_a, seg_b, tech)
        assert math.isfinite(v) and v > 0

    def test_decreases_with_separation(self, tech):
        """Farther segments have smaller potential coupling."""
        seg_a = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        v_close = capacitance_segment_integral(
            seg_a,
            Segment(a=Point(20, 0, 5), b=Point(30, 0, 5),
                    width=2.0, thickness=1.0, metal=0),
            tech,
        )
        v_far = capacitance_segment_integral(
            seg_a,
            Segment(a=Point(200, 0, 5), b=Point(210, 0, 5),
                    width=2.0, thickness=1.0, metal=0),
            tech,
        )
        assert v_far < v_close

    def test_invalid_n_div_raises(self, tech):
        seg = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        with pytest.raises(ValueError):
            capacitance_segment_integral(seg, seg, tech, n_div=0)

    def test_via_segment_returns_zero(self, tech):
        """A segment whose metal index is out of range (i.e. via)
        contributes zero."""
        seg_via = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=999,
        )
        seg_metal = Segment(
            a=Point(50, 0, 5), b=Point(60, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        assert capacitance_segment_integral(seg_via, seg_metal, tech) == 0.0


# Inner kernels ----------------------------------------------------------


class TestInnerKernels:
    def test_inner_a_returns_finite(self, tech):
        seg_a = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        seg_b = Segment(
            a=Point(50, 0, 5), b=Point(60, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        v = capacitance_integral_inner_a(seg_a, seg_b, tech, s=0.5)
        assert math.isfinite(v) and v > 0

    def test_inner_b_returns_finite(self, tech):
        seg_a = Segment(
            a=Point(0, 0, 5), b=Point(10, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        seg_b = Segment(
            a=Point(50, 0, 5), b=Point(60, 0, 5),
            width=2.0, thickness=1.0, metal=0,
        )
        v = capacitance_integral_inner_b(seg_a, seg_b, tech, t=0.5)
        assert math.isfinite(v) and v > 0


# capacitance_per_segment ------------------------------------------------


class TestCapacitancePerSegment:
    def test_returns_symmetric_matrix(self, tech, two_caps):
        a, _ = two_caps
        segs, _ = capacitance_setup([a], tech)
        P = capacitance_per_segment(segs, tech)
        assert P.shape == (len(segs), len(segs))
        np.testing.assert_allclose(P, P.T, atol=1e-12)

    def test_diagonal_largest_in_each_row(self, tech, two_caps):
        """Self-coupling should dominate for typical geometries."""
        a, _ = two_caps
        segs, _ = capacitance_setup([a], tech)
        P = capacitance_per_segment(segs, tech)
        # Most diagonal entries should be ≥ off-diagonal in their row
        diag_dominant = sum(
            P[i, i] >= np.max(np.delete(P[i], i))
            for i in range(len(segs))
        )
        assert diag_dominant >= len(segs) // 2

    def test_empty_segs_returns_empty_matrix(self, tech):
        P = capacitance_per_segment([], tech)
        assert P.shape == (0, 0)


# analyze_capacitance_driver ---------------------------------------------


class TestAnalyzeCapacitanceDriver:
    def test_returns_segment_cap_result(self, tech, two_caps):
        a, b = two_caps
        result = analyze_capacitance_driver([a, b], tech)
        assert isinstance(result, SegmentCapResult)
        assert result.P_matrix.shape == (
            len(result.segments), len(result.segments)
        )
        assert result.C_matrix.shape == result.P_matrix.shape

    def test_pinv_inverse_relation(self, tech, two_caps):
        """C should be a (pseudo-)inverse of P."""
        a, _ = two_caps
        result = analyze_capacitance_driver([a], tech)
        N = result.P_matrix.shape[0]
        if N >= 2:
            # P · C ≈ I (modulo small singular values for big N)
            check = result.P_matrix @ result.C_matrix
            # Diagonals should be near 1
            np.testing.assert_allclose(np.diag(check), 1.0, atol=1e-3)

    def test_polygon_alias(self, tech, two_caps):
        a, b = two_caps
        r1 = analyze_capacitance_driver([a, b], tech)
        r2 = analyze_capacitance_polygon([a, b], tech)
        np.testing.assert_allclose(r1.P_matrix, r2.P_matrix)

    def test_empty_input(self, tech):
        result = analyze_capacitance_driver([], tech)
        assert result.P_matrix.shape == (0, 0)
        assert result.segments == []
