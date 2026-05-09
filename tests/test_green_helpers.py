"""Tests for the Sommerfeld helper kernels and remaining mutual-L helpers."""

from __future__ import annotations

import math

import pytest

from reasitic.geometry import Point, Segment
from reasitic.inductance import (
    mutual_inductance_axial_term,
    mutual_inductance_segment_kernel,
    wire_axial_separation,
)
from reasitic.substrate import (
    green_function_kernel_a,
    green_function_kernel_b,
    green_function_select_integrator,
    green_kernel_a_helper,
    green_kernel_b_helper,
    green_kernel_shared_helper,
)

# Sommerfeld helpers ------------------------------------------------------


class TestGreenKernelSharedHelper:
    def test_zero_kappa_returns_zero(self):
        v = green_kernel_shared_helper(k_rho=0.0, z_a_um=5.0, z_b_um=5.0)
        assert v == 0.0

    def test_decays_with_height(self):
        """exp(-k(z_a + z_b)) means higher z reduces the kernel."""
        low = green_kernel_shared_helper(k_rho=1e3, z_a_um=1.0, z_b_um=1.0)
        high = green_kernel_shared_helper(k_rho=1e3, z_a_um=10.0, z_b_um=10.0)
        assert high < low

    def test_returns_finite_positive(self):
        v = green_kernel_shared_helper(k_rho=1e3, z_a_um=5.0, z_b_um=5.0)
        assert math.isfinite(v) and v > 0


class TestGreenKernelAB:
    def test_a_b_agree_without_omega(self):
        """At ω=0 (no substrate loss), both kernels reduce to the
        shared base value."""
        a = green_kernel_a_helper(1e3, 5.0, 5.0, omega_rad=0.0,
                                   sigma_S_per_m=0.0)
        b = green_kernel_b_helper(1e3, 5.0, 5.0, omega_rad=0.0,
                                   sigma_S_per_m=0.0)
        s = green_kernel_shared_helper(1e3, 5.0, 5.0)
        assert a == s
        assert b == s

    def test_a_minus_b_matches_correction(self):
        """green_kernel_a - green_kernel_b = 2 × correction term."""
        kw = dict(omega_rad=2 * math.pi * 1e9, sigma_S_per_m=10.0)
        a = green_kernel_a_helper(1e3, 5.0, 5.0, **kw)
        b = green_kernel_b_helper(1e3, 5.0, 5.0, **kw)
        # The two should differ symmetrically around the shared base
        s = green_kernel_shared_helper(1e3, 5.0, 5.0)
        assert (a - s) == pytest.approx(-(b - s), rel=1e-9)


class TestGreenFunctionKernelTopLevel:
    def test_kernel_a_finite(self):
        v = green_function_kernel_a(
            1e3, z_a_um=5.0, z_b_um=5.0,
            omega_rad=2 * math.pi * 1e9, sigma_S_per_m=10.0,
        )
        assert math.isfinite(v)

    def test_kernel_b_finite(self):
        v = green_function_kernel_b(
            1e3, z_a_um=5.0, z_b_um=5.0,
            omega_rad=2 * math.pi * 1e9, sigma_S_per_m=10.0,
        )
        assert math.isfinite(v)


class TestGreenFunctionSelectIntegrator:
    def test_oscillating_branch(self):
        """Non-zero ω → cosine-weighted DQAWF path (scipy.quad)."""
        v = green_function_select_integrator(
            "oscillating",
            omega_rad=2 * math.pi * 1e9,
            lower=1e3, upper=1e6,
            integrand_args={
                "sigma_a_S_per_m": 10.0,
                "sigma_b_S_per_m": 1.0,
                "layer_thickness_m": 1e-4,
                "rho_m": 1e-5,
            },
        )
        assert math.isfinite(v)

    def test_propagation_branch(self):
        v = green_function_select_integrator(
            "propagation",
            omega_rad=2 * math.pi * 1e9,
            lower=1e3, upper=1e6,
            integrand_args={
                "sigma_a_S_per_m": 10.0,
                "sigma_b_S_per_m": 1.0,
                "layer_thickness_m": 1e-4,
                "z_m": 1e-5,
            },
        )
        assert math.isfinite(v)

    def test_unknown_kind_raises(self):
        with pytest.raises(ValueError):
            green_function_select_integrator(
                "magic", omega_rad=1e9,
            )


# mutual_inductance_axial_term -------------------------------------------


class TestMutualInductanceAxialTerm:
    def test_default_freq_factor_returns_separation(self):
        a1 = Point(0, 0, 0)
        a2 = Point(0, 0, 100)
        # Default freq_factor=1 → just the wire_axial_separation value
        v = mutual_inductance_axial_term(a1, a2, a1, a2, radius_um=2.0)
        sep = wire_axial_separation(a1, a2, radius_um=2.0)
        assert v == pytest.approx(sep)

    def test_freq_factor_scales(self):
        a1 = Point(0, 0, 0)
        a2 = Point(0, 0, 100)
        v1 = mutual_inductance_axial_term(a1, a2, a1, a2, freq_factor=2.5)
        v0 = mutual_inductance_axial_term(a1, a2, a1, a2, freq_factor=1.0)
        assert v1 == pytest.approx(2.5 * v0)


# mutual_inductance_segment_kernel ---------------------------------------


class TestMutualInductanceSegmentKernel:
    def test_parallel_segments_return_one(self):
        seg_a = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        seg_b = Segment(
            a=Point(0, 10, 0), b=Point(100, 10, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        v = mutual_inductance_segment_kernel(seg_a, seg_b)
        assert v == pytest.approx(1.0)

    def test_perpendicular_segments_return_zero(self):
        seg_a = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        seg_b = Segment(
            a=Point(50, 0, 0), b=Point(50, 100, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        assert mutual_inductance_segment_kernel(seg_a, seg_b) == pytest.approx(0.0)
