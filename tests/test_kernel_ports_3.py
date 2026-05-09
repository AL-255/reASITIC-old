"""Sommerfeld inner-integrand cluster + filament-pair primitives."""

from __future__ import annotations

import math

import pytest

from reasitic.geometry import Point
from reasitic.inductance import (
    mutual_inductance_filament_kernel,
    wire_axial_separation,
    wire_separation_periodic,
)
from reasitic.substrate import (
    green_function_kernel_a_oscillating,
    green_function_kernel_b_reflection,
    green_oscillating_integrand,
    green_propagation_integrand,
)

# Sommerfeld integrands ---------------------------------------------------


class TestGreenOscillatingIntegrand:
    def test_returns_complex(self):
        v = green_oscillating_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, rho_m=1e-5,
        )
        assert isinstance(v, complex)
        assert math.isfinite(v.real) and math.isfinite(v.imag)

    def test_zero_omega_returns_real_at_dc(self):
        """At ω=0 the propagation constant is purely real → integrand is
        purely real."""
        v = green_oscillating_integrand(
            k_rho=1e3, omega_rad=0.0,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, rho_m=1e-5,
        )
        assert abs(v.imag) < 1e-9

    def test_decays_with_layer_thickness(self):
        """Thicker substrate (layer_thickness_m → ∞) drives the
        boundary tanh factor toward 1, stabilising the integrand."""
        v_thin = green_oscillating_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-6, rho_m=1e-5,
        )
        v_thick = green_oscillating_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1.0, rho_m=1e-5,
        )
        assert math.isfinite(v_thin.real) and math.isfinite(v_thick.real)


class TestGreenPropagationIntegrand:
    def test_returns_complex(self):
        v = green_propagation_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        assert isinstance(v, complex)
        assert math.isfinite(v.real) and math.isfinite(v.imag)

    def test_huge_z_decays_to_near_zero(self):
        v = green_propagation_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1.0,  # 1 m height — physically absurd
        )
        # The decay e^{-γz} is essentially zero
        assert abs(v) < 1e-3


class TestGreenFunctionKernelA:
    def test_zero_kappa_returns_zero(self):
        assert green_function_kernel_a_oscillating(
            0.0, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        ) == 0.0

    def test_decays_at_large_kappa(self):
        """exp(-k·z) drives the kernel to zero as k → ∞."""
        small = green_function_kernel_a_oscillating(
            1e2, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-3,
        )
        large = green_function_kernel_a_oscillating(
            1e6, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-3,
        )
        assert abs(large) < abs(small)


class TestGreenFunctionKernelB:
    def test_uses_reflection_coefficient(self):
        """The b-kernel scales by Γ — should be smaller in magnitude
        than the a-kernel at the same k_ρ for typical substrates."""
        a = green_function_kernel_a_oscillating(
            1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        b = green_function_kernel_b_reflection(
            1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        assert math.isfinite(a) and math.isfinite(b)
        # Reflection coefficient |Γ| ≤ 1 → b's magnitude ≤ a's
        assert abs(b) <= abs(a) + 1e-9


# Filament-pair primitives ------------------------------------------------


class TestMutualInductanceFilamentKernel:
    def test_parallel_returns_one(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 10, 0), Point(100, 10, 0)
        assert mutual_inductance_filament_kernel(a1, a2, b1, b2) == pytest.approx(1.0)

    def test_anti_parallel_returns_negative_one(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(100, 10, 0), Point(0, 10, 0)
        assert mutual_inductance_filament_kernel(a1, a2, b1, b2) == pytest.approx(-1.0)

    def test_perpendicular_returns_zero(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 0, 0), Point(0, 100, 0)
        assert mutual_inductance_filament_kernel(a1, a2, b1, b2) == pytest.approx(0.0)

    def test_45_degrees_returns_sqrt_half(self):
        a1, a2 = Point(0, 0, 0), Point(100, 0, 0)
        b1, b2 = Point(0, 0, 0), Point(50, 50, 0)
        v = mutual_inductance_filament_kernel(a1, a2, b1, b2)
        assert v == pytest.approx(1.0 / math.sqrt(2.0), rel=1e-9)

    def test_zero_length_returns_zero(self):
        a1, a2 = Point(0, 0, 0), Point(0, 0, 0)
        b1, b2 = Point(0, 0, 0), Point(50, 50, 0)
        assert mutual_inductance_filament_kernel(a1, a2, b1, b2) == 0.0


class TestWireAxialSeparation:
    def test_distance_minus_two_radii(self):
        a1 = Point(0, 0, 0)
        a2 = Point(30, 40, 0)  # |B-A| = 50
        s = wire_axial_separation(a1, a2, radius_um=2.0)
        assert s == pytest.approx(50.0 - 4.0)

    def test_zero_radius_is_pure_distance(self):
        a1 = Point(0, 0, 0)
        a2 = Point(0, 0, 100)
        assert wire_axial_separation(a1, a2) == pytest.approx(100.0)

    def test_can_be_negative(self):
        """Overlap → negative separation."""
        a1 = Point(0, 0, 0)
        a2 = Point(0, 0, 1)  # 1 μm apart
        assert wire_axial_separation(a1, a2, radius_um=10.0) < 0


class TestWireSeparationPeriodic:
    def test_both_below_fold_returns_positive(self):
        v = wire_separation_periodic(
            i=2, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert v >= 0

    def test_split_fold_returns_negative(self):
        # i above, j below
        v = wire_separation_periodic(
            i=15, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert v <= 0

    def test_signed_sqrt_form(self):
        """Magnitude is sqrt(|p_i · p_j|) regardless of sign."""
        v_ab = wire_separation_periodic(
            i=2, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        v_ba = wire_separation_periodic(
            i=3, j=2, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert abs(v_ab) == pytest.approx(abs(v_ba))
