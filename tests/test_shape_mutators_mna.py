"""Tests for shape-mutation helpers and MNA / LMAT helper ports."""

from __future__ import annotations

import math

import numpy as np
import pytest

import reasitic
from reasitic.geometry import (
    Point,
    Polygon,
    Shape,
    emit_vias_at_layer_transitions,
    extend_terminal_segment,
)
from reasitic.network import (
    assemble_mna_matrix,
    lmat_compute_partial_traces,
    lmat_subblock_assemble,
    setup_mna_rhs,
    unpack_mna_solution_backward,
    unpack_mna_solution_forward,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


# extend_terminal_segment ------------------------------------------------


class TestExtendTerminalSegment:
    def test_extends_along_axis(self, tech):
        sh = reasitic.wire("W", length=100, width=2, metal="m3", tech=tech,
                           x_origin=0, y_origin=0)
        out = extend_terminal_segment(sh, dx_um=10.0)
        # Original wire goes (0,0,z)→(100,0,z). After extension,
        # last endpoint should be at length/2 + dx = 60 along the
        # axis from the *previous* vertex.
        last = out.polygons[-1].vertices[-1]
        prev = out.polygons[-1].vertices[-2]
        assert last.x == pytest.approx(prev.x + 60.0, rel=1e-9)

    def test_zero_dx_halves_segment(self, tech):
        sh = reasitic.wire("W", length=100, width=2, metal="m3", tech=tech)
        out = extend_terminal_segment(sh, dx_um=0.0)
        last = out.polygons[-1].vertices[-1]
        prev = out.polygons[-1].vertices[-2]
        d = math.sqrt((last.x - prev.x) ** 2 + (last.y - prev.y) ** 2)
        assert d == pytest.approx(50.0, rel=1e-9)

    def test_empty_shape_returns_unchanged(self):
        empty = Shape(name="EMPTY")
        assert extend_terminal_segment(empty) is empty

    def test_preserves_metadata(self, tech):
        sh = reasitic.wire("W", length=100, width=2, metal="m3", tech=tech,
                           x_origin=10, y_origin=20)
        out = extend_terminal_segment(sh, dx_um=5)
        assert out.name == "W"
        assert out.x_origin == 10
        assert out.y_origin == 20


# emit_vias_at_layer_transitions ----------------------------------------


class TestEmitViasAtLayerTransitions:
    def test_no_transitions_no_via(self, tech):
        sh = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=2,
            tech=tech, metal="m3"
        )
        out = emit_vias_at_layer_transitions(sh, tech)
        # All polygons on m3 → no via insertion
        assert len(out.polygons) == len(sh.polygons)

    def test_inserts_via_between_different_metals(self, tech):
        m2 = tech.metal_by_name("m2").index
        m3 = tech.metal_by_name("m3").index
        a = Polygon(
            vertices=[Point(0, 0, 0), Point(10, 0, 0), Point(10, 10, 0)],
            metal=m2,
        )
        b = Polygon(
            vertices=[Point(10, 10, 0), Point(20, 10, 0)],
            metal=m3,
        )
        sh = Shape(name="X", polygons=[a, b])
        out = emit_vias_at_layer_transitions(sh, tech)
        # Should be 3 polys: a, via, b
        assert len(out.polygons) == 3
        via = out.polygons[1]
        # Via metal index is past the metal-layer count
        assert via.metal >= len(tech.metals)

    def test_single_polygon_unchanged(self, tech):
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech)
        out = emit_vias_at_layer_transitions(sh, tech)
        assert len(out.polygons) == len(sh.polygons)


# assemble_mna_matrix ----------------------------------------------------


class TestAssembleMNAMatrix:
    def test_empty_branches(self):
        Y = assemble_mna_matrix(4)
        assert Y.shape == (4, 4)
        assert np.all(Y == 0)

    def test_single_branch_stamp(self):
        # Branch from node 0 to node 1 with admittance y = 0.02
        y = 0.02 + 0.005j
        Y = assemble_mna_matrix(2, branch_admittances=[(0, 1, y)])
        # MNA stamp:  Y[0,0] += y,  Y[1,1] += y,  Y[0,1] -= y, Y[1,0] -= y
        assert Y[0, 0] == y
        assert Y[1, 1] == y
        assert Y[0, 1] == -y
        assert Y[1, 0] == -y

    def test_ground_node_skipped(self):
        """A branch from node 0 to ground (-1) only stamps the diagonal."""
        Y = assemble_mna_matrix(2, branch_admittances=[(0, -1, 0.1 + 0j)])
        assert Y[0, 0] == 0.1 + 0j
        assert Y[1, 1] == 0
        # No off-diagonal stamps since the other end is ground
        assert Y[0, 1] == 0
        assert Y[1, 0] == 0


# setup_mna_rhs ---------------------------------------------------------


class TestSetupMNARHS:
    def test_empty_returns_zeros(self):
        b = setup_mna_rhs(5)
        assert b.shape == (5,)
        assert np.all(b == 0)

    def test_current_source_stamped(self):
        b = setup_mna_rhs(3, current_sources=[(1, 1.5 + 0.5j)])
        assert b[0] == 0
        assert b[1] == 1.5 + 0.5j
        assert b[2] == 0

    def test_out_of_range_index_ignored(self):
        b = setup_mna_rhs(3, current_sources=[(99, 1.0 + 0j)])
        assert np.all(b == 0)


# unpack_mna_solution_* -------------------------------------------------


class TestUnpackMNASolution:
    def test_forward_extracts_port_subset(self):
        x = np.array([1, 2, 3, 4, 5], dtype=complex)
        ports = unpack_mna_solution_forward(x, port_nodes=[0, 2, 4])
        np.testing.assert_array_equal(ports, np.array([1, 3, 5], dtype=complex))

    def test_forward_no_ports_returns_full(self):
        x = np.array([1, 2, 3], dtype=complex)
        out = unpack_mna_solution_forward(x)
        np.testing.assert_array_equal(out, x)

    def test_backward_pads_to_full(self):
        ports = np.array([10, 20], dtype=complex)
        full = unpack_mna_solution_backward(
            ports, port_nodes=[0, 3], n_nodes=5
        )
        np.testing.assert_array_equal(
            full, np.array([10, 0, 0, 20, 0], dtype=complex)
        )

    def test_round_trip(self):
        x_full = np.array([3, 5, 7, 9, 11], dtype=complex)
        ports = [1, 3]
        compact = unpack_mna_solution_forward(x_full, port_nodes=ports)
        rebuilt = unpack_mna_solution_backward(
            compact, port_nodes=ports, n_nodes=len(x_full)
        )
        # Only the port positions should match — everything else zero
        for idx in ports:
            assert rebuilt[idx] == x_full[idx]


# lmat helpers ----------------------------------------------------------


class TestLmatHelpers:
    def test_subblock_assemble_extracts_correctly(self):
        L = np.arange(16).reshape(4, 4).astype(float)
        sub = lmat_subblock_assemble(L, [0, 2], [1, 3])
        # L[0,1], L[0,3], L[2,1], L[2,3]
        np.testing.assert_array_equal(sub, [[1, 3], [9, 11]])

    def test_subblock_rejects_non_2d(self):
        with pytest.raises(ValueError):
            lmat_subblock_assemble(np.arange(8), [0], [0])

    def test_partial_traces(self):
        L = np.diag([1.0, 2.0, 3.0, 4.0, 5.0])
        traces = lmat_compute_partial_traces(L, block_sizes=[2, 3])
        # Tr(diag(1,2)) = 3, Tr(diag(3,4,5)) = 12
        np.testing.assert_array_equal(traces, [3.0, 12.0])

    def test_partial_traces_block_size_overflow_raises(self):
        L = np.eye(4)
        with pytest.raises(ValueError):
            lmat_compute_partial_traces(L, block_sizes=[10])

    def test_partial_traces_zero_block(self):
        L = np.eye(3) * 5.0
        traces = lmat_compute_partial_traces(L, block_sizes=[1, 0, 2])
        np.testing.assert_array_equal(traces, [5.0, 0.0, 10.0])
