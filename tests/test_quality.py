"""Tests for metal-loss quality factor."""

import math
from pathlib import Path

import pytest

from reasitic import (
    compute_ac_resistance,
    compute_self_inductance,
    parse_tech_file,
    square_spiral,
)
from reasitic.quality import metal_only_q
from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_q_zero_at_dc(tech) -> None:
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    assert metal_only_q(sp, tech, freq_ghz=0.0) == 0.0


def test_q_consistent_with_omega_l_over_r(tech) -> None:
    """Direct ωL/R should match the convenience function."""
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    f = 2.4
    L_nH = compute_self_inductance(sp)
    R = compute_ac_resistance(sp, tech, f)
    expected = TWO_PI * f * GHZ_TO_HZ * L_nH * NH_TO_H / R
    assert metal_only_q(sp, tech, f) == pytest.approx(expected, rel=1e-12)


def test_q_grows_with_frequency_until_skin_dominates(tech) -> None:
    """In a typical RF design Q grows with f at low frequencies (since
    R changes slowly while ωL grows linearly), then rolls off as skin
    effect kicks in. We just check the low-f monotonicity here."""
    sp = square_spiral(
        "S1",
        length=200.0,
        width=10.0,
        spacing=2.0,
        turns=3.0,
        tech=tech,
        metal="m3",
    )
    q1 = metal_only_q(sp, tech, freq_ghz=0.5)
    q2 = metal_only_q(sp, tech, freq_ghz=1.0)
    q3 = metal_only_q(sp, tech, freq_ghz=2.0)
    assert q1 < q2 < q3
    # All Q values should be finite and non-negative
    for q in (q1, q2, q3):
        assert math.isfinite(q)
        assert q >= 0
