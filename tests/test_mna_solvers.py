"""Tests for the MNA solvers and the eddy matrix assembler."""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.inductance import assemble_eddy_matrix
from reasitic.network import (
    assemble_mna_matrix,
    setup_mna_rhs,
    solve_3port_equations,
    solve_node_equations,
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


# solve_node_equations ---------------------------------------------------


class TestSolveNodeEquations:
    def test_identity_returns_b(self):
        Y = np.eye(4, dtype=complex)
        b = np.array([1, 2, 3, 4], dtype=complex)
        v = solve_node_equations(Y, b)
        np.testing.assert_allclose(v, b)

    def test_diagonal_y_inverse_diagonal(self):
        Y = np.diag([2.0, 4.0, 8.0]).astype(complex)
        b = np.array([10, 20, 40], dtype=complex)
        v = solve_node_equations(Y, b)
        np.testing.assert_allclose(v, [5, 5, 5])

    def test_complex_round_trip(self):
        """Y · v = b ⇒ Y · solve(Y, b) ≈ b for any non-singular Y."""
        rng = np.random.RandomState(7)
        Y = rng.rand(5, 5) + 1j * rng.rand(5, 5) + 5 * np.eye(5)
        b = rng.rand(5) + 1j * rng.rand(5)
        v = solve_node_equations(Y, b)
        np.testing.assert_allclose(Y @ v, b, atol=1e-10)

    def test_singular_raises(self):
        Y = np.zeros((3, 3), dtype=complex)
        b = np.array([1, 2, 3], dtype=complex)
        with pytest.raises(np.linalg.LinAlgError):
            solve_node_equations(Y, b)

    def test_non_square_raises(self):
        with pytest.raises(ValueError):
            solve_node_equations(
                np.zeros((2, 3), dtype=complex),
                np.zeros(2, dtype=complex),
            )

    def test_dimension_mismatch_raises(self):
        with pytest.raises(ValueError):
            solve_node_equations(
                np.eye(3, dtype=complex),
                np.zeros(2, dtype=complex),
            )


# solve_3port_equations -------------------------------------------------


class TestSolve3PortEquations:
    def test_pure_3node_system_returns_input_when_no_interior(self):
        """When all 3 nodes are ports, the result is exactly Y_full."""
        Y = (np.array([[2, -1, 0], [-1, 3, -1], [0, -1, 2]],
                      dtype=complex))
        Y3 = solve_3port_equations(Y, port_nodes=[0, 1, 2])
        np.testing.assert_allclose(Y3, Y)

    def test_4node_to_3port_schur(self):
        """Eliminate node 3, retain ports 0/1/2."""
        # Build a simple resistive network: 4 nodes with star topology,
        # central node = 3.
        Y = np.zeros((4, 4), dtype=complex)
        for hub_branch in (0, 1, 2):
            y = 0.1 + 0j
            Y[hub_branch, hub_branch] += y
            Y[3, 3] += y
            Y[hub_branch, 3] -= y
            Y[3, hub_branch] -= y
        Y3 = solve_3port_equations(Y, port_nodes=[0, 1, 2])
        # Star network with three arms of admittance y → eliminating
        # the centre gives a delta of y/3 between every port pair.
        # Y_3port[i, i] = y - y²/(3y) = y - y/3 = 2y/3
        # Y_3port[i, j] = -y²/(3y) = -y/3
        expected_self = 0.1 - 0.1 / 3.0
        expected_off = -0.1 / 3.0
        for i in range(3):
            assert Y3[i, i] == pytest.approx(expected_self, rel=1e-9)
            for j in range(3):
                if i != j:
                    assert Y3[i, j] == pytest.approx(expected_off, rel=1e-9)

    def test_wrong_port_count_raises(self):
        Y = np.eye(4, dtype=complex)
        with pytest.raises(ValueError):
            solve_3port_equations(Y, port_nodes=[0, 1])

    def test_non_square_raises(self):
        with pytest.raises(ValueError):
            solve_3port_equations(
                np.zeros((3, 4), dtype=complex),
                port_nodes=[0, 1, 2],
            )


# Round-trip: assemble + solve ------------------------------------------


class TestAssembleAndSolve:
    def test_branch_solve_round_trip(self):
        """Build a 3-node MNA from branch admittances, drive with a
        current source at node 0, and solve."""
        # Two resistors in series: 0—1 (y=1), 1—2 (y=2)
        Y = assemble_mna_matrix(
            3,
            branch_admittances=[(0, 1, 1.0 + 0j), (1, 2, 2.0 + 0j),
                                (2, -1, 0.5 + 0j)],
        )
        b = setup_mna_rhs(3, current_sources=[(0, 1.0 + 0j)])
        # Note this builds a singular matrix without grounding;
        # the (2, -1, 0.5) anchors node 2.
        v = solve_node_equations(Y, b)
        # All voltages should be finite
        assert np.all(np.isfinite(v))


# assemble_eddy_matrix --------------------------------------------------


class TestAssembleEddyMatrix:
    def test_returns_square_real_matrix(self, spiral, tech):
        M = assemble_eddy_matrix(spiral, tech, freq_ghz=2.0)
        n = M.shape[0]
        assert M.shape == (n, n)
        assert M.dtype.kind == "f"

    def test_symmetric(self, spiral, tech):
        M = assemble_eddy_matrix(spiral, tech, freq_ghz=2.0)
        np.testing.assert_allclose(M, M.T, atol=1e-12)

    def test_zero_freq_returns_empty(self, spiral, tech):
        M = assemble_eddy_matrix(spiral, tech, freq_ghz=0.0)
        # No skin-depth at DC
        assert M.shape == (0, 0)

    def test_no_layers_returns_empty(self, spiral):
        from reasitic.tech import Chip, Tech
        empty_tech = Tech(chip=Chip(), layers=[], metals=[], vias=[])
        M = assemble_eddy_matrix(spiral, empty_tech, freq_ghz=2.0)
        assert M.shape == (0, 0)

    def test_higher_freq_gives_more_coupling(self, spiral, tech):
        """At higher frequency the substrate looks more like a ground
        plane — the thickness factor (1 − exp(−2t/δ)) grows, so eddy
        mutual coupling increases."""
        M_low = assemble_eddy_matrix(spiral, tech, freq_ghz=0.1)
        M_hi = assemble_eddy_matrix(spiral, tech, freq_ghz=10.0)
        if M_low.size > 0 and M_hi.size > 0:
            assert abs(M_hi.trace()) > abs(M_low.trace())
