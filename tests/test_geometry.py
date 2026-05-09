import math
from pathlib import Path

import pytest

from reasitic import (
    Point,
    Polygon,
    Segment,
    parse_tech_file,
    polygon_spiral,
    square_spiral,
    wire,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


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


def test_square_spiral_two_turns(tech) -> None:
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    assert sp.name == "S1"
    assert sp.sides == 4
    # 2 full turns → 2 closed square loops
    assert len(sp.polygons) == 2
    # Each loop is 4 segments
    for poly in sp.polygons:
        assert len(poly.edges()) == 4
    # Outer loop: 170 μm → outer half = 85, side length = 170
    outer_segs = sp.polygons[0].edges()
    for s in outer_segs:
        assert s.length == pytest.approx(170.0)
    # Second loop pitch: width + spacing = 13, so side length = 170 - 26 = 144
    inner_segs = sp.polygons[1].edges()
    for s in inner_segs:
        assert s.length == pytest.approx(144.0)


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


def test_shape_translate(tech) -> None:
    sp = square_spiral(
        "S1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=1.0,
        tech=tech,
        metal="m3",
    )
    moved = sp.translate(50.0, 0.0)
    assert moved.x_origin == 50.0
    assert moved.polygons[0].vertices[0].x == pytest.approx(50.0 + 50.0)


def test_bounding_box(tech) -> None:
    sp = square_spiral(
        "S1",
        length=200.0,
        width=10.0,
        spacing=2.0,
        turns=1.0,
        tech=tech,
        metal="m3",
    )
    xmin, ymin, xmax, ymax = sp.bounding_box()
    assert xmin == pytest.approx(-100.0)
    assert xmax == pytest.approx(+100.0)
    assert ymin == pytest.approx(-100.0)
    assert ymax == pytest.approx(+100.0)


def test_fractional_turns(tech) -> None:
    sp = square_spiral(
        "S1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=1.5,
        tech=tech,
        metal="m3",
    )
    # 1 full loop + half loop (2 segments)
    assert len(sp.polygons) == 2
    full = sp.polygons[0]
    partial = sp.polygons[1]
    assert len(full.edges()) == 4
    assert len(partial.edges()) == 2
