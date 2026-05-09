"""Branch-coverage tests for network/twoport.py.

Targets the specific shape-validation and zero-impedance branches
that the existing test suite doesn't exercise:
- y_to_z / y_to_s / s_to_y / pi_equivalent shape-mismatch raises
- pi_to_y zero series impedance raise
- spiral_y_at_freq zero L+R raise + explicit y_p1 / y_p2 overrides
- deembed_pad_open_short shape mismatch raise
"""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.network import (
    PiModel,
    deembed_pad_open_short,
    pi_equivalent,
    pi_to_y,
    s_to_y,
    spiral_y_at_freq,
    y_to_s,
    y_to_z,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3"
    )


# Shape-validation raises -----------------------------------------------


class TestShapeValidationRaises:
    def test_y_to_z_rejects_3x3(self):
        with pytest.raises(ValueError, match="2x2"):
            y_to_z(np.zeros((3, 3), dtype=complex))

    def test_y_to_s_rejects_1x2(self):
        with pytest.raises(ValueError, match="2x2"):
            y_to_s(np.zeros((1, 2), dtype=complex))

    def test_s_to_y_rejects_5x5(self):
        with pytest.raises(ValueError, match="2x2"):
            s_to_y(np.zeros((5, 5), dtype=complex))

    def test_pi_equivalent_rejects_4x4(self):
        with pytest.raises(ValueError, match="2x2"):
            pi_equivalent(np.zeros((4, 4), dtype=complex), freq_ghz=1.0)


# pi_to_y zero impedance -------------------------------------------------


class TestPiToYZeroImpedance:
    def test_zero_series_impedance_raises(self):
        with pytest.raises(ValueError, match="series impedance is zero"):
            pi_to_y(PiModel(
                freq_ghz=1.0, Z_s=0 + 0j,
                Y_p1=1e-3 + 0j, Y_p2=1e-3 + 0j,
            ))


# spiral_y_at_freq branches ---------------------------------------------


class TestSpiralYAtFreqBranches:
    def test_explicit_y_p1_only(self, spiral, tech):
        """If only y_p1 is supplied, y_p2 falls back to substrate stub."""
        Y = spiral_y_at_freq(
            spiral, tech, freq_ghz=2.4,
            y_p1=1e-4 + 0j,
        )
        assert Y[0, 0].real >= 1e-4 - 1e-12  # the explicit y_p1 contributes

    def test_explicit_y_p2_only(self, spiral, tech):
        """If only y_p2 is supplied, y_p1 falls back to substrate stub."""
        Y = spiral_y_at_freq(
            spiral, tech, freq_ghz=2.4,
            y_p2=2e-4 + 0j,
        )
        assert Y[1, 1].real >= 2e-4 - 1e-12

    def test_explicit_both_overrides(self, spiral, tech):
        Y_a = spiral_y_at_freq(
            spiral, tech, freq_ghz=2.4,
            y_p1=1e-4 + 0j, y_p2=2e-4 + 0j,
        )
        # Should differ from the default (substrate-only) one
        Y_b = spiral_y_at_freq(spiral, tech, freq_ghz=2.4)
        assert not np.allclose(Y_a, Y_b)

    def test_zero_l_and_r_raises(self, spiral, tech, monkeypatch):
        """When the inductance + resistance kernels both report zero
        the series impedance is 0 and the function raises."""
        from reasitic.network import twoport as tp

        monkeypatch.setattr(tp, "compute_self_inductance", lambda _s: 0.0)
        monkeypatch.setattr(tp, "compute_ac_resistance",
                            lambda _s, _t, _f: 0.0)
        with pytest.raises(ValueError, match="series impedance is zero"):
            spiral_y_at_freq(spiral, tech, freq_ghz=2.4)


# deembed_pad_open_short shape mismatch ---------------------------------


class TestDeembedShapeMismatch:
    def test_meas_wrong_shape_raises(self):
        good = np.eye(2, dtype=complex)
        with pytest.raises(ValueError, match="Y_meas must be 2x2"):
            deembed_pad_open_short(np.zeros((3, 3), dtype=complex), good, good)

    def test_open_wrong_shape_raises(self):
        good = np.eye(2, dtype=complex)
        with pytest.raises(ValueError, match="Y_open must be 2x2"):
            deembed_pad_open_short(good, np.zeros((1, 1), dtype=complex), good)

    def test_short_wrong_shape_raises(self):
        good = np.eye(2, dtype=complex)
        with pytest.raises(ValueError, match="Y_short must be 2x2"):
            deembed_pad_open_short(good, good, np.zeros((4, 4), dtype=complex))
