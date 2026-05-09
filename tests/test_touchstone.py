"""Tests for the Touchstone v1 writer."""

from pathlib import Path

import numpy as np
import pytest

from reasitic.network import (
    TouchstonePoint,
    write_touchstone,
    write_touchstone_file,
)


def _identity_points(freqs: list[float]) -> list[TouchstonePoint]:
    return [
        TouchstonePoint(freq_ghz=f, matrix=np.eye(2, dtype=complex)) for f in freqs
    ]


def test_writes_option_line() -> None:
    out = write_touchstone(_identity_points([1.0]))
    assert out.startswith("# GHz S MA R 50\n")


def test_default_format_ma() -> None:
    out = write_touchstone(_identity_points([1.0, 2.0]))
    lines = out.strip().splitlines()
    assert len(lines) == 3  # option + 2 freq points
    # row format: f s11_mag s11_ang s21_mag s21_ang s12_mag s12_ang s22_mag s22_ang
    cells = lines[1].split()
    assert len(cells) == 9
    assert cells[0] == "1"  # 1 GHz
    # S11 mag = 1, ang = 0 (identity)
    assert float(cells[1]) == pytest.approx(1.0)
    assert float(cells[2]) == pytest.approx(0.0)


def test_ri_format_round_trip() -> None:
    S = np.array([[0.1 + 0.2j, 0.5j], [0.5j, 0.1 - 0.2j]])
    p = TouchstonePoint(freq_ghz=2.0, matrix=S)
    out = write_touchstone([p], fmt="RI")
    cells = out.strip().splitlines()[-1].split()
    # 1 freq + 4 entries × 2 scalars = 9 cells
    assert len(cells) == 9
    f = float(cells[0])
    s11_re, s11_im = float(cells[1]), float(cells[2])
    s21_re, s21_im = float(cells[3]), float(cells[4])
    assert f == pytest.approx(2.0)
    assert complex(s11_re, s11_im) == pytest.approx(S[0, 0])
    assert complex(s21_re, s21_im) == pytest.approx(S[1, 0])


def test_freq_unit_scaling() -> None:
    out = write_touchstone(_identity_points([1.0]), freq_unit="MHz")
    # 1 GHz = 1000 MHz
    line = out.strip().splitlines()[1]
    assert line.split()[0] == "1000"


def test_db_format_unit_magnitude() -> None:
    p = TouchstonePoint(freq_ghz=1.0, matrix=np.eye(2, dtype=complex))
    out = write_touchstone([p], fmt="DB")
    cells = out.strip().splitlines()[-1].split()
    # Identity → 20·log10(1) = 0 dB
    assert float(cells[1]) == pytest.approx(0.0)


def test_three_port_row_major() -> None:
    """For higher-port files entries are row-major i1 i2 ... iN."""
    M = np.arange(9).reshape(3, 3) + 1j * np.arange(9).reshape(3, 3)
    p = TouchstonePoint(freq_ghz=1.0, matrix=M)
    out = write_touchstone([p], fmt="RI")
    cells = out.strip().splitlines()[-1].split()
    # 1 freq + 9 entries × 2 scalars = 19
    assert len(cells) == 19
    # First entry should be M[0,0] = 0+0j
    assert float(cells[1]) == pytest.approx(0.0)
    # Second entry should be M[0,1] = 1+1j
    assert float(cells[3]) == pytest.approx(1.0)


def test_two_port_uses_11_21_12_22_order() -> None:
    """Touchstone v1 quirk: 2-port files write S11, S21, S12, S22."""
    S = np.array([[1, 2], [3, 4]], dtype=complex)
    p = TouchstonePoint(freq_ghz=1.0, matrix=S)
    out = write_touchstone([p], fmt="RI")
    cells = out.strip().splitlines()[-1].split()
    # f, 11_re, 11_im, 21_re, 21_im, 12_re, 12_im, 22_re, 22_im
    assert float(cells[1]) == 1.0  # S11
    assert float(cells[3]) == 3.0  # S21
    assert float(cells[5]) == 2.0  # S12
    assert float(cells[7]) == 4.0  # S22


def test_writes_file(tmp_path: Path) -> None:
    out_path = tmp_path / "spiral.s2p"
    write_touchstone_file(out_path, _identity_points([1.0, 2.0, 3.0]))
    text = out_path.read_text()
    assert text.startswith("# GHz S MA R 50\n")
    assert text.count("\n") == 4  # option + 3 freq points + trailing


def test_rejects_empty_sweep() -> None:
    with pytest.raises(ValueError):
        write_touchstone([])


def test_rejects_inconsistent_shapes() -> None:
    pts = [
        TouchstonePoint(freq_ghz=1.0, matrix=np.eye(2, dtype=complex)),
        TouchstonePoint(freq_ghz=2.0, matrix=np.eye(3, dtype=complex)),
    ]
    with pytest.raises(ValueError):
        write_touchstone(pts)
