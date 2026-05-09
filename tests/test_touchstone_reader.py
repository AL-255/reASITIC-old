"""Round-trip tests for the Touchstone reader/writer."""

from pathlib import Path

import numpy as np
import pytest

from reasitic.network import (
    TouchstoneFile,
    TouchstonePoint,
    read_touchstone,
    read_touchstone_file,
    write_touchstone,
)


def _identity_points(freqs: list[float]) -> list[TouchstonePoint]:
    return [
        TouchstonePoint(freq_ghz=f, matrix=np.eye(2, dtype=complex)) for f in freqs
    ]


def test_round_trip_ma() -> None:
    pts = _identity_points([1.0, 2.0, 5.0])
    text = write_touchstone(pts, fmt="MA")
    parsed = read_touchstone(text)
    assert isinstance(parsed, TouchstoneFile)
    assert parsed.n_ports == 2
    assert parsed.param == "S"
    assert parsed.z0_ohm == 50.0
    assert len(parsed.points) == 3
    for p in parsed.points:
        np.testing.assert_allclose(p.matrix, np.eye(2), atol=1e-9)


def test_round_trip_ri() -> None:
    S = np.array([[0.1 + 0.2j, 0.5j], [0.5j, 0.1 - 0.2j]])
    pts = [TouchstonePoint(freq_ghz=2.0, matrix=S)]
    text = write_touchstone(pts, fmt="RI")
    parsed = read_touchstone(text)
    np.testing.assert_allclose(parsed.points[0].matrix, S, atol=1e-9)


def test_round_trip_db() -> None:
    S = np.array([[0.5 + 0.5j, 0.2 + 0.1j], [0.2 + 0.1j, 0.5 + 0.5j]])
    pts = [TouchstonePoint(freq_ghz=2.0, matrix=S)]
    text = write_touchstone(pts, fmt="DB")
    parsed = read_touchstone(text)
    # DB conversion has more rounding; tolerance loosened
    np.testing.assert_allclose(parsed.points[0].matrix, S, atol=1e-6)


def test_freq_unit_round_trip_mhz() -> None:
    pts = _identity_points([1.0])
    text = write_touchstone(pts, fmt="RI", freq_unit="MHz")
    parsed = read_touchstone(text)
    assert parsed.points[0].freq_ghz == pytest.approx(1.0, rel=1e-9)


def test_three_port_round_trip() -> None:
    M = np.array(
        [
            [0.1, 0.2j, 0.3 + 0.1j],
            [0.2j, 0.4, 0.5j],
            [0.3 + 0.1j, 0.5j, 0.1],
        ]
    )
    pts = [TouchstonePoint(freq_ghz=1.0, matrix=M)]
    text = write_touchstone(pts, fmt="RI")
    parsed = read_touchstone(text)
    assert parsed.n_ports == 3
    np.testing.assert_allclose(parsed.points[0].matrix, M, atol=1e-9)


def test_read_with_comments_and_blanks() -> None:
    text = """\
! This is a comment
! Another comment

# GHz S RI R 50

1.0 0.1 0.2 0.3 0.4 0.3 0.4 0.1 0.2
2.0 0.2 0.3 0.4 0.5 0.4 0.5 0.2 0.3
"""
    parsed = read_touchstone(text)
    assert len(parsed.points) == 2


def test_read_file(tmp_path: Path) -> None:
    text = "# GHz S MA R 50\n1.0 1.0 0 1.0 0 1.0 0 1.0 0\n"
    f = tmp_path / "x.s2p"
    f.write_text(text)
    parsed = read_touchstone_file(f)
    assert parsed.n_ports == 2


def test_read_rejects_bad_row_width() -> None:
    text = "# GHz S MA R 50\n1.0 0.1 0.2 0.3\n"  # missing entries
    with pytest.raises(ValueError):
        read_touchstone(text)


def test_read_rejects_empty_data() -> None:
    text = "# GHz S MA R 50\n"
    with pytest.raises(ValueError):
        read_touchstone(text)


def test_read_handles_non_50_z0() -> None:
    text = "# GHz S RI R 75\n1.0 0.1 0 0 0 0 0 0.1 0\n"
    parsed = read_touchstone(text)
    assert parsed.z0_ohm == 75.0
