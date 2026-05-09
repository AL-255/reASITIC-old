"""Save/Load round-trip tests."""

import json
from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.persistence import (
    load_session,
    save_session,
    shape_from_dict,
    shape_to_dict,
    tech_from_dict,
    tech_to_dict,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_shape_dict_round_trip(tech) -> None:
    sp = square_spiral(
        "S1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )
    d = shape_to_dict(sp)
    sp2 = shape_from_dict(d)
    assert sp2.name == sp.name
    assert sp2.width == sp.width
    assert sp2.spacing == sp.spacing
    assert sp2.turns == sp.turns
    assert len(sp2.polygons) == len(sp.polygons)
    for p1, p2 in zip(sp.polygons, sp2.polygons, strict=True):
        for v1, v2 in zip(p1.vertices, p2.vertices, strict=True):
            assert v1.x == v2.x
            assert v1.y == v2.y
            assert v1.z == v2.z


def test_tech_dict_round_trip(tech) -> None:
    d = tech_to_dict(tech)
    tech2 = tech_from_dict(d)
    assert tech2.chip.chipx == tech.chip.chipx
    assert tech2.chip.fftx == tech.chip.fftx
    assert len(tech2.metals) == len(tech.metals)
    for m1, m2 in zip(tech.metals, tech2.metals, strict=True):
        assert m1.name == m2.name
        assert m1.rsh == m2.rsh


def test_session_round_trip(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S1", length=170.0, width=10.0, spacing=3.0, turns=2.0, tech=tech, metal="m3"
    )
    w = wire("W1", length=100.0, width=10.0, tech=tech, metal="m3")
    out = tmp_path / "session.json"
    save_session(out, tech=tech, shapes={"S1": sp, "W1": w})
    tech2, shapes = load_session(out)
    assert tech2 is not None
    assert tech2.metal_by_name("m3").rsh == tech.metal_by_name("m3").rsh
    assert set(shapes) == {"S1", "W1"}
    assert shapes["W1"].polygons[0].vertices[0].x == w.polygons[0].vertices[0].x


def test_session_without_tech(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S1", length=170.0, width=10.0, spacing=3.0, turns=2.0, tech=tech, metal="m3"
    )
    out = tmp_path / "shapes_only.json"
    save_session(out, shapes={"S1": sp})
    tech2, shapes = load_session(out)
    assert tech2 is None
    assert "S1" in shapes


def test_session_without_shapes(tmp_path: Path, tech) -> None:
    out = tmp_path / "tech_only.json"
    save_session(out, tech=tech)
    tech2, shapes = load_session(out)
    assert tech2 is not None
    assert shapes == {}


def test_load_rejects_future_version(tmp_path: Path) -> None:
    payload = {"version": 99, "tech": {"chip": {}}}
    out = tmp_path / "future.json"
    out.write_text(json.dumps(payload))
    with pytest.raises(ValueError):
        load_session(out)
