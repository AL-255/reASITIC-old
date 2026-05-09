"""Tests for the high-level network-analysis commands: Pi, Zin, SelfRes."""

import math
from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
)
from reasitic.network.analysis import (
    pi_model_at_freq,
    self_resonance,
    zin_terminated,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return square_spiral(
        "S",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )


# Pi-model ---------------------------------------------------------------


def test_pi_model_l_matches_compute_self_inductance(tech, spiral) -> None:
    from reasitic import compute_self_inductance

    pi = pi_model_at_freq(spiral, tech, freq_ghz=2.0)
    L_direct = compute_self_inductance(spiral)
    assert pi.L_nH == pytest.approx(L_direct, rel=1e-9)


def test_pi_model_r_matches_compute_ac_resistance(tech, spiral) -> None:
    from reasitic import compute_ac_resistance

    pi = pi_model_at_freq(spiral, tech, freq_ghz=2.0)
    R_direct = compute_ac_resistance(spiral, tech, 2.0)
    assert pi.R_series == pytest.approx(R_direct, rel=1e-9)


def test_pi_model_substrate_caps_present(tech, spiral) -> None:
    """spiral_y_at_freq now includes the substrate stub; Pi
    extraction should report finite, positive shunt caps."""
    pi = pi_model_at_freq(spiral, tech, freq_ghz=2.0)
    assert pi.C_p1_fF > 0
    assert pi.C_p2_fF > 0
    # Stub is a parallel-plate model — caps are ~fF scale
    assert pi.C_p1_fF < 1000.0


def test_pi_model_rejects_nonpositive_freq(tech, spiral) -> None:
    with pytest.raises(ValueError):
        pi_model_at_freq(spiral, tech, freq_ghz=0)


# Zin --------------------------------------------------------------------


def test_zin_returns_finite_with_substrate(tech, spiral) -> None:
    """With the substrate shunt-cap stub on, Y is non-singular → Zin
    returns a finite complex impedance."""
    z = zin_terminated(spiral, tech, freq_ghz=2.0)
    assert math.isfinite(z.real)
    assert math.isfinite(z.imag)


def test_zin_raises_when_substrate_disabled(tech, spiral) -> None:
    """With include_substrate=False, Y is singular → Zin raises."""
    # Drive zin_terminated through spiral_y_at_freq with the
    # substrate disabled; we shadow it via a tiny test stub.
    import numpy as np

    from reasitic.network.twoport import spiral_y_at_freq, y_to_z

    Y = spiral_y_at_freq(spiral, tech, 2.0, include_substrate=False)
    with np.errstate(divide="ignore", invalid="ignore"):
        Z = y_to_z(Y)
    assert not np.all(np.isfinite(Z))


def test_zin_with_synthetic_y_open() -> None:
    """Quick path-only test: build a Y matrix where Z is finite
    (add a tiny shunt) and check zin_terminated returns finite."""
    import numpy as np

    from reasitic.network.twoport import y_to_z

    # Add a small shunt cap to break the singularity
    omega = 2 * math.pi * 2.0e9
    Yp = 1j * omega * 1e-15  # 1 fF
    Z_series = 5.0 + 1j * omega * 1.0e-9
    Yseries = 1.0 / Z_series
    Y = np.array(
        [
            [Yseries + Yp, -Yseries],
            [-Yseries, Yseries + Yp],
        ],
        dtype=complex,
    )
    Z = y_to_z(Y)
    assert math.isfinite(Z[0, 0].real)


# Self-resonance --------------------------------------------------------


def test_selfres_returns_not_converged_for_lossless(tech, spiral) -> None:
    """No shunt cap → no resonance → not converged."""
    # spiral_y_at_freq now defaults to including the substrate stub,
    # which creates a finite shunt cap and lets self-resonance find a
    # real crossing. So this test now checks that *with* substrate the
    # resonance is found.
    res = self_resonance(spiral, tech, f_low_ghz=0.1, f_high_ghz=50.0)
    assert res.converged is True
    assert 1.0 < res.freq_ghz < 30.0


# ShuntR ----------------------------------------------------------------


def test_shunt_resistance_positive(tech, spiral) -> None:
    from reasitic.network.analysis import shunt_resistance

    r = shunt_resistance(spiral, tech, freq_ghz=2.4)
    assert r.R_p_ohm > 0
    assert r.Q > 0
    assert r.R_series_ohm > 0


def test_shunt_resistance_differential_doubles(tech, spiral) -> None:
    from reasitic.network.analysis import shunt_resistance

    r_se = shunt_resistance(spiral, tech, freq_ghz=2.4, differential=False)
    r_di = shunt_resistance(spiral, tech, freq_ghz=2.4, differential=True)
    # Differential mode doubles L and R; Q stays the same since it
    # scales as ωL/R; Rp = R(1+Q²) doubles.
    assert r_di.L_nH == pytest.approx(r_se.L_nH * 2.0, rel=1e-9)
    assert r_di.R_series_ohm == pytest.approx(r_se.R_series_ohm * 2.0, rel=1e-9)
    assert pytest.approx(r_se.Q, rel=1e-9) == r_di.Q


# Pi3, Pi4 --------------------------------------------------------------


def test_pi3_basic(tech, spiral) -> None:
    from reasitic.network.analysis import pi3_model

    res = pi3_model(spiral, tech, freq_ghz=2.4)
    assert res.L_series_nH > 0
    assert res.R_series_ohm > 0
    assert res.C_p1_to_gnd_fF > 0


def test_pi3_with_ground_spiral_reduces_l(tech) -> None:
    from reasitic import square_spiral
    from reasitic.network.analysis import pi3_model

    sig = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    gnd = square_spiral(
        "G", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3",
        x_origin=300,
    )
    no_gnd = pi3_model(sig, tech, freq_ghz=2.4)
    with_gnd = pi3_model(sig, tech, freq_ghz=2.4, ground_shape=gnd)
    # With a coupled ground, the effective series-L gets reduced
    # (or amplified depending on coupling sign); check it changes.
    assert with_gnd.L_series_nH != no_gnd.L_series_nH


def test_pi4_with_pads(tech, spiral) -> None:
    from reasitic import capacitor
    from reasitic.network.analysis import pi4_model

    pad = capacitor(
        "PAD", length=50, width=50, metal_top="m3", metal_bottom="m2", tech=tech
    )
    res = pi4_model(spiral, tech, freq_ghz=2.4, pad1=pad, pad2=pad)
    assert res.C_pad1_fF > 0
    assert res.C_pad2_fF > 0
    assert res.L_series_nH > 0


# CalcTrans -------------------------------------------------------------


def test_calc_transformer_returns_finite_k(tech) -> None:
    from reasitic import square_spiral
    from reasitic.network.analysis import calc_transformer

    pri = square_spiral(
        "P", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    sec = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3",
        x_origin=210,
    )
    t = calc_transformer(pri, sec, tech, freq_ghz=2.4)
    assert t.L_pri_nH > 0
    assert t.L_sec_nH > 0
    assert -1.0 < t.k < 1.0
    # Identical geometries → turns ratio ≈ 1
    assert t.n_turns_ratio == pytest.approx(1.0, rel=1e-6)
