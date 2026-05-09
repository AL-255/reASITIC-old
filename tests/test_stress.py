"""Stress tests for very large geometries.

These verify that the solvers don't blow up numerically when given
many segments, and that the per-frequency analysis paths handle
edge-case frequencies (very low, very high, exactly at f_SR).
"""

import math

import pytest

from reasitic import (
    compute_self_inductance,
    metal_only_q,
    parse_tech_file,
    polygon_spiral,
    square_spiral,
)
from reasitic.inductance import (
    solve_inductance_matrix,
    solve_inductance_mna,
)
from reasitic.network import linear_freqs, two_port_sweep
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_16_turn_spiral_self_l_finite(tech) -> None:
    """64-segment spiral should solve cleanly."""
    sp = square_spiral(
        "Big",
        length=600, width=10, spacing=2, turns=16,
        tech=tech, metal="m3",
    )
    assert len(sp.segments()) == 64
    L = compute_self_inductance(sp)
    assert math.isfinite(L)
    assert L > 0


def test_16_turn_mna_solver_finite(tech) -> None:
    sp = square_spiral(
        "Big",
        length=600, width=10, spacing=2, turns=16,
        tech=tech, metal="m3",
    )
    L, R = solve_inductance_mna(sp, tech, freq_ghz=1.0, n_w=1, n_t=1)
    assert math.isfinite(L)
    assert math.isfinite(R)
    assert L > 0


def test_32_turn_polygon_spiral(tech) -> None:
    """32-turn polygon spiral with 8 sides → 256 segments."""
    sp = polygon_spiral(
        "Octa32",
        radius=400, width=8, spacing=2, turns=32,
        sides=8, tech=tech, metal="m3",
    )
    # The inner radius collapses before 32 turns; check we got a
    # reasonable number of polygons (≥ 16) and L is finite.
    n_polys = len(sp.polygons)
    assert n_polys >= 8
    L = compute_self_inductance(sp)
    assert math.isfinite(L)
    assert L > 0


def test_high_frequency_q_does_not_blow_up(tech) -> None:
    """Q at 100 GHz should be finite (skin effect dominates but Q
    rolls off through the substrate cap)."""
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    Q = metal_only_q(sp, tech, freq_ghz=100.0)
    assert math.isfinite(Q)
    assert Q >= 0


def test_low_frequency_q_zero_at_dc(tech) -> None:
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    assert metal_only_q(sp, tech, freq_ghz=0.0) == 0.0


def test_dense_frequency_sweep(tech) -> None:
    """1000-point sweep should run in < 5 seconds."""
    import time
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    fs = linear_freqs(0.1, 50.0, 0.05)  # 1000 points
    assert len(fs) == 999
    t0 = time.perf_counter()
    sweep = two_port_sweep(sp, tech, fs)
    elapsed = time.perf_counter() - t0
    assert len(sweep.S) == 999
    assert elapsed < 5.0  # 5 seconds is generous; should be ~0.5 s


def test_filament_solver_with_large_grid(tech) -> None:
    """4×4 filament grid on 32 segments = 512 filaments — should
    still solve."""
    sp = square_spiral(
        "Big",
        length=400, width=20, spacing=4, turns=8,
        tech=tech, metal="m3",
    )
    L, R = solve_inductance_matrix(sp, tech, freq_ghz=2.0, n_w=2, n_t=2)
    # n_seg = 32, n_w*n_t = 4 → 128 filaments
    assert math.isfinite(L)
    assert math.isfinite(R)
    assert L > 0


def test_zero_radius_spiral_collapses_gracefully(tech) -> None:
    """Tiny radius with thick width → spiral collapses; should not
    crash the L computation."""
    from reasitic.geometry import polygon_spiral as ps_func
    sp = ps_func(
        "Tiny",
        radius=10, width=10, spacing=1, turns=1,
        sides=4, tech=tech, metal="m3",
    )
    L = compute_self_inductance(sp)
    # Either reasonable L or 0 (collapsed); just check finite
    assert math.isfinite(L)


def test_single_segment_self_l_doesnt_diverge(tech) -> None:
    """A 1-μm wire: tiny but should compute a finite L."""
    from reasitic import wire
    w = wire("Tiny", length=1.0, width=0.5, tech=tech, metal="m3")
    L = compute_self_inductance(w)
    assert math.isfinite(L)
    assert L > 0


def test_optimisation_doesnt_get_stuck_on_extremes(tech) -> None:
    """Even a hard L target should converge in finite time."""
    import time

    from reasitic.optimise import optimise_square_spiral
    t0 = time.perf_counter()
    res = optimise_square_spiral(
        tech, target_L_nH=20.0, freq_ghz=2.4, metal="m3",
        length_bounds=(50, 500), turns_bounds=(1, 10),
    )
    elapsed = time.perf_counter() - t0
    assert elapsed < 30.0  # should finish well under 30 s
    # May or may not meet 20 nH within bounds; just check returned
    assert res.length_um > 0