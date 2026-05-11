"""Tests for inter-shape mutual inductance and coupling coefficient."""

import pytest

from reasitic import (
    compute_mutual_inductance,
    coupling_coefficient,
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.inductance.grover import parallel_segment_mutual
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Mutual between two parallel wires --------------------------------------


def test_two_parallel_wires_match_grover(tech) -> None:
    """Two co-extensive parallel wires should produce a mutual M
    that matches the standalone parallel_segment_mutual result.

    Build wire A on m3, wire B on m3 offset 50 μm in y. They run
    along x (orientation default). Both wires have the same length
    100 μm; their sep is purely in y (50 μm) since both at z=6.
    """
    a = wire("A", length=100.0, width=10.0, tech=tech, metal="m3", y_origin=0.0)
    b = wire("B", length=100.0, width=10.0, tech=tech, metal="m3", y_origin=50.0)
    M = compute_mutual_inductance(a, b)
    expected = parallel_segment_mutual(100.0, 100.0, 50.0, offset_um=0.0)
    assert pytest.approx(expected, rel=1e-9) == M


def test_anti_parallel_wires_negative_mutual(tech) -> None:
    """A wire and its phase-flipped twin (currents oppose) should
    produce the negative mutual."""
    a = wire("A", length=100.0, width=10.0, tech=tech, metal="m3")
    # Flip the second wire by reversing its endpoints
    b = wire("B", length=100.0, width=10.0, tech=tech, metal="m3", y_origin=50.0)
    seg_b = b.polygons[0].vertices
    b.polygons[0].vertices = list(reversed(seg_b))
    M = compute_mutual_inductance(a, b)
    expected = parallel_segment_mutual(100.0, 100.0, 50.0, offset_um=0.0)
    assert pytest.approx(-expected, rel=1e-9) == M


# Coupling coefficient ---------------------------------------------------


def test_coupling_zero_for_distant_loops(tech) -> None:
    """Two square spirals far apart should have very small k."""
    a = square_spiral(
        "A", length=100.0, width=10.0, spacing=2.0, turns=2.0, tech=tech, metal="m3"
    )
    b = square_spiral(
        "B",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal="m3",
        x_origin=10000.0,
    )
    k = coupling_coefficient(a, b)
    assert abs(k) < 1e-3


def test_coupling_strong_for_adjacent_spirals(tech) -> None:
    """Two identical spirals offset by their own outer side give a
    moderate coupling. Sanity bounds: k must be in [-1, 1] and be
    non-trivial (>0.05)."""
    a = square_spiral(
        "A", length=200.0, width=10.0, spacing=2.0, turns=3.0, tech=tech, metal="m3"
    )
    b = square_spiral(
        "B",
        length=200.0,
        width=10.0,
        spacing=2.0,
        turns=3.0,
        tech=tech,
        metal="m3",
        x_origin=210.0,  # just barely separated
    )
    k = coupling_coefficient(a, b)
    assert 0.05 < abs(k) < 1.0


def test_coupling_decays_with_distance(tech) -> None:
    """k should be largest at zero distance and decrease with offset."""
    a = square_spiral(
        "A", length=100.0, width=10.0, spacing=2.0, turns=2.0, tech=tech, metal="m3"
    )
    near = square_spiral(
        "B1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal="m3",
        x_origin=200.0,
    )
    far = square_spiral(
        "B2",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal="m3",
        x_origin=2000.0,
    )
    k_near = abs(coupling_coefficient(a, near))
    k_far = abs(coupling_coefficient(a, far))
    assert k_near > k_far
    assert k_far < 0.05  # very weak coupling at 20× spacing


def test_mutual_zero_when_either_shape_empty(tech) -> None:
    a = wire("A", length=100.0, width=10.0, tech=tech, metal="m3")
    from reasitic import Shape

    empty = Shape(name="empty")
    assert compute_mutual_inductance(a, empty) == 0.0
    assert coupling_coefficient(a, empty) == 0.0


