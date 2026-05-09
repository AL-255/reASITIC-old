import pytest

from reasitic import parse_tech, parse_tech_file
from reasitic.tech import TechParseError
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")
_CMOS = _paths.tech_path("CMOS.tek")


@pytest.mark.skipif(not _BICMOS.exists(), reason="BiCMOS.tek not vendored")
def test_parse_bicmos_tek() -> None:
    tech = parse_tech_file(_BICMOS)
    # Chip section
    assert tech.chip.chipx == 512
    assert tech.chip.chipy == 512
    assert tech.chip.fftx == 128
    assert tech.chip.ffty == 128
    assert tech.chip.tech_file == "BiCMOS.tek"
    assert tech.chip.tech_path == "."
    assert tech.chip.freq == pytest.approx(0.1)
    # the file sets eddy = 0 then eddy = 1; latest wins
    assert tech.chip.eddy is True
    # Layers
    assert len(tech.layers) == 3
    assert tech.layers[0].rho == pytest.approx(10.0)
    assert tech.layers[0].t == pytest.approx(800.0)
    assert tech.layers[0].eps == pytest.approx(11.9)
    # Metals — note rsh converted from mΩ/sq to Ω/sq
    assert len(tech.metals) == 3
    msub = tech.metal_by_name("msub")
    assert msub.layer == 1
    assert msub.rsh == pytest.approx(0.035)
    assert msub.t == pytest.approx(0.4)
    m3 = tech.metal_by_name("m3")
    assert m3.index == 2
    assert m3.t == pytest.approx(2.0)
    # Vias
    assert len(tech.vias) == 2
    via3 = tech.via_by_name("via3")
    assert via3.top == 2
    assert via3.bottom == 1


@pytest.mark.skipif(not _CMOS.exists(), reason="CMOS.tek not vendored")
def test_parse_cmos_tek() -> None:
    tech = parse_tech_file(_CMOS)
    assert len(tech.layers) == 2
    assert len(tech.metals) == 5
    assert len(tech.vias) == 4
    # Sanity check: m1..m5 names exist
    for name in ("m1", "m2", "m3", "m4", "m5"):
        m = tech.metal_by_name(name)
        assert m.t == pytest.approx(0.5) or name == "m5"
    # m5 is thicker
    assert tech.metal_by_name("m5").t == pytest.approx(1.0)


def test_parse_inline_string() -> None:
    text = """
    <chip>
        chipx = 100
        chipy = 200
        freq = 2.4
        eddy = false

    <layer> 0
        rho = 1
        t = 100
        eps = 11.9
    """
    tech = parse_tech(text)
    assert tech.chip.chipx == 100
    assert tech.chip.eddy is False
    assert len(tech.layers) == 1


def test_unknown_keys_go_to_extra() -> None:
    text = """
    <metal> 0
        layer = 0
        name = m1
        weird_key = something
    """
    tech = parse_tech(text)
    metal = tech.metals[0]
    assert metal.name == "m1"
    assert metal.extra["weird_key"] == "something"


def test_comments_stripped() -> None:
    text = """
    <chip>
        chipx = 50  ; lateral chip width
        ; this entire line is a comment
        chipy = 75
    """
    tech = parse_tech(text)
    assert tech.chip.chipx == 50
    assert tech.chip.chipy == 75


def test_bool_parser_variants() -> None:
    for value in ("true", "TRUE", "1", "yes", "on"):
        text = f"<chip>\n    eddy = {value}\n"
        assert parse_tech(text).chip.eddy is True
    for value in ("false", "0", "off", "no"):
        text = f"<chip>\n    eddy = {value}\n"
        assert parse_tech(text).chip.eddy is False


def test_bool_parser_rejects_garbage() -> None:
    text = "<chip>\n    eddy = banana\n"
    with pytest.raises(TechParseError):
        parse_tech(text)