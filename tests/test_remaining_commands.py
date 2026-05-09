"""Tests for the remaining REPL aliases that complete binary parity."""

from pathlib import Path

import pytest

from reasitic.cli import Repl
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def repl():
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("SQ NAME=A:LEN=200:W=10:S=2:N=3:METAL=m3")
    r.execute("SQ NAME=B:LEN=200:W=10:S=2:N=3:METAL=m3:XORG=300")
    return r


# Move-axis variants ---------------------------------------------------


def test_movex(repl) -> None:
    xmin0, _, _, _ = repl.shapes["A"].bounding_box()
    repl.execute("MOVEX A 50")
    xmin1, _, _, _ = repl.shapes["A"].bounding_box()
    assert xmin1 - xmin0 == pytest.approx(50.0)


def test_movey(repl) -> None:
    _, ymin0, _, _ = repl.shapes["A"].bounding_box()
    repl.execute("MOVEY A 30")
    _, ymin1, _, _ = repl.shapes["A"].bounding_box()
    assert ymin1 - ymin0 == pytest.approx(30.0)


# Flip / Reverse -------------------------------------------------------


def test_flip_reverses_polygon_order(repl) -> None:
    polys_before = [list(p.vertices) for p in repl.shapes["A"].polygons]
    repl.execute("FLIP A")
    polys_after = repl.shapes["A"].polygons
    # Reversed order
    assert len(polys_after) == len(polys_before)
    # First polygon's first vertex now matches the last polygon's last
    # vertex from before
    assert polys_after[0].vertices[0] == polys_before[-1][-1]


# Join with shunt -----------------------------------------------------


def test_joinshunt_creates_friendship(repl) -> None:
    repl.execute("JOINSHUNT A B")
    assert frozenset({"A", "B"}) in repl.friendships


# Select / Unselect ---------------------------------------------------


def test_select_unselect(repl) -> None:
    repl.execute("SELECT A")
    assert repl.selected_shape == "A"
    repl.execute("UNSELECT")
    assert repl.selected_shape is None


# SpToWire ------------------------------------------------------------


def test_sptowire_breaks_into_n_wires(repl) -> None:
    n_polys = len(repl.shapes["A"].polygons)
    repl.execute("SPTOWIRE A")
    # Original A is gone; A_0..A_{n-1} now exist
    assert "A" not in repl.shapes
    for i in range(n_polys):
        assert f"A_{i}" in repl.shapes


# Pi2 / 2PortX --------------------------------------------------------


def test_pi2_works(repl) -> None:
    assert repl.execute("PI2 A 2.4")


def test_2port_x(repl) -> None:
    assert repl.execute("2PORTX A 1.0 5.0 1.0")


# RESISHF -------------------------------------------------------------


def test_resishf(repl) -> None:
    assert repl.execute("RESISHF A 2.4")


# CCELL / SETMAXNW ----------------------------------------------------


def test_ccell(repl) -> None:
    repl.execute("CCELL 100 50")
    assert repl.cell_constraints["max_l"] == 100.0
    assert repl.cell_constraints["max_w"] == 50.0


def test_setmaxnw(repl) -> None:
    repl.execute("SETMAXNW 16")
    assert repl.max_nw == 16


# SWEEPMM (alias for SWEEP) ------------------------------------------


def test_sweepmm_alias(repl) -> None:
    assert repl.execute(
        "SWEEPMM LMIN=100:LMAX=150:LSTEP=50:WMIN=8:WMAX=12:WSTEP=4"
        ":SMIN=2:SMAX=2:SSTEP=1:NMIN=2:NMAX=2:NSTEP=1:FREQ=2.4:METAL=m3"
    )


# BCAT alias ---------------------------------------------------------


def test_bcat_alias(repl, tmp_path: Path, capsys) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hello bcat\n")
    repl.execute(f"BCAT {f}")
    out = capsys.readouterr().out
    assert "hello bcat" in out