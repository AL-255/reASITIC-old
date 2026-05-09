"""Tests for the GUI metal/via color resolution."""

import pytest

import reasitic
from reasitic.gui.colors import metal_color, normalize, via_color
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


def test_normalize_known_aliases():
    # Known X11 names that Tk does not recognise
    assert normalize("greenish") == "#a8d8a8"
    assert normalize("yellowish") == "#d8d8a8"
    assert normalize("blueish") == "#a8a8d8"


def test_normalize_passthrough():
    assert normalize("red") == "red"
    assert normalize("#11aaff") == "#11aaff"
    assert normalize("") == "#888888"


def test_metal_color_uses_tech_field(tech):
    # In the BiCMOS tech file, m2 is "green" and m3 is "red"
    assert metal_color(tech, "m2").lower() in ("green", "#008000", "#00ff00")
    assert metal_color(tech, "m3").lower() in ("red", "#ff0000", "#800000")


def test_metal_color_unknown_falls_back():
    """Asking for a metal that doesn't exist returns the gray fallback."""
    fake_tech = type("T", (), {"metals": [], "vias": []})()
    assert metal_color(fake_tech, "nonexistent") == "#888888"


def test_via_color_uses_tech_field(tech):
    # via2 in BiCMOS is "greenish" → mapped to a hex code
    assert via_color(tech, "via2") == "#a8d8a8"