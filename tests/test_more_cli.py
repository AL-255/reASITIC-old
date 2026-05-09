"""Tests for additional CLI commands: builders, edit, tech-modify, view."""

from pathlib import Path

import pytest

from reasitic.cli import Repl

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def repl():
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    return r


# Builder commands ------------------------------------------------------


def test_trans_command(repl) -> None:
    assert repl.execute(
        "TRANS NAME=T:LEN=200:W=10:S=2:N=2:METAL=m3:METAL2=m2"
    )
    assert "T" in repl.shapes


def test_balun_command(repl) -> None:
    assert repl.execute(
        "BALUN NAME=B:LEN=200:W=10:S=2:N=2:METAL=m3:METAL2=m2"
    )
    assert "B" in repl.shapes


def test_capacitor_command(repl) -> None:
    assert repl.execute(
        "CAPACITOR NAME=C:LEN=20:WID=20:METAL1=m3:METAL2=m2"
    )
    assert "C" in repl.shapes


def test_symsq_command(repl) -> None:
    assert repl.execute(
        "SYMSQ NAME=S:LEN=200:W=10:S=2:N=3:METAL=m3"
    )
    assert "S" in repl.shapes


# Shape edit -----------------------------------------------------------


def test_phase_command(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    assert repl.execute("PHASE A 1")
    assert repl.shapes["A"].orientation == 1
    repl.execute("PHASE A -1")
    assert repl.shapes["A"].orientation == -1


def test_split_command(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=4:METAL=m3")
    n_polys = len(repl.shapes["A"].polygons)
    assert n_polys >= 2
    repl.execute(f"SPLIT A {n_polys // 2} A_tail")
    assert "A" in repl.shapes
    assert "A_tail" in repl.shapes
    assert (
        len(repl.shapes["A"].polygons) + len(repl.shapes["A_tail"].polygons)
        == n_polys
    )


def test_join_command(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.execute("SQ NAME=B:LEN=100:W=10:S=2:N=2:METAL=m3:XORG=200")
    n_a = len(repl.shapes["A"].polygons)
    n_b = len(repl.shapes["B"].polygons)
    repl.execute("JOIN A B")
    assert "B" not in repl.shapes
    assert len(repl.shapes["A"].polygons) == n_a + n_b


# Tech edits -----------------------------------------------------------


def test_modify_tech_layer_rho(repl) -> None:
    initial = repl.tech.layers[0].rho
    repl.execute("MODIFYTECHLAYER rho 0 5.0")
    assert repl.tech.layers[0].rho == 5.0
    assert repl.tech.layers[0].rho != initial


def test_modify_tech_layer_t(repl) -> None:
    repl.execute("MODIFYTECHLAYER t 0 1234")
    assert repl.tech.layers[0].t == 1234.0


def test_modify_tech_layer_eps(repl) -> None:
    repl.execute("MODIFYTECHLAYER eps 0 9.5")
    assert repl.tech.layers[0].eps == 9.5


def test_chip_command(repl) -> None:
    repl.execute("CHIP 1024 768")
    assert repl.tech.chip.chipx == 1024
    assert repl.tech.chip.chipy == 768


def test_eddy_toggle(repl) -> None:
    repl.execute("EDDY off")
    assert repl.tech.chip.eddy is False
    repl.execute("EDDY on")
    assert repl.tech.chip.eddy is True


# Cell / AutoCell ------------------------------------------------------


def test_cell_command(repl) -> None:
    repl.execute("CELL 100 50 5")
    assert repl.cell_constraints == {"max_l": 100.0, "max_w": 50.0, "max_t": 5.0}


def test_autocell_command(repl) -> None:
    repl.execute("AUTOCELL 0.25 1.5")
    assert repl.auto_cell_alpha == 0.25
    assert repl.auto_cell_beta == 1.5


# View no-ops accept silently ------------------------------------------


def test_view_commands_are_noops(repl) -> None:
    for cmd in ("SCALE 2", "PAN 10 10", "BB", "REFRESH", "GRID 5",
                "ORIGIN 0 0", "VPC", "OPENGL on"):
        assert repl.execute(cmd) is True


# Pause / Input --------------------------------------------------------


def test_pause_command_doesnt_block(repl) -> None:
    assert repl.execute("PAUSE") is True


# Error recovery -------------------------------------------------------


def test_unknown_command_doesnt_kill_session(repl, capsys) -> None:
    repl.execute("ZZZNONEXISTENT foo bar")
    out = capsys.readouterr().out
    assert "Unknown" in out
    # Subsequent command still works
    assert repl.execute("LIST") is True


def test_bad_args_doesnt_kill_session(repl, capsys) -> None:
    repl.execute("IND nonexistent_shape")
    captured = capsys.readouterr().out
    assert "Error" in captured or "shape" in captured.lower()
    assert repl.execute("LIST") is True


def test_log_writes_lines(repl, tmp_path: Path) -> None:
    log = tmp_path / "session.log"
    repl.cmd_log(str(log))
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.execute("LIST")
    repl.cmd_log()  # stop logging
    text = log.read_text()
    # Expect both commands recorded
    assert "SQ" in text
    assert "LIST" in text


# Recording ------------------------------------------------------------


def test_record_captures_lines(repl) -> None:
    repl.cmd_record()
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.execute("IND A")
    assert repl.macro is not None
    assert any("SQ" in cmd for cmd in repl.macro)
    assert any("IND" in cmd for cmd in repl.macro)
