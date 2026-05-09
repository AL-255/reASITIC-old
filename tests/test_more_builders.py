"""Tests for SymPoly, MMSquare, CIF reader, LDIV."""

from pathlib import Path

import pytest

from reasitic import (
    multi_metal_square,
    parse_tech_file,
    square_spiral,
    symmetric_polygon,
)
from reasitic.exports import read_cif, read_cif_file, write_cif

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# SymPoly --------------------------------------------------------------


def test_sympoly_two_arms(tech) -> None:
    s = symmetric_polygon(
        "SP1",
        radius=100, width=10, spacing=2, turns=2,
        sides=8, tech=tech, metal="m3",
    )
    # 2 arms × 2 turns = 4 polygons
    assert len(s.polygons) == 4
    assert s.sides == 8


def test_sympoly_default_sides(tech) -> None:
    s = symmetric_polygon(
        "SP",
        radius=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    assert s.sides == 8


# MMSquare -------------------------------------------------------------


def test_mmsquare_one_metal(tech) -> None:
    """One metal → equivalent to a single square spiral."""
    mm = multi_metal_square(
        "MM",
        length=100, width=10, spacing=2, turns=2,
        tech=tech, metals=["m3"],
    )
    assert len(mm.polygons) == 2  # 2 turns


def test_mmsquare_three_metals(tech) -> None:
    """Three metals → 3 × turns polygons stacked."""
    mm = multi_metal_square(
        "MM",
        length=100, width=10, spacing=2, turns=2,
        tech=tech, metals=["msub", "m2", "m3"],
    )
    # 3 metals × 2 turns = 6 polygons
    assert len(mm.polygons) == 6


def test_mmsquare_uses_three_distinct_metal_indices(tech) -> None:
    mm = multi_metal_square(
        "MM",
        length=100, width=10, spacing=2, turns=2,
        tech=tech, metals=["m2", "m3"],
    )
    metals = {p.metal for p in mm.polygons}
    assert len(metals) == 2


def test_mmsquare_rejects_empty_metal_list(tech) -> None:
    with pytest.raises(ValueError):
        multi_metal_square(
            "MM",
            length=100, width=10, spacing=2, turns=2,
            tech=tech, metals=[],
        )


# CIF reader -----------------------------------------------------------


def test_cif_round_trip_basic(tech) -> None:
    """Write a wire to CIF, read it back, and compare."""
    from reasitic import wire
    w = wire("W", length=100, width=10, tech=tech, metal="m3")
    cif_text = write_cif([w], tech)
    shapes = read_cif(cif_text, tech)
    # We expect 1 shape with 1 polygon
    assert len(shapes) == 1
    assert len(shapes[0].polygons) == 1


def test_cif_round_trip_spiral(tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal="m3",
    )
    cif_text = write_cif([sp], tech)
    shapes = read_cif(cif_text, tech)
    # 2 turns → 2 polygons
    assert len(shapes[0].polygons) == 2


def test_cif_read_layer_resolution(tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    cif_text = write_cif([sp], tech)
    shapes = read_cif(cif_text, tech)
    # Layer should resolve back to m3's index
    m3_idx = tech.metal_by_name("m3").index
    assert shapes[0].polygons[0].metal == m3_idx


def test_cif_read_file(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    out = tmp_path / "S.cif"
    out.write_text(write_cif([sp], tech))
    shapes = read_cif_file(out, tech)
    assert len(shapes) == 1


# LDIV / OPTSYMPOLY via CLI -------------------------------------------


def test_ldiv_command(tech) -> None:
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("SQ NAME=L:LEN=100:W=10:S=2:N=2:METAL=m3")
    # Should not raise
    assert r.execute("LDIV L 1 1 1") is True


def test_optsympoly_command(tech) -> None:
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    assert r.execute("OPTSYMPOLY 1.0 2.0 8 m3") is True


# CLI builder commands ------------------------------------------------


def test_sympoly_cli(tech) -> None:
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("SYMPOLY NAME=SP:RAD=100:W=10:S=2:N=2:SIDES=8:METAL=m3")
    assert "SP" in r.shapes


def test_mmsquare_cli(tech) -> None:
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("MMSQUARE NAME=MM:LEN=100:W=10:S=2:N=2:METALS=m2,m3")
    assert "MM" in r.shapes
