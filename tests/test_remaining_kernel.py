"""Tests for the final remaining kernel ports."""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.inductance import auto_filament_subdivisions_critical
from reasitic.network import (
    back_substitute_solution,
    build_segment_node_list,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal="m3"
    )


# back_substitute_solution -----------------------------------------------


class TestBackSubstituteSolution:
    def test_passthrough_no_perm(self):
        x = np.array([1, 2, 3, 4], dtype=complex)
        out = back_substitute_solution(x)
        np.testing.assert_array_equal(out, x)

    def test_with_bias(self):
        x = np.array([1, 2, 3], dtype=complex)
        out = back_substitute_solution(x, bias=10.0)
        np.testing.assert_array_equal(out, [11, 12, 13])

    def test_node_index_permutation(self):
        x = np.array([10, 20, 30, 40], dtype=complex)
        out = back_substitute_solution(x, node_indices=[3, 1, 0])
        np.testing.assert_array_equal(out, [40, 20, 10])


# build_segment_node_list ------------------------------------------------


class TestBuildSegmentNodeList:
    def test_returns_one_entry_per_vertex(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        # Total = sum of vertex counts across polygons
        total_vertices = sum(len(p.vertices) for p in spiral.polygons)
        assert len(nodes) == total_vertices

    def test_metal_index_recorded(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        m3 = tech.metal_by_name("m3").index
        # Square spiral on m3 — every entry has metal == m3
        assert all(metal == m3 for _, _, metal in nodes)

    def test_polygon_indices_monotone(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        # poly indices go 0, 0, ..., 1, 1, ... — monotone non-decreasing
        prev = -1
        for pi, _, _ in nodes:
            assert pi >= prev
            prev = pi

    def test_empty_shape(self, tech):
        from reasitic.geometry import Shape
        out = build_segment_node_list(Shape(name="EMPTY"), tech)
        assert out == []


# auto_filament_subdivisions_critical ------------------------------------


class TestAutoFilamentSubdivisionsCritical:
    def test_critical_picks_finer_cells(self, spiral, tech):
        """Critical mode uses 2× cells-per-skin-depth, so it should
        produce subdivisions ≥ those of normal mode (capped by n_max)."""
        from reasitic.inductance import auto_filament_subdivisions
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w_n, n_t_n = auto_filament_subdivisions(
            seg, rsh, freq_ghz=10.0,
        )
        n_w_c, n_t_c = auto_filament_subdivisions_critical(
            seg, rsh, freq_ghz=10.0,
        )
        assert n_w_c >= n_w_n
        assert n_t_c >= n_t_n

    def test_returns_at_least_one_each(self, spiral, tech):
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w, n_t = auto_filament_subdivisions_critical(
            seg, rsh, freq_ghz=2.0,
        )
        assert n_w >= 1
        assert n_t >= 1

    def test_dc_returns_one_one(self, spiral, tech):
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w, n_t = auto_filament_subdivisions_critical(seg, rsh, freq_ghz=0.0)
        assert n_w == 1 and n_t == 1
