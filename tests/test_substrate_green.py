"""Tests for the multi-layer Sommerfeld substrate Green's function."""

import math

import pytest

from reasitic import parse_tech_file
from reasitic.substrate import (
    coupled_capacitance_per_pair,
    green_function_static,
    integrate_green_kernel,
)
from reasitic.substrate.green import (
    _stack_reflection_coefficient,
    green_layer_tanh_factor,
    layer_reflection_coefficient,
    propagation_constant,
    rect_tile_self_inv_r,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Reflection coefficient ------------------------------------------------


def test_reflection_coeff_in_range(tech) -> None:
    """The recursive reflection coefficient should stay in [-1, 1]."""
    R = _stack_reflection_coefficient(tech, k_rho=1.0e6)
    assert -1.0 <= R <= 1.0


def test_reflection_coeff_zero_at_dc(tech) -> None:
    """k_ρ → 0 returns 0 by guard."""
    assert _stack_reflection_coefficient(tech, k_rho=0.0) == 0.0


# Static Green's function ------------------------------------------------


def test_green_function_decays_with_separation(tech) -> None:
    g_near = green_function_static(rho_um=10.0, z1_um=5.0, z2_um=5.0, tech=tech)
    g_far = green_function_static(rho_um=1000.0, z1_um=5.0, z2_um=5.0, tech=tech)
    assert g_near > g_far
    assert g_far > 0


def test_green_function_finite_at_zero_rho(tech) -> None:
    """Self-pair (ρ → 0) is regularised by the floor at 1 μm."""
    g = green_function_static(rho_um=0.0, z1_um=5.0, z2_um=5.0, tech=tech)
    assert math.isfinite(g)
    assert g > 0


# Coupled capacitance ----------------------------------------------------


def test_coupled_cap_zero_for_zero_area(tech) -> None:
    C = coupled_capacitance_per_pair(
        rho_um=10.0, z1_um=5.0, z2_um=5.0, a1_um2=0.0, a2_um2=10.0, tech=tech
    )
    assert C == 0.0


def test_coupled_cap_finite_for_normal_inputs(tech) -> None:
    C = coupled_capacitance_per_pair(
        rho_um=50.0, z1_um=5.0, z2_um=5.0, a1_um2=400.0, a2_um2=400.0, tech=tech
    )
    assert math.isfinite(C)
    assert C > 0


# Bessel-J0 numerical integration ---------------------------------------


def test_integrate_green_kernel_returns_finite(tech) -> None:
    val = integrate_green_kernel(rho_um=10.0, z1_um=5.0, z2_um=5.0, tech=tech)
    assert math.isfinite(val)


def test_integrate_green_kernel_decays_with_z(tech) -> None:
    """Larger z (higher metal) → smaller substrate-coupled value."""
    near = integrate_green_kernel(rho_um=10.0, z1_um=2.0, z2_um=2.0, tech=tech)
    far = integrate_green_kernel(rho_um=10.0, z1_um=20.0, z2_um=20.0, tech=tech)
    assert abs(far) < abs(near)


# Analytical rectangular self-tile term ---------------------------------


class TestRectTileSelfInvR:
    """Closed-form ⟨1/r⟩ over a rectangle (Nabors-White 1991, Walker 1990).

    The four-fold integral

        ∫₀ᵃ ∫₀ᵃ ∫₀ᵇ ∫₀ᵇ 1/√((x−x')² + (y−y')²) dx dx' dy dy'
          = (4/3) × { −a³ − b³ + (a²+b²)^{3/2}
                      + 3 a² b · sinh⁻¹(b/a)
                      + 3 a b² · sinh⁻¹(a/b) }

    Dividing by ``(ab)²`` gives ⟨1/r⟩. For a *unit square* (a = b = 1)
    that evaluates exactly to::

        (4/3) × ( −2 + 2√2 + 6·sinh⁻¹(1) ) ≈ 8.15555906...

    All other rectangles fall out of this by linearity (⟨1/r⟩ is
    inversely proportional to the linear scale factor).
    """

    def test_zero_inputs_return_zero(self):
        assert rect_tile_self_inv_r(0.0, 10.0) == 0.0
        assert rect_tile_self_inv_r(10.0, 0.0) == 0.0
        assert rect_tile_self_inv_r(-1.0, 10.0) == 0.0

    def test_unit_square_closed_form(self):
        """Hand-computed value for a 1 m × 1 m tile.

        Inputs are in microns; here we use ``1e6 µm = 1 m`` so the
        result has the simple form quoted in the docstring.
        """
        v = rect_tile_self_inv_r(1.0e6, 1.0e6)
        expected = (4.0 / 3.0) * (
            -2.0 + 2.0 * math.sqrt(2.0) + 6.0 * math.asinh(1.0)
        )
        assert v == pytest.approx(expected, rel=1e-12)

    def test_symmetry_in_arguments(self):
        v_ab = rect_tile_self_inv_r(7.0, 13.0)
        v_ba = rect_tile_self_inv_r(13.0, 7.0)
        assert v_ab == pytest.approx(v_ba, rel=1e-12)

    def test_inverse_linear_scaling(self):
        """Doubling both sides halves ⟨1/r⟩ — dimensional argument
        and a check the closed form respects it."""
        small = rect_tile_self_inv_r(5.0, 7.0)
        big = rect_tile_self_inv_r(10.0, 14.0)
        assert big == pytest.approx(small * 0.5, rel=1e-12)

    def test_finite_for_extreme_aspect(self):
        """A long thin tile (100:1 aspect) still gives a finite,
        positive ⟨1/r⟩."""
        v = rect_tile_self_inv_r(1.0, 100.0)
        assert math.isfinite(v)
        assert v > 0

    def test_units_in_inverse_meters(self):
        """For a 10 µm tile, the result must be in 1/m and equal
        ``(unit-square value) / (10 µm in m)``."""
        v_10um = rect_tile_self_inv_r(10.0, 10.0)
        v_unit = rect_tile_self_inv_r(1.0e6, 1.0e6)
        # 10 µm = 1e-5 m → scale factor 1e5
        assert v_10um == pytest.approx(v_unit * 1.0e5, rel=1e-12)


# Sommerfeld primitives (C-grounded) -----------------------------------


class TestGreenLayerTanhFactor:
    """The tanh boundary factor decoded from green_function_kernel_a.

    Decomp ``0x0808cc90`` (lines 9630-9669) computes
    ``(2^x − 1) / (2^x + 1) × sign`` three times for different
    layer-boundary distances. The pattern simplifies to
    ``tanh(k_ρ · Δz)``. These tests pin the primitive's behaviour
    against directly-decoded C properties.
    """

    def test_zero_dz_returns_zero(self):
        """``Δz = 0`` ⇒ tanh(0) = 0 — the C path computes
        ``2^0 − 1 = 0`` so the factor vanishes."""
        assert green_layer_tanh_factor(1.0e6, 0.0) == 0.0

    def test_zero_k_returns_zero(self):
        assert green_layer_tanh_factor(0.0, 5.0) == 0.0

    def test_sign_tracks_dz(self):
        """The C ``sign = (-lVar15 < 0) ? -1 : +1`` tracks the sign
        of ``Δz``. tanh is odd, so sign of result == sign of Δz."""
        v_pos = green_layer_tanh_factor(1.0e6, 5.0)
        v_neg = green_layer_tanh_factor(1.0e6, -5.0)
        assert v_pos > 0
        assert v_neg < 0
        assert v_pos == pytest.approx(-v_neg, rel=1e-12)

    def test_saturates_at_one(self):
        """Large ``k·Δz`` ⇒ ``tanh → ±1``. The C sets
        ``dVar4 = 1e+15`` when the argument exceeds the magic
        threshold ``500``, so the saturation is explicit there."""
        # k * dz = 1e6 * 1e-3 m = 1e3 → tanh(1e3) ≈ 1.0
        # (use a moderate k_rho × dz product to avoid overflow)
        v = green_layer_tanh_factor(1.0e8, 100.0)
        assert v == pytest.approx(1.0, rel=1e-9)

    def test_units_match_decomp(self):
        """``k_ρ`` is in 1/m and ``dz`` in microns; the function
        converts dz internally. Verify against an external tanh."""
        k_rho = 1.0e5  # 1/m
        dz_um = 10.0
        # k · Δz in dimensionless: 1e5 / m × 10 µm × 1e-6 m/µm = 1.0
        expected = math.tanh(1.0)
        assert green_layer_tanh_factor(k_rho, dz_um) == pytest.approx(expected, rel=1e-12)


class TestSommerfeldReflectionCoefficient:
    """Single-layer ``Γ = (k − γ) / (k + γ)`` from reflection_coeff_imag.

    Decomp ``0x08093eb8`` builds ``γ = √(k² + j·2π·μ₀·σ·ω)`` then
    forms ``(k − γ) / (k + γ)`` and returns the imaginary part.
    """

    def test_zero_omega_returns_zero(self):
        """ω = 0 ⇒ γ = k ⇒ Γ = 0. The C model has no static stack
        reflection — it relies entirely on the conductivity-induced
        ω-dependent part for substrate coupling."""
        gamma = layer_reflection_coefficient(
            k_rho=1.0e6, omega_rad=0.0, sigma_S_per_m=10.0,
        )
        assert gamma == 0j

    def test_zero_sigma_returns_zero(self):
        """σ = 0 (perfect dielectric) ⇒ γ = k ⇒ Γ = 0."""
        gamma = layer_reflection_coefficient(
            k_rho=1.0e6, omega_rad=2.0 * math.pi * 1.0e9, sigma_S_per_m=0.0,
        )
        assert gamma == 0j

    def test_perfect_conductor_limit(self):
        """For very high σ, γ → ∞ and Γ → -1 (perfect electric
        ground reflection). σ = 10⁹ S/m at f = 1 GHz gives
        ``2π·μ₀·σ·ω`` ≈ 5×10¹⁰ ≫ k², so γ.real ≈ γ.imag ≈ √(σω/2)
        and Γ → −1 with a small ``2k/γ`` correction."""
        gamma = layer_reflection_coefficient(
            k_rho=1.0e3, omega_rad=2.0 * math.pi * 1.0e9, sigma_S_per_m=1.0e9,
        )
        assert gamma.real == pytest.approx(-1.0, abs=2e-3)

    def test_propagation_constant_real_part_at_omega_zero(self):
        """Decomp lines 13100-13105: ``γ = sqrt(k² + j·...)``. At
        ω=0 the imaginary part is zero so γ = k (real)."""
        gamma = propagation_constant(k_rho=1.5e6, omega_rad=0.0, sigma_S_per_m=10.0)
        assert gamma == complex(1.5e6, 0.0)

    def test_propagation_constant_imag_part_grows_with_omega(self):
        """Higher ω at fixed σ should give a larger imaginary part
        of γ (the substrate becomes more lossy)."""
        g_low = propagation_constant(1.0e6, 2.0 * math.pi * 1.0e8, 10.0)
        g_hi = propagation_constant(1.0e6, 2.0 * math.pi * 1.0e10, 10.0)
        assert abs(g_hi.imag) > abs(g_low.imag)