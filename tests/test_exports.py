"""Tests for layout file exporters: CIF, Tek, Sonnet."""

from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.exports import (
    write_cif,
    write_cif_file,
    write_sonnet,
    write_tek,
    write_tek_file,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# CIF --------------------------------------------------------------------


def test_cif_writes_symbol_definition(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = write_cif([sp], tech)
    assert text.startswith("DS 1 1 1;")
    assert "DF;" in text
    assert text.rstrip().endswith("E")


def test_cif_uses_layer_name_from_tech(tech) -> None:
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = write_cif([w], tech)
    # The metal layer's name in BiCMOS.tek is "m3" → CIF uses "NM3"
    assert "L NM3;" in text


def test_cif_polygon_count_matches_shape(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = write_cif([sp], tech)
    # Two full turns → two P (polygon) statements
    assert text.count("P ") == 2


def test_cif_writes_to_file(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    out = tmp_path / "spiral.cif"
    write_cif_file(out, [sp], tech)
    assert out.exists()
    assert out.read_text().startswith("DS 1 1 1;")


def test_cif_centi_micron_scaling(tech) -> None:
    """Default scale is 0.01 μm per CIF unit, so a 100 μm wire writes
    coordinates spanning 10000 units."""
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = write_cif([w], tech)
    # Expect "5000" or "-5000" to appear (half-length × 100)
    assert "5000" in text


# Tek (gnuplot-style) ----------------------------------------------------


def test_tek_writes_blocks(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = write_tek([sp])
    # Two polygons → two header lines
    assert text.count("# name=S") == 2
    # And blank-line separators
    assert "\n\n" in text


def test_tek_x_y_coords_present(tech) -> None:
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = write_tek([w])
    lines = [line for line in text.splitlines() if line and not line.startswith("#")]
    # Should have 2 vertices for the wire
    assert len(lines) == 2
    x0, _y0 = (float(v) for v in lines[0].split())
    x1, _y1 = (float(v) for v in lines[1].split())
    assert x1 - x0 == pytest.approx(100.0)


def test_tek_writes_to_file(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    out = tmp_path / "plot.tek"
    write_tek_file(out, [sp])
    assert out.read_text().count("# name=S") == 2


# Sonnet -----------------------------------------------------------------


def test_sonnet_emits_header_and_geo(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = write_sonnet([sp], tech)
    assert text.startswith("FTYP SONPROJ")
    assert "GEO" in text
    assert "END\n" in text


def test_sonnet_polygon_count(tech) -> None:
    sp = square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    text = write_sonnet([sp], tech)
    # Two polygons → two NUM directives
    assert text.count("NUM ") == 2
    assert text.count("LAYER ") == 2


def test_sonnet_box_dimensions(tech) -> None:
    text = write_sonnet([], tech)
    # BiCMOS chipx=512, chipy=512
    assert "BOX 1 512 512" in text
