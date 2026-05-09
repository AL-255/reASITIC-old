"""Coverage tests for GDS export edge cases.

Exercises the rare branches that the main round-trip test doesn't
hit: degenerate (single-vertex) polygons, open polylines (FlexPath
rendering), and the read-back path-element branch.
"""

from __future__ import annotations

from pathlib import Path

import pytest

import reasitic
from reasitic.exports import read_gds_file, write_gds_file
from reasitic.geometry import Point, Polygon, Shape
from tests import _paths

gdstk = pytest.importorskip("gdstk")

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


def test_degenerate_polygon_skipped(tmp_path: Path):
    """A polygon with < 2 vertices should be silently skipped."""
    sh = Shape(
        name="DEGEN",
        polygons=[
            Polygon(vertices=[Point(0, 0, 0)], metal=0),  # 1 vertex
            Polygon(  # full triangle
                vertices=[
                    Point(0, 0, 0), Point(10, 0, 0),
                    Point(10, 10, 0), Point(0, 0, 0),
                ],
                metal=0,
            ),
        ],
    )
    p = tmp_path / "out.gds"
    write_gds_file(p, [sh])
    assert p.exists()
    # Read back — only the triangle should land
    [recovered] = read_gds_file(p)
    assert len(recovered.polygons) == 1


def test_open_polyline_via_flexpath(tmp_path: Path, tech):
    """A wire shape — a single open polyline — should round-trip via
    gdstk's FlexPath rendering.

    The reasitic ``wire`` builder emits an open polyline (start→end
    with no closing vertex), which exercises the ``else`` branch of
    ``_build_gds_library`` that builds a FlexPath with the polygon's
    width.
    """
    w = reasitic.wire("W1", length=80, width=4, metal="m3", tech=tech)
    # Force an open-polyline polygon — the wire builder typically
    # closes its loop, so build it manually to be sure.
    open_poly = Polygon(
        vertices=[Point(0, 0, 5), Point(50, 0, 5), Point(50, 30, 5)],
        metal=0,
        width=4.0,
    )
    sh = Shape(name="W_OPEN", polygons=[open_poly])
    p = tmp_path / "wire.gds"
    write_gds_file(p, [w, sh])
    assert p.exists()
    # Read back via the path element-handling branch
    recovered = read_gds_file(p, tech)
    names = {s.name for s in recovered}
    assert "W1" in names
    assert "W_OPEN" in names


def test_read_back_path_element(tmp_path: Path, tech):
    """Write a GDS with a path element via raw gdstk, then read it
    through reASITIC's reader to exercise the `cell.paths` branch."""
    lib = gdstk.Library(name="PATHTEST", unit=1e-6, precision=1e-9)
    cell = gdstk.Cell("PATH_CELL")
    path = gdstk.FlexPath(
        [(0, 0), (50, 0), (50, 30)],
        2.0,                # width
        layer=0,
        datatype=0,
    )
    cell.add(path)
    lib.add(cell)
    p = tmp_path / "path.gds"
    lib.write_gds(str(p))

    shapes = read_gds_file(p, tech)
    [recovered] = shapes
    assert recovered.name == "PATH_CELL"
    # Path got converted to one or more closed polygons in the reader
    assert len(recovered.polygons) >= 1
    for poly in recovered.polygons:
        assert poly.metal == 0


def test_polygon_with_two_vertices_not_closed():
    """``_is_closed`` returns False for any polygon with < 3 vertices."""
    from reasitic.exports.gds import _is_closed
    poly = Polygon(
        vertices=[Point(0, 0, 0), Point(0, 0, 0)], metal=0,
    )
    assert _is_closed(poly) is False


def test_unnamed_shape_writes_as_unnamed_cell(tmp_path: Path):
    """A shape with an empty name should be written as cell 'UNNAMED'."""
    sh = Shape(
        name="",
        polygons=[
            Polygon(
                vertices=[
                    Point(0, 0, 0), Point(5, 0, 0),
                    Point(5, 5, 0), Point(0, 0, 0),
                ],
                metal=0,
            )
        ],
    )
    p = tmp_path / "anon.gds"
    write_gds_file(p, [sh])
    assert p.exists()
    [back] = read_gds_file(p)
    assert back.name == "UNNAMED"
