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