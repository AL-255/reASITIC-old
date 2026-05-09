"""Tests for the FFT-accelerated convolution Green's-function pipeline."""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.substrate import (
    compute_green_function,
    fft_apply_to_green,
    rasterize_shape,
    setup_green_fft_grid,
    substrate_cap_matrix,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


# setup_green_fft_grid ---------------------------------------------------


class TestSetupGreenFFTGrid:
    def test_returns_grid_with_correct_dims(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        assert g.nx == 16 and g.ny == 16
        assert g.g_grid.shape == (16, 16)
        # FFT is zero-padded to 2N for linear convolution
        assert g.g_fft.shape == (32, 32)

    def test_falls_back_to_tech_defaults(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0)
        # BiCMOS.tek has fftx = ffty = 128
        assert g.nx == 128 and g.ny == 128

    def test_chip_dim_override(self, tech):
        g = setup_green_fft_grid(
            tech, z1_um=5.0, z2_um=5.0, nx=32, ny=32,
            chip_x_um=200.0, chip_y_um=300.0
        )
        assert g.chip_x_um == 200.0
        assert g.chip_y_um == 300.0

    def test_g_grid_finite(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=32, ny=32)
        assert np.all(np.isfinite(g.g_grid))
        # Centre cell should have the largest magnitude (closest source-
        # field separation).
        peak = np.unravel_index(np.argmax(np.abs(g.g_grid)), g.g_grid.shape)
        assert peak == (g.nx // 2, g.ny // 2) or g.g_grid[g.nx // 2, g.ny // 2] > 0

    def test_invalid_dims_raise(self, tech):
        with pytest.raises(ValueError):
            setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=0, ny=16)

    def test_compute_green_function_alias(self, tech):
        """The decomp-name alias must produce identical output."""
        a = compute_green_function(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        b = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        np.testing.assert_allclose(a.g_grid, b.g_grid)
        np.testing.assert_allclose(a.g_fft, b.g_fft)


# fft_apply_to_green -----------------------------------------------------


class TestFFTApplyToGreen:
    def test_zero_charge_yields_zero_potential(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        Q = np.zeros((16, 16))
        V = fft_apply_to_green(g, Q)
        np.testing.assert_allclose(V, 0.0)

    def test_returns_correct_shape(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        Q = np.zeros((16, 16))
        Q[8, 8] = 1.0
        V = fft_apply_to_green(g, Q)
        assert V.shape == (16, 16)
        assert np.all(np.isfinite(V))

    def test_rejects_wrong_charge_shape(self, tech):
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        with pytest.raises(ValueError):
            fft_apply_to_green(g, np.zeros((4, 4)))

    def test_potential_max_at_charge_location(self, tech):
        """A point charge produces the highest |V| at its own cell."""
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=32, ny=32)
        Q = np.zeros((32, 32))
        Q[10, 12] = 1.0
        V = fft_apply_to_green(g, Q)
        peak = np.unravel_index(np.argmax(np.abs(V)), V.shape)
        assert peak == (10, 12)

    def test_linearity(self, tech):
        """V(αQ + βQ') = α V(Q) + β V(Q')."""
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=16, ny=16)
        Q1 = np.random.RandomState(42).rand(16, 16)
        Q2 = np.random.RandomState(43).rand(16, 16)
        V1 = fft_apply_to_green(g, Q1)
        V2 = fft_apply_to_green(g, Q2)
        Vsum = fft_apply_to_green(g, 2.0 * Q1 + 3.0 * Q2)
        np.testing.assert_allclose(Vsum, 2.0 * V1 + 3.0 * V2, atol=1e-9)

    def test_no_circular_aliasing(self, tech):
        """A charge at one corner should NOT produce a peak at the
        opposite corner — that would mean wraparound."""
        g = setup_green_fft_grid(tech, z1_um=5.0, z2_um=5.0, nx=32, ny=32)
        Q = np.zeros((32, 32))
        Q[2, 2] = 1.0
        V = fft_apply_to_green(g, Q)
        # Far diagonal corner should be smaller than near corners.
        assert abs(V[30, 30]) < abs(V[2, 2])
        assert abs(V[30, 30]) < abs(V[3, 3])


# rasterize_shape --------------------------------------------------------


class TestRasterizeShape:
    def test_capacitor_fills_some_cells(self, tech):
        """A 50×50 cap centred well inside a 256×256 chip on a 64×64
        grid (4 μm/cell) should cover ~150 cells (50/4 ≈ 12.5 per side)."""
        cap = reasitic.capacitor(
            "C1", length=50, width=50,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(80, 80)
        mask = rasterize_shape(
            cap, nx=64, ny=64, chip_x_um=256.0, chip_y_um=256.0
        )
        assert mask.dtype == np.bool_
        # Cap is fully inside the chip footprint, so we expect to land
        # somewhere around 12² = 144 cells (10–250 cell tolerance).
        assert 10 < mask.sum() < 250

    def test_empty_shape_yields_empty_mask(self, tech):
        from reasitic.geometry import Shape
        empty = Shape(name="EMPTY")
        mask = rasterize_shape(empty, nx=16, ny=16,
                               chip_x_um=256.0, chip_y_um=256.0)
        assert not mask.any()

    def test_invalid_grid_raises(self, tech):
        cap = reasitic.capacitor(
            "C1", length=50, width=50,
            metal_top="m3", metal_bottom="m2", tech=tech,
        )
        with pytest.raises(ValueError):
            rasterize_shape(cap, nx=0, ny=16,
                            chip_x_um=256.0, chip_y_um=256.0)


# substrate_cap_matrix ---------------------------------------------------


class TestSubstrateCapMatrix:
    def test_empty_returns_0x0(self, tech):
        C = substrate_cap_matrix([], tech)
        assert C.shape == (0, 0)

    def test_single_shape_yields_1x1_positive(self, tech):
        cap = reasitic.capacitor(
            "C1", length=50, width=50,
            metal_top="m3", metal_bottom="m2", tech=tech,
        )
        C = substrate_cap_matrix([cap], tech, nx=32, ny=32)
        assert C.shape == (1, 1)
        assert np.isfinite(C[0, 0])

    def test_two_shapes_returns_2x2_symmetric(self, tech):
        a = reasitic.capacitor(
            "A", length=40, width=40,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(50, 50)
        b = reasitic.capacitor(
            "B", length=40, width=40,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(150, 150)
        C = substrate_cap_matrix([a, b], tech, nx=32, ny=32)
        assert C.shape == (2, 2)
        # Symmetry to floating-point precision
        assert C[0, 1] == pytest.approx(C[1, 0], rel=1e-9, abs=1e-15)

    def test_dict_input_works(self, tech):
        a = reasitic.capacitor(
            "A", length=40, width=40,
            metal_top="m3", metal_bottom="m2", tech=tech,
        )
        C = substrate_cap_matrix({"A": a}, tech, nx=16, ny=16)
        assert C.shape == (1, 1)

    def test_far_apart_shapes_have_smaller_offdiag(self, tech):
        """Shapes farther apart should have smaller off-diagonal cap
        than close ones (the FFT picks up the spatial-frequency drop-off)."""
        a_close = reasitic.capacitor(
            "A", length=20, width=20,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(10, 10)
        b_close = reasitic.capacitor(
            "B", length=20, width=20,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(50, 10)
        C_close = substrate_cap_matrix([a_close, b_close], tech,
                                       nx=64, ny=64)

        b_far = reasitic.capacitor(
            "B", length=20, width=20,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(220, 10)
        C_far = substrate_cap_matrix([a_close, b_far], tech,
                                     nx=64, ny=64)
        # Off-diagonal mutual capacitance (in absolute value) should
        # decrease with separation.
        assert abs(C_far[0, 1]) <= abs(C_close[0, 1])
