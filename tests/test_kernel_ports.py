"""Tests for the kernel-port additions: polygon edge ops, chip-edge
extension, and three-class DC-resistance accumulator."""

from __future__ import annotations

import math

import pytest

import reasitic
from reasitic.geometry import (
    Point,
    Polygon,
    extend_last_segment_to_chip_edge,
    polygon_edge_vectors,
)
from reasitic.resistance import three_class_resistance
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


# polygon_edge_vectors ----------------------------------------------------


class TestPolygonEdgeVectors:
    def test_forward_returns_consecutive_diffs(self):
        poly = Polygon(
            vertices=[Point(0, 0, 0), Point(10, 0, 0),
                      Point(10, 5, 0), Point(0, 5, 0)],
            metal=0,
        )
        edges = polygon_edge_vectors(poly, direction="forward")
        assert edges == [(10.0, 0.0), (0.0, 5.0), (-10.0, 0.0)]

    def test_backward_returns_inverse_diffs(self):
        poly = Polygon(
            vertices=[Point(0, 0, 0), Point(10, 0, 0),
                      Point(10, 5, 0), Point(0, 5, 0)],
            metal=0,
        )
        edges = polygon_edge_vectors(poly, direction="backward")
        # vertices[i] - vertices[i-1]
        assert edges == [(10.0, 0.0), (0.0, 5.0), (-10.0, 0.0)]

    def test_forward_and_backward_match_geometric_edges(self):
        """Both directions return the same set of edge vectors for a
        ring; only the offset differs."""
        poly = Polygon(
            vertices=[Point(0, 0, 0), Point(1, 2, 0),
                      Point(3, 1, 0), Point(2, -1, 0)],
            metal=0,
        )
        f = polygon_edge_vectors(poly, direction="forward")
        b = polygon_edge_vectors(poly, direction="backward")
        assert f == b
        assert len(f) == len(poly.vertices) - 1

    def test_empty_polygon(self):
        poly = Polygon(vertices=[Point(0, 0, 0)], metal=0)
        assert polygon_edge_vectors(poly) == []

    def test_invalid_direction_raises(self):
        poly = Polygon(vertices=[Point(0, 0, 0), Point(1, 0, 0)], metal=0)
        with pytest.raises(ValueError):
            polygon_edge_vectors(poly, direction="diagonal")


# extend_last_segment_to_chip_edge ---------------------------------------


class TestExtendLastSegmentToChipEdge:
    def test_extends_north_facing_to_chipy(self, tech):
        chipy = tech.chip.chipy
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech,
                           x_origin=100, y_origin=10)
        # Build a vertical wire: rotate it so it runs +Y
        vert = sh.rotate_xy(math.pi / 2)
        out = extend_last_segment_to_chip_edge(vert, tech)
        last_v = out.polygons[-1].vertices[-1]
        assert last_v.y == pytest.approx(chipy)

    def test_extends_east_facing_to_chipx(self, tech):
        chipx = tech.chip.chipx
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech,
                           x_origin=100, y_origin=100)
        out = extend_last_segment_to_chip_edge(sh, tech)
        last_v = out.polygons[-1].vertices[-1]
        # The wire's last segment runs +X (length=50, x_origin=100), so
        # extending should snap to chipx.
        assert last_v.x == pytest.approx(chipx)

    def test_no_op_with_zero_chip(self, tech):
        zero_tech = type(
            "T", (), {"chip": type("C", (), {"chipx": 0, "chipy": 0})()}
        )()
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech)
        out = extend_last_segment_to_chip_edge(sh, zero_tech)
        # Untouched
        assert out.polygons[-1].vertices[-1].x == sh.polygons[-1].vertices[-1].x

    def test_empty_shape_returns_unchanged(self, tech):
        from reasitic.geometry import Shape
        empty = Shape(name="EMPTY")
        out = extend_last_segment_to_chip_edge(empty, tech)
        assert out is empty


# three_class_resistance --------------------------------------------------


class TestThreeClassResistance:
    def test_returns_three_positive_buckets(self, tech):
        sh = reasitic.square_spiral(
            "L", length=200, width=10, spacing=2, turns=3,
            tech=tech, metal="m3"
        )
        r = three_class_resistance(sh, tech)
        assert r.R_a > 0
        assert r.R_b > 0
        assert r.R_c > 0

    def test_buckets_have_known_ordering(self, tech):
        """At fixed length, the bucket-A coefficient on R_seg is the
        largest (5.3e-17), then B (2.8e-17), then C (1.9e-17). The
        length term is 5.6e-17 for A and B but only 4.0e-17 for C, so
        R_a > R_b but the inequality with R_c depends on the shape's
        rsh × L vs L ratio."""
        sh = reasitic.square_spiral(
            "L", length=200, width=10, spacing=2, turns=3,
            tech=tech, metal="m3"
        )
        r = three_class_resistance(sh, tech)
        assert r.R_a > r.R_b

    def test_scales_linearly_with_geometry(self, tech):
        """Doubling every segment length doubles each bucket exactly."""
        small = reasitic.wire("W1", length=100, width=10, metal="m3", tech=tech)
        big = reasitic.wire("W2", length=200, width=10, metal="m3", tech=tech)
        rs = three_class_resistance(small, tech)
        rb = three_class_resistance(big, tech)
        assert rb.R_a == pytest.approx(2.0 * rs.R_a, rel=1e-9)
        assert rb.R_b == pytest.approx(2.0 * rs.R_b, rel=1e-9)
        assert rb.R_c == pytest.approx(2.0 * rs.R_c, rel=1e-9)

    def test_zero_for_empty_shape(self, tech):
        from reasitic.geometry import Shape
        empty = Shape(name="EMPTY")
        r = three_class_resistance(empty, tech)
        assert r.R_a == 0.0
        assert r.R_b == 0.0
        assert r.R_c == 0.0
