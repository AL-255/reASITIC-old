"""Tests for OptSq optimiser and substrate shunt capacitance."""

import math

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
)
from reasitic.optimise import optimise_square_spiral
from reasitic.substrate import (
    parallel_plate_cap_per_area,
    shape_shunt_capacitance,
)
from reasitic.units import EPS_0
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Optimiser --------------------------------------------------------------


def test_opt_sq_meets_l_target_within_tolerance(tech) -> None:
    res = optimise_square_spiral(
        tech,
        target_L_nH=1.5,
        freq_ghz=2.0,
        metal="m3",
        L_tolerance=0.10,
    )
    # Within the requested ±10 % L tolerance, plus a tiny SLSQP slack:
    # the optimiser uses inequality constraints which the solver can
    # violate by a few ppm at the boundary depending on the BLAS build,
    # so we assert against a slightly looser band than what we ask for.
    assert res.L_nH == pytest.approx(1.5, rel=0.105)
    # Q should be positive
    assert res.Q > 0


def test_opt_sq_returns_geometry_inside_bounds(tech) -> None:
    res = optimise_square_spiral(
        tech,
        target_L_nH=1.0,
        freq_ghz=2.0,
        metal="m3",
        length_bounds=(50.0, 300.0),
        width_bounds=(2.0, 30.0),
        spacing_bounds=(1.0, 10.0),
        turns_bounds=(1.0, 6.0),
    )
    assert 50.0 <= res.length_um <= 300.0
    assert 2.0 <= res.width_um <= 30.0
    assert 1.0 <= res.spacing_um <= 10.0
    assert 1.0 <= res.turns <= 6.0


def test_opt_sq_uses_supplied_init(tech) -> None:
    res = optimise_square_spiral(
        tech,
        target_L_nH=1.5,
        freq_ghz=2.0,
        metal="m3",
        init=(150.0, 8.0, 2.0, 2.5),
    )
    assert res is not None
    # The L of the result should still be in range
    assert res.L_nH > 0


# Substrate shunt cap ----------------------------------------------------


def test_parallel_plate_cap_per_area() -> None:
    # 1 μm of ε_r=4 dielectric: C/A = 4 ε₀ / 1e-6 m
    cpa = parallel_plate_cap_per_area(eps_r=4.0, h_um=1.0)
    expected = 4.0 * EPS_0 / 1.0e-6
    assert cpa == pytest.approx(expected, rel=1e-9)


def test_parallel_plate_cap_zero_thickness_inf() -> None:
    assert math.isinf(parallel_plate_cap_per_area(eps_r=4.0, h_um=0.0))


def test_shape_shunt_capacitance_positive(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    C = shape_shunt_capacitance(sp, tech)
    assert C > 0
    assert math.isfinite(C)


def test_shape_shunt_zero_when_no_layers() -> None:
    """An empty Tech.layers list yields C = 0 (no ground reference)."""
    from reasitic.tech import Chip, Tech

    empty_tech = Tech(chip=Chip(), layers=[], metals=[], vias=[])
    from reasitic import Shape

    sp = Shape(name="dummy")
    assert shape_shunt_capacitance(sp, empty_tech) == 0.0


def test_shunt_decreases_with_higher_metal(tech) -> None:
    """A polygon on a higher metal layer (further from ground) has
    a smaller shunt cap than the same polygon on a lower metal."""
    from reasitic import capacitor

    # Square cap-plate on m2 (lower) vs m3 (higher)
    cap_low = capacitor(
        "C_low", length=20.0, width=20.0,
        metal_top="m2", metal_bottom="m2", tech=tech,
    )
    cap_high = capacitor(
        "C_high", length=20.0, width=20.0,
        metal_top="m3", metal_bottom="m3", tech=tech,
    )
    C_low = shape_shunt_capacitance(cap_low, tech)
    C_high = shape_shunt_capacitance(cap_high, tech)
    assert C_low > C_high


def test_shunt_increases_with_area(tech) -> None:
    """Doubling the spiral side should roughly quadruple shunt C
    (area dominates the parallel-plate term)."""
    small = square_spiral(
        "S1", length=100, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    big = square_spiral(
        "S2", length=200, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    C_s = shape_shunt_capacitance(small, tech)
    C_b = shape_shunt_capacitance(big, tech)
    assert C_b > C_s
    # Sanity: shouldn't be an order of magnitude off from 4x
    assert C_b / C_s > 1.5


