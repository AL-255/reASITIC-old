import math

import pytest

from reasitic import (
    Point,
    Polygon,
    Segment,
    parse_tech_file,
    polygon_spiral,
    wire,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_point_ops() -> None:
    a = Point(1, 2, 3)
    b = Point(4, 5, 6)
    assert (a - b) == Point(-3, -3, -3)
    assert (a + b) == Point(5, 7, 9)
    assert a.distance_to(b) == pytest.approx(math.sqrt(27))


def test_segment_length_and_direction() -> None:
    s = Segment(Point(0, 0, 0), Point(3, 4, 0), width=1.0, thickness=1.0, metal=0)
    assert s.length == pytest.approx(5.0)
    dx, dy, dz = s.direction
    assert (dx, dy, dz) == pytest.approx((0.6, 0.8, 0.0))


def test_polygon_edges_count() -> None:
    poly = Polygon(
        vertices=[Point(0, 0), Point(1, 0), Point(1, 1), Point(0, 1), Point(0, 0)],
        metal=0,
        width=1.0,
        thickness=1.0,
    )
    edges = poly.edges()
    assert len(edges) == 4
    # All have length 1 (a unit square)
    for e in edges:
        assert e.length == pytest.approx(1.0)


def test_wire_builder(tech) -> None:
    w = wire(
        "W1",
        length=100.0,
        width=10.0,
        tech=tech,
        metal="m3",
        x_origin=0.0,
        y_origin=0.0,
    )
    assert w.name == "W1"
    assert w.width == 10.0
    segs = w.segments()
    assert len(segs) == 1
    assert segs[0].length == pytest.approx(100.0)
    # Wire on m3: z = d + t/2 = 5 + 1.0 = 6.0
    m3 = tech.metal_by_name("m3")
    assert segs[0].a.z == pytest.approx(m3.d + m3.t * 0.5)


def test_polygon_spiral_octagon(tech) -> None:
    sp = polygon_spiral(
        "OctSpiral",
        radius=100.0,
        width=10.0,
        spacing=3.0,
        turns=1.0,
        tech=tech,
        metal="m3",
        sides=8,
    )
    assert sp.sides == 8
    assert len(sp.polygons) == 1
    # 8 sides means 9 vertex points (start + 8 + close)... we set
    # sides=8 segments which means 9 vertices
    assert len(sp.polygons[0].vertices) == 9


