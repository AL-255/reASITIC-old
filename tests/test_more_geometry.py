"""Tests for the additional shape builders: ring, via, transformer,
symsq, capacitor, balun."""

import pytest

from reasitic import (
    balun,
    capacitor,
    parse_tech_file,
    ring,
    symmetric_square,
    transformer,
    via,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Ring -------------------------------------------------------------------


def test_ring_one_loop(tech) -> None:
    r = ring("R1", radius=50.0, width=5.0, sides=8, tech=tech, metal="m3")
    assert len(r.polygons) == 1
    # 8-sided ring → 9 vertices (closed)
    assert len(r.polygons[0].vertices) == 9


def test_ring_default_sides(tech) -> None:
    r = ring("R1", radius=100.0, width=5.0, tech=tech, metal="m3")
    assert r.sides == 32


# Via --------------------------------------------------------------------


def test_via_emits_pad_polygons_on_both_metals(tech) -> None:
    """C-faithful: cmd_via_build_geometry emits a polygon record at
    the via shape's origin tagged with both metal-layer colours, which
    CIF/GDS expanders write as a top-metal pad, a bottom-metal pad, and
    nx × ny VIA squares. The Python form returns these as separate
    polygons on the shape (top metal first, then bottom, then via grid).
    """
    v = via("V1", tech=tech, via_index=0, x_origin=0.0, y_origin=0.0)
    via_rec = tech.vias[0]
    # First two polys are the M2/M3 pad rectangles at the two metal
    # indices; remaining are nx × ny via squares.
    pad_metals = {v.polygons[0].metal, v.polygons[1].metal}
    assert pad_metals == {via_rec.top, via_rec.bottom}
    assert len(v.polygons) >= 3  # 2 pads + at least 1 via square


def test_via_array_dimensions(tech) -> None:
    """The cluster bbox spans ``nx · via_w + (nx-1) · via_s`` ×
    ``ny · via_w + (ny-1) · via_s`` (decoded from
    cmd_via_build_geometry @ :4091-4095).
    """
    v = via("V1", tech=tech, via_index=0, nx=3, ny=2)
    via_rec = tech.vias[0]
    expected_w = via_rec.width * 3 + via_rec.space * 2
    expected_h = via_rec.width * 2 + via_rec.space * 1
    # First pad polygon's bbox should equal the cluster span.
    pad_verts = v.polygons[0].vertices
    xs = [p.x for p in pad_verts[:-1]]
    ys = [p.y for p in pad_verts[:-1]]
    assert (max(xs) - min(xs)) == pytest.approx(expected_w)
    assert (max(ys) - min(ys)) == pytest.approx(expected_h)
    # nx × ny via squares emitted (= 6 here)
    via_squares = [p for p in v.polygons if p.metal >= len(tech.metals)]
    assert len(via_squares) == 3 * 2


def test_via_invalid_index_raises(tech) -> None:
    with pytest.raises(ValueError):
        via("V1", tech=tech, via_index=99)


# Transformer ------------------------------------------------------------


def test_transformer_two_coils(tech) -> None:
    t = transformer(
        "T1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal_primary="m3",
    )
    # 2 turns × 2 coils = 4 polygons
    assert len(t.polygons) == 4
    assert t.metal == tech.metal_by_name("m3").index


def test_transformer_two_metals(tech) -> None:
    t = transformer(
        "T1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal_primary="m2",
        metal_secondary="m3",
    )
    metals_used = {p.metal for p in t.polygons}
    assert metals_used == {
        tech.metal_by_name("m2").index,
        tech.metal_by_name("m3").index,
    }


# Symmetric square -------------------------------------------------------


def test_symsq_two_arms(tech) -> None:
    s = symmetric_square(
        "S1",
        length=200.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    # 2 turns × 2 arms = 4 polygons
    assert len(s.polygons) == 4


# Capacitor --------------------------------------------------------------


def test_capacitor_two_plates(tech) -> None:
    cap = capacitor(
        "C1",
        length=20.0,
        width=20.0,
        metal_top="m3",
        metal_bottom="m2",
        tech=tech,
    )
    assert len(cap.polygons) == 2
    metals = sorted(p.metal for p in cap.polygons)
    assert metals == sorted(
        [tech.metal_by_name("m3").index, tech.metal_by_name("m2").index]
    )


def test_capacitor_z_separation(tech) -> None:
    cap = capacitor(
        "C1",
        length=20.0,
        width=20.0,
        metal_top="m3",
        metal_bottom="m2",
        tech=tech,
    )
    z_top = cap.polygons[0].vertices[0].z
    z_bot = cap.polygons[1].vertices[0].z
    assert z_top != z_bot


# Balun ------------------------------------------------------------------


def test_balun_two_metals(tech) -> None:
    b = balun(
        "B1",
        length=100.0,
        width=10.0,
        spacing=2.0,
        turns=2.0,
        tech=tech,
        metal="m2",
        metal2="m3",
    )
    metals_used = {p.metal for p in b.polygons}
    assert len(metals_used) == 2