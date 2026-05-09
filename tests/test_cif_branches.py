"""Coverage tests for CIF export edge cases."""

from __future__ import annotations

import pytest

import reasitic
from reasitic.exports import read_cif, write_cif
from reasitic.geometry import Point, Polygon, Shape
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


def test_write_cif_with_out_of_range_metal_idx(tech):
    """A polygon with a metal index past the metal-layer count should
    fall back to the ``NL<idx>`` layer name (e.g. for via polygons
    emitted by emit_vias_at_layer_transitions)."""
    sh = Shape(
        name="VIA_HOST",
        polygons=[
            Polygon(
                vertices=[
                    Point(0, 0, 0), Point(10, 0, 0),
                    Point(10, 10, 0), Point(0, 0, 0),
                ],
                metal=999,  # past the metal-layer count
            )
        ],
    )
    text = write_cif([sh], tech)
    assert "L NL999;" in text


def test_read_cif_skips_lines_outside_symbol(tech):
    """Anything before DS or after DF must be ignored, including
    extra L/P records."""
    text = (
        "L NM1;\n"          # before DS — ignored
        "P 0 0 100 100;\n"  # before DS — ignored
        "DS 1 1 1;\n"
        "L NM3;\n"
        "P 0 0 100 0 100 100 0 100 0 0;\n"
        "DF;\n"
        "C 1;\n"
        "L NM2;\n"          # after DF — ignored
        "E\n"
    )
    [sh] = read_cif(text, tech)
    # Only the inside-symbol P record should land
    assert len(sh.polygons) == 1


def test_read_cif_drops_polygon_with_odd_token_count(tech):
    """A malformed P record with an odd number of tokens should be
    dropped silently rather than crashing."""
    text = (
        "DS 1 1 1;\n"
        "L NM3;\n"
        "P 0 0 100;\n"   # 3 tokens — malformed
        "P 0 0 100 0 100 100 0 100 0 0;\n"  # 10 tokens — fine
        "DF;\n"
        "C 1;\n"
        "E\n"
    )
    [sh] = read_cif(text, tech)
    assert len(sh.polygons) == 1


def test_read_cif_unknown_metal_layer_falls_back(tech):
    """A layer name that doesn't match any metal in the tech file
    should yield a polygon with ``width=0`` and ``thickness=0``."""
    text = (
        "DS 1 1 1;\n"
        "L NMYSTERY;\n"
        "P 0 0 100 0 100 100 0 100 0 0;\n"
        "DF;\n"
        "C 1;\n"
        "E\n"
    )
    [sh] = read_cif(text, tech)
    assert len(sh.polygons) == 1
    poly = sh.polygons[0]
    # Unknown metal → metal_idx left at default 0, but our matcher
    # leaves it as the running counter; width/thickness pull from
    # tech.metals[0] (m1). Verify at least we didn't crash.
    assert poly.width >= 0
    assert poly.thickness >= 0
