"""Tests for the second batch of kernel ports: shapes_bounding_box,
substrate Green's primitives (propagation_constant,
layer_reflection_coefficient), and eddy_packed_index."""

from __future__ import annotations

import math

import pytest

import reasitic
from reasitic.geometry import Shape, shapes_bounding_box
from reasitic.inductance import eddy_packed_index
from reasitic.substrate import (
    layer_reflection_coefficient,
    propagation_constant,
)
from reasitic.substrate.green import TWO_PI_MU0
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


# shapes_bounding_box ----------------------------------------------------


class TestShapesBoundingBox:
    def test_empty_list_with_tech_returns_chip_outline(self, tech):
        bb = shapes_bounding_box([], tech=tech)
        assert bb == (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)

    def test_empty_list_no_tech_returns_zeros(self):
        assert shapes_bounding_box([]) == (0.0, 0.0, 0.0, 0.0)

    def test_dict_input_works(self, tech):
        sh = reasitic.square_spiral("L1", length=200, width=10, spacing=2,
                                    turns=3, tech=tech, metal="m3")
        bb = shapes_bounding_box({"L1": sh}, tech=tech)
        sh_bb = sh.bounding_box()
        assert bb == pytest.approx(sh_bb)

    def test_union_of_two_disjoint_shapes(self, tech):
        a = reasitic.square_spiral("A", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3",
                                   x_origin=0, y_origin=0)
        b = reasitic.square_spiral("B", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3",
                                   x_origin=200, y_origin=300)
        bb = shapes_bounding_box([a, b], tech=tech)
        # The union must cover both
        assert bb[0] <= a.x_origin
        assert bb[1] <= a.y_origin
        assert bb[2] >= b.x_origin
        assert bb[3] >= b.y_origin

    def test_x_origin_y_origin_are_added(self, tech):
        a = reasitic.square_spiral("A", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3",
                                   x_origin=100, y_origin=200)
        bb = shapes_bounding_box([a])
        local_bb = a.bounding_box()
        assert bb[0] == pytest.approx(local_bb[0] + 100)
        assert bb[1] == pytest.approx(local_bb[1] + 200)

    def test_all_empty_shapes_falls_back_to_chip(self, tech):
        empty = Shape(name="EMPTY")
        bb = shapes_bounding_box([empty], tech=tech)
        assert bb == (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)


# propagation_constant ---------------------------------------------------


class TestPropagationConstant:
    def test_zero_omega_returns_pure_real_kappa(self):
        """At ω=0 the j·μ₀σω term vanishes → γ = k_ρ exactly."""
        k = 100.0
        gamma = propagation_constant(k, omega_rad=0.0,
                                     sigma_S_per_m=10.0)
        assert gamma == pytest.approx(complex(k, 0.0))

    def test_zero_sigma_returns_pure_real_kappa(self):
        """A non-conductive layer (σ=0) → γ = k_ρ."""
        k = 100.0
        gamma = propagation_constant(k, omega_rad=2 * math.pi * 1e9,
                                     sigma_S_per_m=0.0)
        assert gamma == pytest.approx(complex(k, 0.0))

    def test_real_and_imag_parts_positive(self):
        """For σ>0 and ω>0, both Re(γ) and Im(γ) must be positive
        (principal sqrt with positive real part)."""
        gamma = propagation_constant(k_rho=1e3,
                                     omega_rad=2 * math.pi * 1e9,
                                     sigma_S_per_m=10.0)
        assert gamma.real > 0
        assert gamma.imag > 0

    def test_known_constant_2pi_mu0(self):
        """Spot-check the magic constant from the binary."""
        assert pytest.approx(2 * math.pi * 4e-7 * math.pi,
                             rel=1e-12) == TWO_PI_MU0

    def test_gamma_squared_equals_input(self):
        """Verify γ² = k² + j·2πμ₀σω."""
        k, w, s = 50.0, 2 * math.pi * 5e9, 10.0
        gamma = propagation_constant(k, w, s)
        rebuild = gamma * gamma
        expected = complex(k * k, TWO_PI_MU0 * s * w)
        assert rebuild == pytest.approx(expected, rel=1e-9)


# layer_reflection_coefficient ------------------------------------------


class TestLayerReflectionCoefficient:
    def test_zero_sigma_returns_zero(self):
        """A lossless layer (σ=0) → γ = k → Γ = 0."""
        gamma = layer_reflection_coefficient(
            k_rho=100.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=0.0
        )
        assert gamma == pytest.approx(complex(0.0, 0.0), abs=1e-12)

    def test_high_sigma_approaches_minus_one(self):
        """Very lossy layer → γ ≫ k → Γ → -1 (perfect reflection)."""
        gamma = layer_reflection_coefficient(
            k_rho=10.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=1e6,
        )
        assert abs(gamma + 1.0) < 0.5

    def test_magnitude_at_most_one(self):
        """The reflection coefficient must satisfy |Γ| ≤ 1 for a
        passive lossy substrate."""
        for sigma in (0.1, 1.0, 10.0, 100.0, 1000.0):
            for omega in (1e8, 1e9, 1e10):
                gamma = layer_reflection_coefficient(
                    k_rho=100.0, omega_rad=omega, sigma_S_per_m=sigma,
                )
                assert abs(gamma) <= 1.0 + 1e-9, (
                    f"|Γ|>1 for σ={sigma}, ω={omega}"
                )

    def test_imag_part_negative_for_passive_substrate(self):
        """For a passive substrate the imaginary part of Γ should be
        negative — energy gets dissipated, not generated."""
        gamma = layer_reflection_coefficient(
            k_rho=10.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=10.0,
        )
        assert gamma.imag < 0


# eddy_packed_index ------------------------------------------------------


class TestEddyPackedIndex:
    @pytest.mark.parametrize("i,j,expected", [
        (1, 1, 1),    # diagonal: 4*1 - 3 = 1
        (2, 2, 5),    # diagonal: 4*2 - 3 = 5
        (3, 3, 9),    # diagonal: 4*3 - 3 = 9
        (5, 5, 17),
    ])
    def test_diagonal_branch(self, i, j, expected):
        assert eddy_packed_index(i, j) == expected

    @pytest.mark.parametrize("i,j,expected", [
        (3, 1, 8 * 1 - 4 * 3 + 3),    # = -1
        (4, 2, 8 * 2 - 4 * 4 + 3),    # = 3
        (5, 1, 8 * 1 - 4 * 5 + 3),    # = -9
    ])
    def test_off_diagonal_branch(self, i, j, expected):
        assert eddy_packed_index(i, j) == expected

    def test_diagonal_uses_i_only(self):
        """When j == i, the i*4 - 3 path runs (j < i is false)."""
        for i in range(1, 10):
            assert eddy_packed_index(i, i) == 4 * i - 3
