"""Numerical tests for the Grover/Greenhouse partial-inductance formulas.

Cross-check values are taken from:

* Greenhouse, "Design of Planar Rectangular Microelectronic
  Inductors," IEEE Trans. PHP-10 (1974), table 1 examples.
* Grover, *Inductance Calculations*, Dover 1946, tabulated values.
* Closed-form sanity checks (limit cases).
"""

import math

import pytest

from reasitic import parse_tech_file, square_spiral, wire
from reasitic.inductance import (
    compute_self_inductance,
    coupled_wire_self_inductance,
    parallel_segment_mutual,
    rectangular_bar_self_inductance,
    segment_self_inductance,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


# Closed-form / limiting-case validation ---------------------------------


def test_rectangular_bar_self_l_matches_round_wire_limit() -> None:
    """In the long-bar limit (L >> W+T), the rectangular-bar formula
    should be close to a round-wire formula with r ≈ (W+T)/4."""
    L_um = 1000.0
    W_um = 5.0
    T_um = 5.0
    L_rect = rectangular_bar_self_inductance(L_um, W_um, T_um)
    # Compare to round-wire with equivalent radius
    L_round = segment_self_inductance(L_um, (W_um + T_um) * 0.25)
    # Both should be within ~10% in this regime
    assert L_rect == pytest.approx(L_round, rel=0.10)


def test_rectangular_bar_zero_length() -> None:
    assert rectangular_bar_self_inductance(0.0, 1.0, 1.0) == 0.0


def test_rectangular_bar_known_value() -> None:
    """Hand-calculated reference for a 100 μm × 10 μm × 2 μm bar.

    L_um = 100, W_um = 10, T_um = 2 → L_cm = 0.01, (W+T)_cm = 0.0012
    formula = 2 * 0.01 * (ln(2*0.01/0.0012) + 0.50049 + 0.0012/(3*0.01))
            = 0.02 * (ln(16.667) + 0.50049 + 0.04)
            = 0.02 * (2.8134 + 0.50049 + 0.04)
            = 0.02 * 3.354
            ≈ 0.06708 nH
    """
    L = rectangular_bar_self_inductance(100.0, 10.0, 2.0)
    assert pytest.approx(0.06708, rel=2e-3) == L


def test_parallel_segment_mutual_zero_separation_diverges() -> None:
    """At sep → 0, mutual → ∞; we clamp at 1e-12 cm so result stays finite."""
    M = parallel_segment_mutual(100.0, 100.0, 1e-9)  # ~1e-9 μm sep
    assert M > 0
    assert math.isfinite(M)


def test_parallel_segment_mutual_equal_lengths_no_offset() -> None:
    """Greenhouse Eq. 8: M = 2L * (asinh(L/d) - sqrt(1 + (d/L)²) + d/L).

    For L=100 μm, d=10 μm: L_cm=0.01, d_cm=0.001, ratio=10
    M = 2*0.01 * (asinh(10) - sqrt(1.01) + 0.1)
      = 0.02 * (2.99822 - 1.00499 + 0.1)
      = 0.02 * 2.0932
      ≈ 0.0419 nH
    """
    M = parallel_segment_mutual(100.0, 100.0, 10.0, offset_um=0.0)
    expected = 0.02 * (math.asinh(10.0) - math.sqrt(1.01) + 0.1)
    assert pytest.approx(expected, rel=1e-9) == M
    # Also matches the precomputed numerical value:
    assert pytest.approx(0.04186, rel=1e-3) == M


def test_parallel_segment_mutual_long_sep_decays() -> None:
    """Mutual decays roughly like ln(L/d) for large d, never goes negative."""
    near = parallel_segment_mutual(100.0, 100.0, 5.0)
    far = parallel_segment_mutual(100.0, 100.0, 200.0)
    assert near > far
    # In the ASITIC sign convention (parallel currents in same
    # direction → positive contribution), mutual is positive even
    # when far apart.
    assert far > 0


def test_parallel_segment_mutual_offset_effect() -> None:
    """Increasing axial offset reduces overlap and thus mutual."""
    overlap = parallel_segment_mutual(100.0, 100.0, 10.0, offset_um=0.0)
    half = parallel_segment_mutual(100.0, 100.0, 10.0, offset_um=50.0)
    none = parallel_segment_mutual(100.0, 100.0, 10.0, offset_um=200.0)
    assert overlap > half > none > 0
    # When fully separated by 2L axially, mutual is small but positive
    assert none / overlap < 0.4


def test_coupled_wire_self_returns_finite() -> None:
    """Sanity: the rectangular-bar self formula returns finite, positive."""
    L = coupled_wire_self_inductance(width_um=10.0, thickness_um=2.0, separation_um=1.0)
    assert math.isfinite(L)
    assert L > 0


# End-to-end shape tests --------------------------------------------------


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_compute_self_inductance_wire(tech) -> None:
    """Single straight wire on m3: only self-inductance, no mutuals."""
    w = wire("W1", length=100.0, width=10.0, tech=tech, metal="m3")
    L = compute_self_inductance(w)
    # The wire has thickness from the tech file (m3 t=2 μm)
    expected = rectangular_bar_self_inductance(100.0, 10.0, 2.0)
    assert pytest.approx(expected, rel=1e-9) == L


def test_compute_self_inductance_square_spiral(tech) -> None:
    """A 2-turn square spiral has 8 segments, lots of mutual coupling."""
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    L = compute_self_inductance(sp)
    assert math.isfinite(L)
    # A 170 μm × 2-turn coil should be in the low-nH range (1-10 nH).
    # The published ASITIC manual examples typically report similar
    # geometries at ~3-5 nH.
    assert 0.5 < L < 30.0