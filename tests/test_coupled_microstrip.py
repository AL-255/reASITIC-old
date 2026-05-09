"""Tests for the Hammerstad-Jensen coupled-microstrip model."""

import math

import pytest

from reasitic.substrate import (
    HJCoupledCaps,
    coupled_microstrip_caps_hj,
    coupled_microstrip_to_cap_matrix,
    even_odd_impedances,
)
from reasitic.substrate.coupled import (
    EPS_0_FCM,
    _eps_eff,
    _kk_prime_ratio,
    _z0_microstrip,
)


class TestSingleStripModel:
    """Hammerstad's single-microstrip building blocks."""

    def test_eps_eff_for_air_substrate_returns_unity(self):
        """eps_r=1 (air) → eps_eff = 1 regardless of W/h."""
        for wh in (0.1, 1.0, 10.0):
            assert _eps_eff(wh, eps_r=1.0) == pytest.approx(1.0, rel=1e-12)

    def test_eps_eff_increases_with_wider_strips(self):
        """Wider strips concentrate more field in the dielectric."""
        eps_r = 9.6  # alumina
        for w1, w2 in [(0.1, 1.0), (1.0, 5.0)]:
            assert _eps_eff(w1, eps_r) < _eps_eff(w2, eps_r)

    def test_eps_eff_in_range_for_high_eps_r(self):
        """eps_eff must lie between 1 and eps_r."""
        eps_r = 11.7  # Si
        for wh in (0.05, 0.5, 1.0, 5.0, 50.0):
            e = _eps_eff(wh, eps_r)
            assert 1.0 < e < eps_r

    def test_z0_decreases_for_wider_strip(self):
        """Z0 ∝ 1/W for wide strips."""
        eps_r = 4.0
        e_eff_a = _eps_eff(0.5, eps_r)
        e_eff_b = _eps_eff(5.0, eps_r)
        assert _z0_microstrip(0.5, e_eff_a) > _z0_microstrip(5.0, e_eff_b)

    def test_z0_50_ohm_design(self):
        """50-Ω microstrip on 1 mm FR-4 (eps_r=4.4) should have W/h ≈ 1.85."""
        eps_eff = _eps_eff(1.85, 4.4)
        z0 = _z0_microstrip(1.85, eps_eff)
        assert z0 == pytest.approx(50.0, rel=0.05)


class TestEllipticIntegralRatio:
    """The Hammerstad piecewise approximation for K(k)/K(k')."""

    def test_k_zero_yields_large_ratio(self):
        """Limiting case: k → 0 makes K(k')/K(k) blow up (capacitance ~ 1/k)."""
        assert _kk_prime_ratio(0.001) > 2.0

    def test_k_one_yields_small_ratio(self):
        """k → 1 makes K(k')/K(k) shrink (the strips decouple)."""
        assert _kk_prime_ratio(0.99) < 0.6

    def test_kk_prime_monotonic_decreasing(self):
        """K(k')/K(k) is a monotonically decreasing function of k."""
        prev = float("inf")
        for k in (0.05, 0.2, 0.5, 0.7, 0.9):
            r = _kk_prime_ratio(k)
            assert r < prev
            prev = r

    def test_k_half_continuity(self):
        """Both branches should agree at k² = 0.5."""
        k_lo = math.sqrt(0.5) - 1e-6
        k_hi = math.sqrt(0.5) + 1e-6
        assert _kk_prime_ratio(k_lo) == pytest.approx(_kk_prime_ratio(k_hi), rel=5e-3)

    def test_out_of_range_k_raises(self):
        with pytest.raises(ValueError):
            _kk_prime_ratio(-0.1)
        with pytest.raises(ValueError):
            _kk_prime_ratio(1.1)


class TestHJCoupled:
    """The full 5-component coupled-microstrip model."""

    def test_returns_dataclass_with_five_caps(self):
        c = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.005,
                                       h_cm=0.01, eps_r=4.4)
        assert isinstance(c, HJCoupledCaps)
        for v in (c.Cp, c.Cf, c.Cf_prime, c.Cga, c.Cgd):
            assert math.isfinite(v)
            assert v > 0

    def test_cp_is_parallel_plate_formula(self):
        """Cp should be exactly εr·ε0·W/h."""
        W, s, h, er = 0.02, 0.005, 0.01, 4.4
        c = coupled_microstrip_caps_hj(W, s, h, er)
        assert c.Cp == pytest.approx(er * EPS_0_FCM * (W / h), rel=1e-12)

    def test_cf_prime_smaller_than_cf(self):
        """Inner-edge fringe must be ≤ outer-edge fringe."""
        c = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.003,
                                       h_cm=0.01, eps_r=4.4)
        assert c.Cf_prime <= c.Cf

    def test_cf_prime_approaches_cf_at_large_spacing(self):
        """Large s → coupled strip looks isolated → Cf' ≈ Cf."""
        # Reference: spacing 100× larger
        c_close = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.005,
                                             h_cm=0.01, eps_r=4.4)
        c_far = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.5,
                                           h_cm=0.01, eps_r=4.4)
        assert c_far.Cf_prime / c_far.Cf > c_close.Cf_prime / c_close.Cf
        assert c_far.Cf_prime / c_far.Cf > 0.95

    def test_gap_caps_decrease_with_spacing(self):
        """Both Cga and Cgd must monotonically shrink as s grows."""
        prev_a = float("inf")
        prev_d = float("inf")
        for s in (0.001, 0.005, 0.02, 0.1):
            c = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=s,
                                           h_cm=0.01, eps_r=4.4)
            assert c.Cga < prev_a
            assert c.Cgd < prev_d
            prev_a = c.Cga
            prev_d = c.Cgd

    def test_cgd_grows_with_eps_r(self):
        """Higher dielectric constant strengthens the substrate-side gap."""
        c_low = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.005,
                                           h_cm=0.01, eps_r=2.2)
        c_hi = coupled_microstrip_caps_hj(W_cm=0.01, s_cm=0.005,
                                          h_cm=0.01, eps_r=11.7)
        assert c_hi.Cgd > c_low.Cgd

    def test_validation_errors(self):
        with pytest.raises(ValueError):
            coupled_microstrip_caps_hj(0.0, 0.01, 0.01, 4.4)
        with pytest.raises(ValueError):
            coupled_microstrip_caps_hj(0.01, 0.0, 0.01, 4.4)
        with pytest.raises(ValueError):
            coupled_microstrip_caps_hj(0.01, 0.01, 0.0, 4.4)
        with pytest.raises(ValueError):
            coupled_microstrip_caps_hj(0.01, 0.01, 0.01, 0.5)


class TestCapMatrix:
    """The wrapper that produces (C_self, C_mutual)."""

    def test_symmetric_pair_uses_even_odd_decomposition(self):
        Cs, Cm = coupled_microstrip_to_cap_matrix(
            W_cm=0.01, s_cm=0.005, h_cm=0.01, eps_r=4.4
        )
        assert Cs > 0
        assert Cm > 0  # odd > even (anti-phase always couples more)
        assert Cm < Cs  # mutual is a fraction of self

    def test_alternate_mode_is_well_defined(self):
        """mode != 1 returns a finite, positive but different decomposition."""
        Cs1, _ = coupled_microstrip_to_cap_matrix(
            W_cm=0.01, s_cm=0.005, h_cm=0.01, eps_r=4.4, mode=1
        )
        Cs2, Cm2 = coupled_microstrip_to_cap_matrix(
            W_cm=0.01, s_cm=0.005, h_cm=0.01, eps_r=4.4, mode=2
        )
        for v in (Cs2, Cm2):
            assert math.isfinite(v)
        # The two modes must give different self caps (the alternate
        # form weights Cf' twice instead of summing Cp + Cf + Cf').
        # F/cm caps are O(1e-12); pytest.approx defaults to abs=1e-12
        # which would absorb the difference, so spell it out.
        assert abs(Cs1 - Cs2) / max(Cs1, Cs2) > 0.01

    def test_mutual_to_self_ratio_drops_with_spacing(self):
        for s, expected_max in [(0.001, 0.5), (0.05, 0.05)]:
            Cs, Cm = coupled_microstrip_to_cap_matrix(
                W_cm=0.01, s_cm=s, h_cm=0.01, eps_r=4.4
            )
            ratio = Cm / Cs
            assert ratio < expected_max


class TestEvenOddImpedances:
    """Z_even / Z_odd derivation."""

    def test_z_odd_smaller_than_z_even(self):
        """For coupled microstrip: Co > Ce → Zo < Ze (always)."""
        Ze, Zo = even_odd_impedances(W_cm=0.01, s_cm=0.005,
                                     h_cm=0.01, eps_r=4.4)
        assert Zo < Ze
        assert 10.0 < Zo < 200.0
        assert 10.0 < Ze < 200.0

    def test_widely_spaced_strips_converge_to_single_z0(self):
        """At very large s, Ze and Zo collapse toward each other."""
        Ze_close, Zo_close = even_odd_impedances(W_cm=0.01, s_cm=0.001,
                                                 h_cm=0.01, eps_r=4.4)
        Ze_far, Zo_far = even_odd_impedances(W_cm=0.01, s_cm=0.5,
                                             h_cm=0.01, eps_r=4.4)
        gap_close = abs(Ze_close - Zo_close) / Ze_close
        gap_far = abs(Ze_far - Zo_far) / Ze_far
        assert gap_far < gap_close
