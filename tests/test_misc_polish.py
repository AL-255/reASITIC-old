"""Tests for viewport state, load_viewport, and python -m reasitic help."""

from pathlib import Path

import pytest

from reasitic import parse_tech_file, square_spiral
from reasitic.cli import Repl
from reasitic.persistence import load_session, load_viewport, save_session
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Viewport state ------------------------------------------------------


def test_scale_command_records_state() -> None:
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("SCALE 2.5")
    assert r.viewport["scale"] == 2.5


def test_pan_command_records_state() -> None:
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("PAN 10 20")
    assert r.viewport["pan_x"] == 10.0
    assert r.viewport["pan_y"] == 20.0


def test_origin_command_records_state() -> None:
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("ORIGIN 100 200")
    assert r.viewport["origin_x"] == 100.0
    assert r.viewport["origin_y"] == 200.0


def test_grid_and_snap() -> None:
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("GRID 5")
    r.execute("SNAP 1")
    assert r.viewport["grid"] == 5.0
    assert r.viewport["snap"] == 1.0


# Save/Load round-trips viewport --------------------------------------


def test_save_load_round_trips_viewport(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal="m3",
    )
    viewport = {"scale": 2.5, "pan_x": 10.0, "pan_y": 20.0,
                "origin_x": 0.0, "origin_y": 0.0,
                "grid": 5.0, "snap": 1.0}
    out = tmp_path / "session.json"
    save_session(out, tech=tech, shapes={"S": sp}, viewport=viewport)
    # load_session is unchanged
    tech2, shapes2 = load_session(out)
    assert tech2 is not None
    assert "S" in shapes2
    # load_viewport is the new helper
    vp = load_viewport(out)
    assert vp == viewport


def test_load_viewport_returns_empty_for_old_files(tmp_path: Path, tech) -> None:
    """Sessions saved without viewport should yield {}."""
    out = tmp_path / "old.json"
    save_session(out, tech=tech)
    vp = load_viewport(out)
    assert vp == {}


def test_repl_save_load_round_trip(tmp_path: Path, tech) -> None:
    """End-to-end: REPL SAVE/LOAD preserves shapes and viewport."""
    r1 = Repl()
    r1.cmd_load_tech(str(_BICMOS))
    r1.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    r1.execute("SCALE 3")
    r1.execute("PAN 1 2")
    out = tmp_path / "session.json"
    r1.cmd_save(str(out))
    # Fresh REPL loads everything back
    r2 = Repl()
    r2.cmd_load_tech(str(_BICMOS))
    r2.cmd_load(str(out))
    assert "A" in r2.shapes
    assert r2.viewport["scale"] == 3.0
    assert r2.viewport["pan_x"] == 1.0


# python -m reasitic help -----------------------------------------------


def test_python_m_reasitic_help_prints_docstring(capsys) -> None:
    from reasitic.__main__ import main

    rc = main(["help", "compute_self_inductance"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "compute_self_inductance" in out
    assert "Greenhouse" in out or "Manhattan" in out or "polygon" in out.lower()


def test_python_m_reasitic_help_handles_unknown(capsys) -> None:
    from reasitic.__main__ import main

    rc = main(["help", "ZzzNonExistent"])
    assert rc == 1
    out = capsys.readouterr().out
    assert "No public symbol" in out


def test_python_m_reasitic_help_resolves_module_path(capsys) -> None:
    from reasitic.__main__ import main

    rc = main(["help", "reasitic.network.spiral_y_at_freq"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "spiral_y_at_freq" in out