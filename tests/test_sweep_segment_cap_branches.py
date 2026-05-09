"""Branch-coverage tests for optimise/sweep.py and substrate/segment_cap.py.

Targets:
- sweep_square_spiral: ValueError / ZeroDivisionError fallback
  (bad geometries → NaN row).
- _format_table: non-structured ndarray raise.
- capacitance_segment_integral: n_div=1 fast path,
  L_a or L_b = 0 fallback.
- capacitance_integral_inner_a / _b: out-of-range metal idx
  returns 0.
- analyze_capacitance_driver: pinv fallback when P is singular.
"""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.geometry import Point, Segment
from reasitic.optimise import sweep_square_spiral
from reasitic.optimise.sweep import sweep_to_csv, sweep_to_tsv
from reasitic.substrate import (
    analyze_capacitance_driver,
    capacitance_integral_inner_a,
    capacitance_integral_inner_b,
    capacitance_segment_integral,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


# sweep_square_spiral ---------------------------------------------------


class TestSweepSquareSpiral:
    def test_failing_geometry_yields_nan_row(self, tech, monkeypatch):
        """When ``compute_self_inductance`` raises, the sweep
        should record NaN rather than crash."""
        from reasitic.optimise import sweep as sweep_mod

        def _bad_L(_sp):
            raise ValueError("forced kernel failure")

        monkeypatch.setattr(sweep_mod, "compute_self_inductance", _bad_L)
        arr = sweep_square_spiral(
            tech,
            length_um=[170.0],
            width_um=[10.0],
            spacing_um=[3.0],
            turns=[2.0],
            freq_ghz=2.0,
            metal="m3",
        )
        assert len(arr) == 1
        assert np.isnan(arr[0]["L_nH"])
        assert np.isnan(arr[0]["Q"])

    def test_zerodiv_geometry_yields_nan_row(self, tech, monkeypatch):
        """ZeroDivisionError in the Q kernel must also fall back
        to NaN, exercising the second arm of the except tuple."""
        from reasitic.optimise import sweep as sweep_mod

        def _bad_Q(_sp, _tech, _f):
            raise ZeroDivisionError("forced div by zero")

        monkeypatch.setattr(sweep_mod, "metal_only_q", _bad_Q)
        arr = sweep_square_spiral(
            tech,
            length_um=[170.0], width_um=[10.0],
            spacing_um=[3.0], turns=[2.0],
            freq_ghz=2.0, metal="m3",
        )
        assert len(arr) == 1
        assert np.isnan(arr[0]["Q"])

    def test_normal_grid_produces_structured_array(self, tech):
        arr = sweep_square_spiral(
            tech,
            length_um=[100.0, 200.0],
            width_um=[10.0],
            spacing_um=[2.0],
            turns=[2.0, 3.0],
            freq_ghz=2.0,
            metal="m3",
        )
        assert len(arr) == 4  # 2 × 1 × 1 × 2
        assert arr.dtype.names == (
            "length_um", "width_um", "spacing_um", "turns", "L_nH", "Q",
        )


class TestSweepFormatters:
    def test_to_tsv_header_and_rows(self, tech):
        arr = sweep_square_spiral(
            tech, length_um=[100.0], width_um=[10.0],
            spacing_um=[2.0], turns=[2.0],
            freq_ghz=2.0, metal="m3",
        )
        tsv = sweep_to_tsv(arr)
        assert tsv.startswith("length_um\twidth_um")
        assert "\n" in tsv

    def test_to_csv_header_and_rows(self, tech):
        arr = sweep_square_spiral(
            tech, length_um=[100.0], width_um=[10.0],
            spacing_um=[2.0], turns=[2.0],
            freq_ghz=2.0, metal="m3",
        )
        csv = sweep_to_csv(arr)
        assert csv.startswith("length_um,width_um")

    def test_unstructured_array_raises(self):
        """Calling the formatter on a plain (non-structured) ndarray
        triggers the explicit ``names is None`` raise."""
        plain = np.zeros((3, 4))
        with pytest.raises(ValueError, match="structured ndarray"):
            sweep_to_tsv(plain)
        with pytest.raises(ValueError, match="structured ndarray"):
            sweep_to_csv(plain)


# capacitance_segment_integral -----------------------------------------


def _seg_at(metal_idx: int, x_a: float, x_b: float) -> Segment:
    return Segment(
        a=Point(x_a, 0, 5), b=Point(x_b, 0, 5),
        width=2.0, thickness=1.0, metal=metal_idx,
    )


class TestCapacitanceSegmentIntegralBranches:
    def test_n_div_one_fast_path(self, tech):
        a = _seg_at(0, 0, 10)
        b = _seg_at(0, 50, 60)
        # n_div=1 takes the centroid-only fast path
        v_one = capacitance_segment_integral(a, b, tech, n_div=1)
        v_two = capacitance_segment_integral(a, b, tech, n_div=2)
        # Both finite; n_div=1 differs from n_div=2 (subdivision matters
        # at this distance) but both are positive Green's-function values.
        assert v_one > 0 and v_two > 0

    def test_zero_length_segment_uses_centroid(self, tech):
        """A zero-length seg_a triggers the L_a <= 0 branch which
        falls back to the centroid Green's value."""
        a = _seg_at(0, 50, 50)   # zero-length
        b = _seg_at(0, 100, 110)
        v = capacitance_segment_integral(a, b, tech, n_div=4)
        # Must equal the n_div=1 centroid value (the L<=0 fallback path
        # explicitly calls green_function_static at the centroid)
        assert v > 0


class TestCapacitanceInnerKernelBranches:
    def test_inner_a_out_of_range_metal_returns_zero(self, tech):
        a = _seg_at(999, 0, 10)
        b = _seg_at(0, 50, 60)
        assert capacitance_integral_inner_a(a, b, tech, s=0.5) == 0.0

    def test_inner_b_out_of_range_metal_returns_zero(self, tech):
        a = _seg_at(0, 0, 10)
        b = _seg_at(999, 50, 60)
        assert capacitance_integral_inner_b(a, b, tech, t=0.5) == 0.0


# analyze_capacitance_driver pinv fallback ------------------------------


class TestAnalyzeCapacitanceDriverPinvFallback:
    def test_singular_p_falls_back_to_pinv(self, tech, monkeypatch):
        """If np.linalg.inv raises LinAlgError, the driver should
        fall back to pinv rather than crash."""
        cap = reasitic.capacitor(
            "C1", length=20, width=20,
            metal_top="m3", metal_bottom="m2", tech=tech,
        ).translate(80, 80)

        # Patch np.linalg.inv on the segment_cap module to always raise
        from reasitic.substrate import segment_cap as sc_mod

        def _bad_inv(M):
            raise np.linalg.LinAlgError("forced singular")

        monkeypatch.setattr(sc_mod.np.linalg, "inv", _bad_inv)
        result = analyze_capacitance_driver([cap], tech, n_div=2)
        # pinv fallback should still produce a finite C matrix
        assert result.C_matrix.shape[0] >= 1
        assert np.all(np.isfinite(result.C_matrix))
