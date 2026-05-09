"""Tests for FastHenry export and auto-sized filament grid."""

from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.exports import write_fasthenry, write_fasthenry_file
from reasitic.geometry import Point, Segment
from reasitic.inductance import auto_filament_subdivisions
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# FastHenry export -----------------------------------------------------


def test_fasthenry_emits_header(tech) -> None:
    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    text = write_fasthenry(sp, tech)
    assert text.startswith("* reASITIC FastHenry input\n")
    assert ".units um" in text
    assert ".end" in text


def test_fasthenry_one_E_per_segment(tech) -> None:
    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    text = write_fasthenry(sp, tech)
    n_segments = len(sp.segments())
    # Each segment becomes one E directive
    e_lines = [line for line in text.splitlines() if line.startswith("E")]
    assert len(e_lines) == n_segments


def test_fasthenry_external_ports(tech) -> None:
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = write_fasthenry(w, tech)
    assert ".external" in text


def test_fasthenry_with_freqs(tech) -> None:
    w = wire("W1", length=100, width=10, tech=tech, metal="m3")
    text = write_fasthenry(w, tech, freqs_ghz=[1.0, 5.0, 10.0])
    assert ".freq" in text


def test_fasthenry_writes_file(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "L", length=100, width=10, spacing=2, turns=2, tech=tech, metal="m3"
    )
    out = tmp_path / "L.inp"
    write_fasthenry_file(out, sp, tech, freqs_ghz=[1.0, 5.0])
    assert out.read_text().startswith("* reASITIC")


# Auto-sized filament grid ---------------------------------------------


def test_auto_subdivisions_at_dc_returns_unity() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=10, thickness=2, metal=0
    )
    n_w, n_t = auto_filament_subdivisions(
        seg, rsh_ohm_per_sq=0.02, freq_ghz=0.0
    )
    assert n_w == 1
    assert n_t == 1


def test_auto_subdivisions_grow_with_frequency() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0), width=20, thickness=10, metal=0
    )
    n_w_lo, n_t_lo = auto_filament_subdivisions(
        seg, rsh_ohm_per_sq=0.02, freq_ghz=1.0
    )
    n_w_hi, n_t_hi = auto_filament_subdivisions(
        seg, rsh_ohm_per_sq=0.02, freq_ghz=20.0
    )
    # Higher freq → smaller skin depth → more subdivisions
    assert n_w_hi >= n_w_lo
    assert n_t_hi >= n_t_lo


def test_auto_subdivisions_capped_at_n_max() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(100, 0, 0),
        width=1000, thickness=1000, metal=0
    )
    n_w, n_t = auto_filament_subdivisions(
        seg, rsh_ohm_per_sq=0.001, freq_ghz=100.0, n_max=4
    )
    assert n_w <= 4
    assert n_t <= 4