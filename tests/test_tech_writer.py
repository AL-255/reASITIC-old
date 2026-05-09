"""Round-trip tests for the tech-file writer."""

from pathlib import Path

import pytest

from reasitic import (
    parse_tech,
    parse_tech_file,
    write_tech,
    write_tech_file,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")
_CMOS = _paths.tech_path("CMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


def test_write_tech_round_trips_bicmos(tech) -> None:
    text = write_tech(tech)
    tech2 = parse_tech(text)
    assert tech2.chip.chipx == tech.chip.chipx
    assert tech2.chip.chipy == tech.chip.chipy
    assert tech2.chip.fftx == tech.chip.fftx
    assert tech2.chip.eddy == tech.chip.eddy
    assert len(tech2.layers) == len(tech.layers)
    assert len(tech2.metals) == len(tech.metals)
    assert len(tech2.vias) == len(tech.vias)


def test_write_tech_preserves_metal_rsh(tech) -> None:
    text = write_tech(tech)
    tech2 = parse_tech(text)
    for m1, m2 in zip(tech.metals, tech2.metals, strict=True):
        # rsh is converted to mΩ/sq on write and back to Ω/sq on parse;
        # round-trip should match within float precision
        assert m1.rsh == pytest.approx(m2.rsh, rel=1e-6)
        assert m1.name == m2.name
        assert m1.t == pytest.approx(m2.t)


def test_write_tech_preserves_via_records(tech) -> None:
    text = write_tech(tech)
    tech2 = parse_tech(text)
    for v1, v2 in zip(tech.vias, tech2.vias, strict=True):
        assert v1.top == v2.top
        assert v1.bottom == v2.bottom
        assert v1.r == pytest.approx(v2.r)
        assert v1.width == pytest.approx(v2.width)


def test_write_tech_file_round_trip(tmp_path: Path, tech) -> None:
    out = tmp_path / "round_trip.tek"
    write_tech_file(tech, out)
    assert out.exists()
    tech2 = parse_tech_file(out)
    assert len(tech2.metals) == len(tech.metals)


@pytest.mark.skipif(not _CMOS.exists(), reason="CMOS.tek not vendored")
def test_write_tech_round_trips_cmos() -> None:
    tech = parse_tech_file(_CMOS)
    text = write_tech(tech)
    tech2 = parse_tech(text)
    assert len(tech2.layers) == 2
    assert len(tech2.metals) == 5
    assert len(tech2.vias) == 4


def test_write_tech_emits_chip_section(tech) -> None:
    text = write_tech(tech)
    assert "<chip>" in text
    assert "chipx" in text
    assert "<layer>" in text
    assert "<metal>" in text
    assert "<via>" in text