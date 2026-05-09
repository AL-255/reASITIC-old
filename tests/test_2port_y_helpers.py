"""Tests for the 2-port Y-derived impedance helpers."""

from __future__ import annotations

import math

import numpy as np
import pytest

from reasitic.network import (
    imag_z_2port_from_y,
    z_2port_from_y,
    zin_terminated_2port,
)


def _RL_pi_y(R: float, L_nH: float, omega: float, C_p_F: float = 0.0) -> np.ndarray:
    """Build a Pi-equivalent Y matrix for a series RL with shunt caps."""
    Z_s = R + 1j * omega * L_nH * 1e-9
    Y_s = 1.0 / Z_s
    Y_p = 1j * omega * C_p_F
    Y = np.array(
        [[Y_s + Y_p, -Y_s], [-Y_s, Y_s + Y_p]],
        dtype=complex,
    )
    return Y


# z_2port_from_y --------------------------------------------------------


class TestZ2PortFromY:
    def test_singleended_port1_returns_inverse_y22(self):
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        Z = z_2port_from_y(Y, port=1)
        assert pytest.approx(1.0 / Y[1, 1]) == Z

    def test_singleended_port2_returns_inverse_y11(self):
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        Z = z_2port_from_y(Y, port=2)
        assert pytest.approx(1.0 / Y[0, 0]) == Z

    def test_differential_form(self):
        """Z_d = (Y11 + Y22 + 2 Y21) / (Y11 Y22 − Y21^2)."""
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.05 + 0.01j]], dtype=complex)
        Z_d = z_2port_from_y(Y, differential=True)
        Y11, Y22, Y21 = Y[0, 0], Y[1, 1], Y[1, 0]
        expected = (Y11 + Y22 + 2.0 * Y21) / (Y11 * Y22 - Y21 * Y21)
        assert Z_d == pytest.approx(expected, rel=1e-12)

    def test_differential_matches_algebraic_identity(self):
        """Verify Z_d = (Y11+Y22+2Y21)/(Y11*Y22-Y21^2) directly."""
        Y = np.array([[0.07 + 0.02j, -0.04 + 0.005j],
                      [-0.04 + 0.005j, 0.06 - 0.01j]], dtype=complex)
        Y11, Y22, Y21 = Y[0, 0], Y[1, 1], Y[1, 0]
        expected = (Y11 + Y22 + 2.0 * Y21) / (Y11 * Y22 - Y21 * Y21)
        Z_d = z_2port_from_y(Y, differential=True)
        assert Z_d == pytest.approx(expected, rel=1e-12)

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError):
            z_2port_from_y(np.zeros((3, 3), dtype=complex))


# imag_z_2port_from_y ---------------------------------------------------


class TestImagZ2PortFromY:
    def test_returns_imag_part(self):
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        z = z_2port_from_y(Y, port=1)
        assert imag_z_2port_from_y(Y, port=1) == pytest.approx(z.imag)

    def test_inductor_imag_z_positive(self):
        """A series inductor (positive reactance) with shunt cap should
        yield a positive Im(Z) at port 1 below resonance."""
        omega = 2 * math.pi * 1e9
        Y = _RL_pi_y(R=1.0, L_nH=5.0, omega=omega, C_p_F=10e-15)
        # Far below resonance (which is ~22 GHz here)
        assert imag_z_2port_from_y(Y, port=1) > 0


# zin_terminated_2port --------------------------------------------------


class TestZinTerminated2Port:
    def test_open_load_yields_open_circuit_zin(self):
        """Y_load → 0 leaves Z_in = (Y_ii − Y_ij Y_ji / Y_jj)^-1."""
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        Z_in = zin_terminated_2port(Y, Y_load=0j, port=1)
        Y_in_expected = Y[0, 0] - Y[0, 1] * Y[1, 0] / Y[1, 1]
        assert Z_in == pytest.approx(1.0 / Y_in_expected)

    def test_short_load_uses_only_ii(self):
        """Y_load → ∞ kills the cross term: Z_in = 1 / Y_ii.

        We approximate ∞ by a very large finite admittance.
        """
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        Y_big = 1e10 + 0j
        Z_in = zin_terminated_2port(Y, Y_load=Y_big, port=1)
        assert Z_in == pytest.approx(1.0 / Y[0, 0], rel=1e-6)

    def test_50_ohm_match_yields_realish_zin(self):
        """A reasonably matched RFIC port should have Re(Z_in) > 0."""
        Y = np.array([[0.02 + 0.005j, -0.018 + 0j],
                      [-0.018 + 0j, 0.02 + 0.005j]], dtype=complex)
        Z_in = zin_terminated_2port(Y, Y_load=0.02 + 0j, port=1)
        assert Z_in.real > 0

    def test_invalid_port_falls_back_to_port_2(self):
        """``port != 1`` selects the port-2 branch — verify both work."""
        Y = np.array([[0.05 + 0.01j, -0.04 + 0j],
                      [-0.04 + 0j, 0.06 - 0.02j]], dtype=complex)
        Z1 = zin_terminated_2port(Y, Y_load=0.01 + 0j, port=1)
        Z2 = zin_terminated_2port(Y, Y_load=0.01 + 0j, port=2)
        # The two ports should give DIFFERENT input impedances when the
        # Y matrix is not symmetric (here Y[0,0] != Y[1,1]).
        assert Z1 != Z2

    def test_invalid_shape_raises(self):
        with pytest.raises(ValueError):
            zin_terminated_2port(np.zeros((3, 3), dtype=complex), Y_load=0j)
