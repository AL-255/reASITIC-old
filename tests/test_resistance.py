"""Tests for DC and AC resistance kernels."""

import math
from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.resistance import (
    ac_resistance_segment,
    compute_ac_resistance,
    compute_dc_resistance,
    segment_dc_resistance,
    skin_depth,
)
from reasitic.units import MU_0

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# DC resistance ----------------------------------------------------------


def test_dc_segment_resistance_formula(tech) -> None:
    """R = rsh * L / W. m3 in BiCMOS.tek has rsh = 20 mΩ/sq → 0.020 Ω/sq."""
    w = wire("W1", length=100.0, width=10.0, tech=tech, metal="m3")
    seg = w.segments()[0]
    R = segment_dc_resistance(seg, tech)
    # 0.020 * 100 / 10 = 0.20 Ω
    assert pytest.approx(0.20, rel=1e-12) == R


def test_dc_zero_length(tech) -> None:
    w = wire("W0", length=0.0, width=10.0, tech=tech, metal="m3")
    R = compute_dc_resistance(w, tech)
    assert R == 0.0


def test_dc_resistance_doubles_with_length(tech) -> None:
    short = wire("S", length=50.0, width=10.0, tech=tech, metal="m3")
    long_ = wire("L", length=100.0, width=10.0, tech=tech, metal="m3")
    R_s = compute_dc_resistance(short, tech)
    R_l = compute_dc_resistance(long_, tech)
    assert R_l == pytest.approx(2.0 * R_s, rel=1e-12)


def test_dc_resistance_halves_with_width(tech) -> None:
    narrow = wire("N", length=100.0, width=5.0, tech=tech, metal="m3")
    wide = wire("W", length=100.0, width=10.0, tech=tech, metal="m3")
    R_n = compute_dc_resistance(narrow, tech)
    R_w = compute_dc_resistance(wide, tech)
    assert R_n == pytest.approx(2.0 * R_w, rel=1e-12)


def test_dc_resistance_square_spiral(tech) -> None:
    """A 2-turn square spiral has 8 segments; resistance is the
    sum of all segment resistances. Outer 4 are 170 μm, inner 4 are
    144 μm. R = 0.020 * (4*170 + 4*144) / 10 = 0.020 * 1256 / 10 = 2.512 Ω."""
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    R = compute_dc_resistance(sp, tech)
    assert pytest.approx(2.512, rel=1e-9) == R


# Skin depth -------------------------------------------------------------


def test_skin_depth_at_dc_is_inf() -> None:
    assert math.isinf(skin_depth(rho_ohm_cm=1.7e-6, freq_hz=0))


def test_skin_depth_aluminium_1ghz() -> None:
    """Reference: aluminium has rho ≈ 2.65e-6 Ω·cm; δ at 1 GHz ≈ 2.6 μm.

    We use the textbook formula δ = sqrt(rho/(π*μ*f)).
    """
    delta_m = skin_depth(rho_ohm_cm=2.65e-6, freq_hz=1e9)
    delta_um = delta_m * 1e6
    # 2.6 μm ± 5%
    assert delta_um == pytest.approx(2.59, rel=0.05)


def test_skin_depth_decreases_with_frequency() -> None:
    d1 = skin_depth(rho_ohm_cm=2.0e-6, freq_hz=1e8)
    d2 = skin_depth(rho_ohm_cm=2.0e-6, freq_hz=1e10)
    # δ ~ 1/sqrt(f), so a 100× increase in f gives a 10× decrease in δ
    assert d1 / d2 == pytest.approx(10.0, rel=1e-9)


# AC resistance ----------------------------------------------------------


def test_ac_resistance_at_dc_equals_dc(tech) -> None:
    """At freq=0 the AC formula should fall back to DC resistance."""
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    R_dc = compute_dc_resistance(sp, tech)
    R_ac0 = compute_ac_resistance(sp, tech, freq_ghz=0.0)
    assert R_ac0 == pytest.approx(R_dc, rel=1e-12)


def test_ac_resistance_increases_with_frequency(tech) -> None:
    """Skin effect makes AC resistance ≥ DC resistance, monotonically
    increasing with frequency."""
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    R_dc = compute_dc_resistance(sp, tech)
    R_low = compute_ac_resistance(sp, tech, freq_ghz=0.1)
    R_mid = compute_ac_resistance(sp, tech, freq_ghz=2.0)
    R_high = compute_ac_resistance(sp, tech, freq_ghz=20.0)
    assert R_dc <= R_low <= R_mid <= R_high
    # At 20 GHz the skin effect should bump R noticeably above DC.
    assert R_high > 1.05 * R_dc


def test_ac_segment_zero_inputs() -> None:
    """Zero-length, zero-width, or zero-rsh all give 0."""
    assert ac_resistance_segment(
        length_um=0, width_um=10, thickness_um=2, rsh_ohm_per_sq=0.02, freq_ghz=1
    ) == 0.0
    assert ac_resistance_segment(
        length_um=100, width_um=0, thickness_um=2, rsh_ohm_per_sq=0.02, freq_ghz=1
    ) == 0.0
    assert ac_resistance_segment(
        length_um=100, width_um=10, thickness_um=2, rsh_ohm_per_sq=0.0, freq_ghz=1
    ) == 0.0


def test_mu0_constant_value() -> None:
    """Sanity: MU_0 should equal 4π × 10⁻⁷ to high precision."""
    assert pytest.approx(4.0e-7 * math.pi, rel=0, abs=1e-20) == MU_0
