"""Tests for the CLI command set: shape mgmt, toggles, help, scripts."""

from pathlib import Path

import pytest

from reasitic.cli import Repl
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def repl():
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    return r


def test_help_lists_categories(repl, capsys) -> None:
    repl.cmd_help()
    out = capsys.readouterr().out
    assert "Categories" in out or "Create" in out


def test_help_for_command(repl, capsys) -> None:
    repl.cmd_help("IND")
    out = capsys.readouterr().out
    assert "Self-inductance" in out


def test_help_unknown_command(repl, capsys) -> None:
    repl.cmd_help("ZZZ_NONEXISTENT")
    out = capsys.readouterr().out
    assert "No help" in out


def test_version(repl, capsys) -> None:
    repl.cmd_version()
    out = capsys.readouterr().out
    assert "reASITIC" in out


def test_verbose_toggle(repl, capsys) -> None:
    assert repl.verbose is False
    repl.cmd_verbose()
    assert repl.verbose is True
    repl.cmd_verbose("off")
    assert repl.verbose is False


def test_timer_toggle(repl) -> None:
    repl.cmd_timer("on")
    assert repl.timer is True
    repl.cmd_timer("off")
    assert repl.timer is False


def test_savemat_toggle(repl) -> None:
    repl.cmd_savemat("true")
    assert repl.save_mat is True


def test_log_start_stop(repl, tmp_path: Path) -> None:
    log = tmp_path / "session.log"
    repl.cmd_log(str(log))
    assert repl.log_path == log
    assert log.exists()
    repl.cmd_log()
    assert repl.log_path is None


def test_record_writes_macro(repl, tmp_path: Path, capsys) -> None:
    repl.cmd_record()
    assert repl.macro == []
    repl.macro = ["SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3"]
    out = tmp_path / "macro.txt"
    repl.cmd_record(str(out))
    assert "SQ" in out.read_text()


def test_cat_prints_file(repl, tmp_path: Path, capsys) -> None:
    f = tmp_path / "x.txt"
    f.write_text("hello world\n")
    repl.cmd_cat(str(f))
    captured = capsys.readouterr().out
    assert "hello world" in captured


def test_erase_removes_shape(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    assert "A" in repl.shapes
    repl.cmd_erase(["A"])
    assert "A" not in repl.shapes


def test_rename(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.cmd_rename("A", "B")
    assert "B" in repl.shapes
    assert "A" not in repl.shapes
    assert repl.shapes["B"].name == "B"


def test_rename_refuses_existing_target(repl, capsys) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.execute("SQ NAME=B:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.cmd_rename("A", "B")
    assert "A" in repl.shapes
    assert "B" in repl.shapes
    out = capsys.readouterr().out
    assert "already exists" in out


def test_copy(repl) -> None:
    repl.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    repl.cmd_copy("A", "A_copy")
    assert "A_copy" in repl.shapes
    assert repl.shapes["A_copy"].name == "A_copy"
    # Independent copy
    assert repl.shapes["A_copy"].polygons is not repl.shapes["A"].polygons


def test_exec_script_runs_lines(repl, tmp_path: Path) -> None:
    script = tmp_path / "test.exec"
    script.write_text(
        "# comment\n"
        "SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3\n"
        "SQ NAME=B:LEN=200:W=10:S=2:N=2:METAL=m3\n"
    )
    repl.cmd_exec_script(str(script))
    assert "A" in repl.shapes
    assert "B" in repl.shapes


def test_dispatch_help_command(repl, capsys) -> None:
    repl.execute("HELP")
    out = capsys.readouterr().out
    assert "Categories" in out


def test_dispatch_version_command(repl, capsys) -> None:
    repl.execute("VERSION")
    out = capsys.readouterr().out
    assert "reASITIC" in out


def test_dispatch_quit_returns_false(repl) -> None:
    assert repl.execute("QUIT") is False
    assert repl.execute("EXIT") is False