"""Tests for the 2-port frequency sweep + 3-port reduction."""

from pathlib import Path

import numpy as np
import pytest

from reasitic import parse_tech_file, square_spiral
from reasitic.network import (
    linear_freqs,
    reduce_3port_z_to_2port_y,
    two_port_sweep,
    write_touchstone,
    z_to_s_3port,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Linear frequency stride ------------------------------------------------


def test_linear_freqs_inclusive() -> None:
    fs = linear_freqs(1.0, 5.0, 1.0)
    assert fs == [1.0, 2.0, 3.0, 4.0, 5.0]


def test_linear_freqs_single_point() -> None:
    fs = linear_freqs(1.0, 1.0, 1.0)
    assert fs == [1.0]


def test_linear_freqs_rejects_zero_step() -> None:
    with pytest.raises(ValueError):
        linear_freqs(1.0, 5.0, 0.0)


# 2-port sweep -----------------------------------------------------------


def test_sweep_returns_correct_lengths(tech) -> None:
    sp = square_spiral(
        "L1", length=170.0, width=10.0, spacing=3.0, turns=2.0,
        tech=tech, metal="m3",
    )
    fs = [1.0, 2.0, 5.0]
    sweep = two_port_sweep(sp, tech, fs)
    assert len(sweep.freqs_ghz) == 3
    assert len(sweep.Y) == 3
    assert len(sweep.Z) == 3
    assert len(sweep.S) == 3
    assert len(sweep.pi) == 3


def test_sweep_pi_extraction_consistent(tech) -> None:
    sp = square_spiral(
        "L1", length=170.0, width=10.0, spacing=3.0, turns=2.0,
        tech=tech, metal="m3",
    )
    sweep = two_port_sweep(sp, tech, [2.0])
    # Z_s (real part) = R_ac, (imag) = ωL
    pi = sweep.pi[0]
    assert pi.Z_s.real > 0  # resistance positive
    assert pi.Z_s.imag > 0  # inductive
    # Substrate shunts are positive imaginary (capacitive)
    assert pi.Y_p1.imag > 0
    assert pi.Y_p2.imag > 0
    # And small in magnitude (substrate cap is fF-scale)
    assert abs(pi.Y_p1) < 1e-2


def test_sweep_to_touchstone(tech) -> None:
    sp = square_spiral(
        "L1", length=170.0, width=10.0, spacing=3.0, turns=2.0,
        tech=tech, metal="m3",
    )
    sweep = two_port_sweep(sp, tech, [1.0, 2.0, 3.0])
    pts = sweep.to_touchstone_points(param="S")
    assert len(pts) == 3
    text = write_touchstone(pts)
    lines = text.strip().splitlines()
    # 1 option line + 3 freq points
    assert len(lines) == 4
    assert lines[0].startswith("# GHz S MA")


def test_sweep_rejects_empty_freqs(tech) -> None:
    sp = square_spiral(
        "L1", length=10.0, width=2.0, spacing=1.0, turns=1.0,
        tech=tech, metal="m3",
    )
    with pytest.raises(ValueError):
        two_port_sweep(sp, tech, [])


# 3-port reduction --------------------------------------------------------


def test_reduce_3port_diagonal() -> None:
    """A diagonal Z matrix gives a diagonal Y; reducing port 2 should
    keep the inverse-of-diagonal entries for ports 0 and 1."""
    Z = np.diag([10.0 + 0j, 20.0 + 0j, 30.0 + 0j])
    Y = reduce_3port_z_to_2port_y(Z)
    assert Y.shape == (2, 2)
    np.testing.assert_allclose(Y, np.diag([1.0 / 10.0, 1.0 / 20.0]), atol=1e-12)


def test_reduce_3port_grounds_first_port() -> None:
    Z = np.diag([10.0 + 0j, 20.0 + 0j, 30.0 + 0j])
    Y = reduce_3port_z_to_2port_y(Z, ground_port=0)
    np.testing.assert_allclose(Y, np.diag([1.0 / 20.0, 1.0 / 30.0]), atol=1e-12)


def test_reduce_3port_rejects_non_3x3() -> None:
    with pytest.raises(ValueError):
        reduce_3port_z_to_2port_y(np.eye(2, dtype=complex))


def test_reduce_3port_rejects_bad_ground() -> None:
    with pytest.raises(ValueError):
        reduce_3port_z_to_2port_y(np.eye(3, dtype=complex), ground_port=4)


def test_z_to_s_3port_matched_load() -> None:
    """Z = diag(50, 50, 50) → S = 0₃."""
    Z = 50.0 * np.eye(3, dtype=complex)
    S = z_to_s_3port(Z, z0_ohm=50.0)
    np.testing.assert_allclose(S, np.zeros((3, 3)), atol=1e-12)


def test_z_to_s_3port_rejects_non_3x3() -> None:
    with pytest.raises(ValueError):
        z_to_s_3port(np.eye(2, dtype=complex))
