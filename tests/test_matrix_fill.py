"""Tests for the filament-list assembly + impedance-matrix fill ports."""

from __future__ import annotations

import math

import numpy as np
import pytest

import reasitic
from reasitic.geometry import Point, Segment
from reasitic.inductance import (
    FilamentList,
    build_filament_list,
    filament_list_setup,
    filament_pair_4corner_integration,
    fill_impedance_matrix_triangular,
    fill_inductance_diagonal,
    fill_inductance_offdiag,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3"
    )


# build_filament_list / filament_list_setup -------------------------------


class TestBuildFilamentList:
    def test_returns_filament_list_dataclass(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        assert isinstance(fl, FilamentList)
        assert fl.total_size == len(fl.filaments)
        assert fl.total_size >= 1

    def test_metal_indices_partition(self, spiral, tech):
        """The metal_indices and via_indices together cover everything."""
        fl = build_filament_list(spiral, tech)
        all_indices = sorted(fl.metal_indices + fl.via_indices)
        assert all_indices == list(range(fl.total_size))

    def test_n_w_n_t_lengths_match_segments(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        n_segs = len(spiral.segments())
        assert len(fl.n_w) == n_segs
        assert len(fl.n_t) == n_segs
        assert all(n >= 1 for n in fl.n_w)
        assert all(n >= 1 for n in fl.n_t)

    def test_freq_dependent_subdivisions(self, spiral, tech):
        """Higher frequency (smaller skin depth) should produce more
        per-segment filaments — but capped at n_max."""
        fl_low = build_filament_list(spiral, tech, freq_ghz=0.001)
        fl_high = build_filament_list(spiral, tech, freq_ghz=10.0,
                                      n_w_max=4, n_t_max=4)
        assert sum(fl_low.n_w) <= sum(fl_high.n_w)

    def test_empty_shape_returns_empty_list(self, tech):
        from reasitic.geometry import Shape
        empty = Shape(name="EMPTY")
        fl = build_filament_list(empty, tech)
        assert fl.total_size == 0
        assert fl.filaments == []

    def test_filament_list_setup_alias_returns_same(self, spiral, tech):
        a = build_filament_list(spiral, tech, freq_ghz=2.0)
        b = filament_list_setup(spiral, tech, freq_ghz=2.0)
        assert a.total_size == b.total_size
        assert a.metal_indices == b.metal_indices


# fill_inductance_* -------------------------------------------------------


class TestFillInductanceDiagonal:
    def test_returns_diagonal_complex_matrix(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_diagonal(fl.filaments, omega_rad=2 * math.pi * 1e9)
        assert Z.shape == (fl.total_size, fl.total_size)
        # Off-diagonal must be zero
        off = Z - np.diag(np.diag(Z))
        np.testing.assert_allclose(off, 0.0, atol=1e-15)

    def test_real_part_zero_without_resistance(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_diagonal(fl.filaments, omega_rad=2 * math.pi * 1e9)
        np.testing.assert_allclose(np.diag(Z).real, 0.0, atol=1e-15)

    def test_diagonal_imag_scales_with_omega(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z1 = fill_inductance_diagonal(fl.filaments, omega_rad=1e9)
        Z2 = fill_inductance_diagonal(fl.filaments, omega_rad=2e9)
        np.testing.assert_allclose(np.diag(Z2).imag, 2.0 * np.diag(Z1).imag,
                                    rtol=1e-9)

    def test_resistance_added_to_real_part(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_diagonal(fl.filaments, tech=tech,
                                      freq_ghz=2.0, omega_rad=0.0)
        # Metal-layer filaments have positive R contribution
        diag_re = np.diag(Z).real
        assert np.any(diag_re > 0)

    def test_empty_filament_list(self):
        Z = fill_inductance_diagonal([], omega_rad=1e9)
        assert Z.shape == (0, 0)


class TestFillInductanceOffdiag:
    def test_diagonal_is_zero(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_offdiag(fl.filaments, omega_rad=2 * math.pi * 1e9)
        np.testing.assert_allclose(np.diag(Z), 0.0, atol=1e-15)

    def test_symmetric(self, spiral, tech):
        """M_ij = M_ji ⇒ Z is symmetric."""
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_offdiag(fl.filaments, omega_rad=2 * math.pi * 1e9)
        np.testing.assert_allclose(Z, Z.T, atol=1e-12)

    def test_pure_imaginary_part(self, spiral, tech):
        """No resistive contribution: all entries are purely imaginary."""
        fl = build_filament_list(spiral, tech)
        Z = fill_inductance_offdiag(fl.filaments, omega_rad=2 * math.pi * 1e9)
        np.testing.assert_allclose(Z.real, 0.0, atol=1e-15)


class TestFillImpedanceMatrixTriangular:
    def test_combines_diagonal_and_offdiag(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        omega = 2 * math.pi * 2e9
        Z = fill_impedance_matrix_triangular(
            fl.filaments, tech=tech, freq_ghz=2.0, omega_rad=omega,
        )
        Zd = fill_inductance_diagonal(
            fl.filaments, tech=tech, freq_ghz=2.0, omega_rad=omega,
        )
        Zo = fill_inductance_offdiag(fl.filaments, omega_rad=omega)
        np.testing.assert_allclose(Z, Zd + Zo, atol=1e-12)

    def test_symmetric_under_no_resistance(self, spiral, tech):
        fl = build_filament_list(spiral, tech)
        Z = fill_impedance_matrix_triangular(
            fl.filaments, omega_rad=2 * math.pi * 1e9,
        )
        # When R = 0 everywhere, Z = jω·M is symmetric
        np.testing.assert_allclose(Z, Z.T, atol=1e-12)


# filament_pair_4corner_integration ---------------------------------------


class TestFilamentPair4CornerIntegration:
    def test_returns_four_distances(self):
        a = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        b = Segment(
            a=Point(0, 10, 0), b=Point(100, 10, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        d_a1b1, d_a1b2, d_a2b1, d_a2b2 = filament_pair_4corner_integration(a, b)
        assert d_a1b1 == pytest.approx(10.0)            # (0,0)→(0,10)
        assert d_a1b2 == pytest.approx(math.sqrt(100**2 + 10**2))
        assert d_a2b1 == pytest.approx(math.sqrt(100**2 + 10**2))
        assert d_a2b2 == pytest.approx(10.0)

    def test_swap_segments_swaps_distances(self):
        a = Segment(
            a=Point(0, 0, 0), b=Point(50, 0, 0),
            width=0.0, thickness=0.0, metal=0,
        )
        b = Segment(
            a=Point(0, 0, 5), b=Point(50, 0, 5),
            width=0.0, thickness=0.0, metal=0,
        )
        d1 = filament_pair_4corner_integration(a, b)
        d2 = filament_pair_4corner_integration(b, a)
        # The 4-corner set is identical, just permuted
        assert sorted(d1) == pytest.approx(sorted(d2))
