"""Tests for the general-3D / orthogonal segment-pair mutual kernels."""

from __future__ import annotations

import math

import pytest

from reasitic.geometry import Point, Segment
from reasitic.inductance import (
    mutual_inductance_3d_segments,
    mutual_inductance_orthogonal_segments,
    mutual_inductance_skew_segments,
    parallel_segment_mutual,
)

# Skew (general 3-D) -----------------------------------------------------


class TestSkewSegments:
    def test_perpendicular_in_plane_returns_zero(self):
        """Two perpendicular line filaments in the same plane have
        cos(α) = 0 → M = 0."""
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(50, 50, 0), Point(50, 150, 0)
        m = mutual_inductance_skew_segments(a1, a2, b1, b2)
        assert m == pytest.approx(0.0, abs=1e-12)

    def test_zero_length_segment_returns_zero(self):
        a1, a2 = Point(0, 0, 0), Point(0, 0, 0)
        b1, b2 = Point(10, 10, 0), Point(20, 20, 0)
        m = mutual_inductance_skew_segments(a1, a2, b1, b2)
        assert m == 0.0

    def test_parallel_segments_match_closed_form(self):
        """Parallel-filament kernel must match
        :func:`parallel_segment_mutual` to high precision."""
        # Two parallel filaments along x-axis, separation 10 μm in y
        L = 100.0
        sep = 10.0
        a1, a2 = Point(0, 0, 0), Point(L, 0, 0)
        b1, b2 = Point(0, sep, 0), Point(L, sep, 0)

        m_skew = mutual_inductance_skew_segments(a1, a2, b1, b2)
        m_grover = parallel_segment_mutual(L, L, sep)
        assert m_skew == pytest.approx(m_grover, rel=1e-6)

    def test_parallel_with_offset_matches_grover(self):
        L1, L2, sep, offset = 100.0, 80.0, 5.0, 30.0
        a1, a2 = Point(0, 0, 0), Point(L1, 0, 0)
        b1, b2 = Point(offset, sep, 0), Point(offset + L2, sep, 0)
        m_skew = mutual_inductance_skew_segments(a1, a2, b1, b2)
        m_grover = parallel_segment_mutual(L1, L2, sep, offset)
        assert m_skew == pytest.approx(m_grover, rel=1e-6)

    def test_anti_parallel_returns_negative(self):
        """Reversing one filament's direction flips the sign of M."""
        L, sep = 100.0, 10.0
        a1, a2 = Point(0, 0, 0), Point(L, 0, 0)
        b1, b2 = Point(L, sep, 0), Point(0, sep, 0)  # reversed
        m_anti = mutual_inductance_skew_segments(a1, a2, b1, b2)
        # Compare with parallel
        b1f, b2f = Point(0, sep, 0), Point(L, sep, 0)
        m_par = mutual_inductance_skew_segments(a1, a2, b1f, b2f)
        assert m_anti == pytest.approx(-m_par, rel=1e-6)

    def test_symmetry(self):
        """M(A, B) == M(B, A) under filament-direction swap."""
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(40, 20, 5), Point(80, 60, 5)  # skew in z
        m_ab = mutual_inductance_skew_segments(a1, a2, b1, b2)
        m_ba = mutual_inductance_skew_segments(b1, b2, a1, a2)
        assert m_ab == pytest.approx(m_ba, rel=1e-6)

    def test_translation_invariance(self):
        """Translating both filaments by the same vector preserves M."""
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(20, 50, 0), Point(120, 50, 0)
        m0 = mutual_inductance_skew_segments(a1, a2, b1, b2)

        dx, dy, dz = 33.0, -17.0, 4.0
        a1p = Point(a1.x + dx, a1.y + dy, a1.z + dz)
        a2p = Point(a2.x + dx, a2.y + dy, a2.z + dz)
        b1p = Point(b1.x + dx, b1.y + dy, b1.z + dz)
        b2p = Point(b2.x + dx, b2.y + dy, b2.z + dz)
        m1 = mutual_inductance_skew_segments(a1p, a2p, b1p, b2p)
        assert m1 == pytest.approx(m0, rel=1e-6)

    def test_distant_skew_decreases_with_distance(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        # 45° tilted segments at increasing z heights
        ms = []
        for z in (10, 50, 200):
            b1 = Point(0, 0, z)
            b2 = Point(70, 70, z)
            ms.append(abs(mutual_inductance_skew_segments(a1, a2, b1, b2)))
        assert ms[0] > ms[1] > ms[2]

    def test_skew_at_45_degrees_is_finite_nonzero(self):
        """A 45° skew filament a few μm above another should produce
        a small but non-zero M."""
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 0, 10), Point(70.71, 70.71, 10)
        m = mutual_inductance_skew_segments(a1, a2, b1, b2)
        assert math.isfinite(m)
        # Coupling through 45° at z=10 should be smaller than
        # parallel-overlapping with sep=10
        m_par = mutual_inductance_skew_segments(
            a1, a2, Point(0, 0, 10), Point(100, 0, 10)
        )
        assert abs(m) < abs(m_par)


# Orthogonal -------------------------------------------------------------


class TestOrthogonalSegments:
    def test_returns_zero_for_perpendicular(self):
        """Line-filament limit: M = 0 for perpendicular pairs."""
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(50, 0, 0), Point(50, 100, 0)
        m = mutual_inductance_orthogonal_segments(a1, a2, b1, b2)
        assert m == 0.0

    def test_rejects_non_perpendicular(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 0, 0), Point(100, 0, 0)  # parallel, not orthogonal
        with pytest.raises(ValueError):
            mutual_inductance_orthogonal_segments(a1, a2, b1, b2)


# Segment dispatcher -----------------------------------------------------


class TestThreeDSegmentDispatcher:
    def test_uses_skew_kernel_internally(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 10, 0), Point(100, 10, 0)
        seg_a = Segment(a=a1, b=a2, width=0.0, thickness=0.0, metal=0)
        seg_b = Segment(a=b1, b=b2, width=0.0, thickness=0.0, metal=0)
        m_seg = mutual_inductance_3d_segments(seg_a, seg_b)
        m_pts = mutual_inductance_skew_segments(a1, a2, b1, b2)
        assert m_seg == pytest.approx(m_pts, rel=1e-9)
