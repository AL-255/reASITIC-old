"""Tests for the multi-layer Sommerfeld substrate Green's function."""

import math
from pathlib import Path

import pytest

from reasitic import parse_tech_file
from reasitic.substrate import (
    coupled_capacitance_per_pair,
    green_function_static,
    integrate_green_kernel,
)
from reasitic.substrate.green import _stack_reflection_coefficient

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


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
