"""Tests for the 2-port network parameter conversions."""

from pathlib import Path

import numpy as np
import pytest

from reasitic import parse_tech_file, square_spiral
from reasitic.network import (
    pi_equivalent,
    pi_to_y,
    s_to_y,
    spiral_y_at_freq,
    y_to_s,
    y_to_z,
    z_to_y,
)
from reasitic.network.twoport import PiModel

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Y/Z round-trips --------------------------------------------------------


def test_y_to_z_to_y_identity() -> None:
    Y = np.array([[1 + 2j, 0.1 - 0.05j], [0.1 - 0.05j, 0.5 + 1j]])
    Z = y_to_z(Y)
    Y2 = z_to_y(Z)
    np.testing.assert_allclose(Y2, Y, atol=1e-12)


def test_y_to_z_known_value() -> None:
    """Diagonal Y = diag(0.02, 0.02) → Z = diag(50, 50)."""
    Y = np.diag([0.02 + 0j, 0.02 + 0j])
    Z = y_to_z(Y)
    np.testing.assert_allclose(Z, np.diag([50 + 0j, 50 + 0j]), atol=1e-12)


# Y/S round-trips --------------------------------------------------------


def test_y_to_s_to_y_identity() -> None:
    Y = np.array([[0.02 + 0.001j, -0.001j], [-0.001j, 0.02 + 0.001j]])
    S = y_to_s(Y)
    Y2 = s_to_y(S)
    np.testing.assert_allclose(Y2, Y, atol=1e-12)


def test_matched_load_yields_zero_s() -> None:
    """Y = diag(Y0, Y0) → S = 0."""
    y0 = 0.02
    Y = np.diag([y0 + 0j, y0 + 0j])
    S = y_to_s(Y, y0=y0)
    np.testing.assert_allclose(S, np.zeros((2, 2)), atol=1e-12)


def test_open_port_y_to_s() -> None:
    """An open 2-port has Y = 0 → S = identity."""
    Y = np.zeros((2, 2), dtype=complex)
    S = y_to_s(Y)
    np.testing.assert_allclose(S, np.eye(2), atol=1e-12)


def test_short_port_y_to_s_diverges() -> None:
    """A short between port and ground is Y = ∞; we approximate
    with a very large admittance and check S is close to -I."""
    Y = np.diag([1e6 + 0j, 1e6 + 0j])
    S = y_to_s(Y)
    np.testing.assert_allclose(S, -np.eye(2), atol=1e-3)


# Pi model ---------------------------------------------------------------


def test_pi_to_y_to_pi_round_trip() -> None:
    pi = PiModel(freq_ghz=2.0, Z_s=10 + 5j, Y_p1=0.001j, Y_p2=0.002j)
    Y = pi_to_y(pi)
    pi2 = pi_equivalent(Y, freq_ghz=2.0)
    assert pi2.Z_s == pytest.approx(pi.Z_s)
    assert pi2.Y_p1 == pytest.approx(pi.Y_p1)
    assert pi2.Y_p2 == pytest.approx(pi.Y_p2)


def test_pi_extraction_from_pure_series_impedance() -> None:
    """Y from pure series impedance Z (no shunts):
       Y = (1/Z) * [[1, -1], [-1, 1]] → Pi extracts Z_s = Z, Y_p = 0."""
    Z = 100 + 50j
    Y = (1 / Z) * np.array([[1, -1], [-1, 1]], dtype=complex)
    pi = pi_equivalent(Y, freq_ghz=1.0)
    assert pi.Z_s == pytest.approx(Z, rel=1e-12)
    assert abs(pi.Y_p1) < 1e-12
    assert abs(pi.Y_p2) < 1e-12


# Spiral Y at frequency --------------------------------------------------


def test_spiral_y_at_freq_consistency(tech) -> None:
    """The spiral's series impedance via Y should equal R + jωL
    derived from compute_self_inductance + compute_ac_resistance."""
    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    f = 2.0
    # Disable substrate to keep the test focused on the series leg.
    Y = spiral_y_at_freq(sp, tech, freq_ghz=f, include_substrate=False)
    pi = pi_equivalent(Y, freq_ghz=f)
    assert abs(pi.Y_p1) < 1e-12
    assert abs(pi.Y_p2) < 1e-12
    # Z_s real part is the AC resistance, imag is ωL
    from reasitic.inductance import compute_self_inductance
    from reasitic.resistance import compute_ac_resistance
    from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI

    L = compute_self_inductance(sp)
    R = compute_ac_resistance(sp, tech, f)
    omega = TWO_PI * f * GHZ_TO_HZ
    assert pi.Z_s.real == pytest.approx(R, rel=1e-9)
    assert pi.Z_s.imag == pytest.approx(omega * L * NH_TO_H, rel=1e-9)


def test_spiral_s_parameters_finite(tech) -> None:
    """A reasonable spiral at 2 GHz should give finite S parameters."""
    sp = square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    Y = spiral_y_at_freq(sp, tech, freq_ghz=2.0)
    S = y_to_s(Y)
    assert np.all(np.isfinite(S))
    # Reciprocal network: S12 == S21
    assert S[0, 1] == pytest.approx(S[1, 0])


def test_y_to_z_rejects_non_2x2() -> None:
    with pytest.raises(ValueError):
        y_to_z(np.eye(3, dtype=complex))


def test_pi_extraction_rejects_zero_y12() -> None:
    Y = np.diag([1 + 0j, 1 + 0j])
    with pytest.raises(ValueError):
        pi_equivalent(Y, freq_ghz=1.0)
