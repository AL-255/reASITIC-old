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


def test_via_endpoints_span_both_metals(tech) -> None:
    v = via("V1", tech=tech, via_index=0, x_origin=0.0, y_origin=0.0)
    seg = v.polygons[0].vertices
    # Two endpoints, one at the bottom-metal z and one at the top-metal z
    assert len(seg) == 2
    via_rec = tech.vias[0]
    bot_z = tech.metals[via_rec.bottom].d + tech.metals[via_rec.bottom].t * 0.5
    top_z = tech.metals[via_rec.top].d + tech.metals[via_rec.top].t * 0.5
    zs = sorted(p.z for p in seg)
    assert zs[0] == pytest.approx(min(bot_z, top_z))
    assert zs[1] == pytest.approx(max(bot_z, top_z))


def test_via_array_dimensions(tech) -> None:
    v = via("V1", tech=tech, via_index=0, nx=3, ny=2)
    via_rec = tech.vias[0]
    expected_w = via_rec.width * 3 + via_rec.space * 2
    expected_t = via_rec.width * 2 + via_rec.space * 1
    assert v.polygons[0].width == pytest.approx(expected_w)
    assert v.polygons[0].thickness == pytest.approx(expected_t)


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