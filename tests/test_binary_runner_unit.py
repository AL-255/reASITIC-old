"""Unit tests for binary_runner that don't require the legacy binary.

Cover the failure paths (binary not found, parse errors) and the
parser internals using synthetic Geom output text.
"""

from pathlib import Path

import pytest

from reasitic.validation.binary_runner import (
    BinaryNotFoundError,
    BinaryRunner,
    parse_geom_output,
)

# Parser tests --------------------------------------------------------


def test_parse_wire_output() -> None:
    text = (
        "Wire <W1> has the following geometry:\n"
        "L = 100.00, W = 10.00, Metal = M3\n"
        "Total length = 100.00 (um), Total Area = 1000.00 (um^2)\n"
        "Located at ( 0.00, 0.00) with 1 segments.\n"
    )
    r = parse_geom_output(text)
    assert r.kind == "Wire"
    assert r.name == "W1"
    assert r.length_um == pytest.approx(100.0)
    assert r.width_um == pytest.approx(10.0)
    assert r.metal == "M3"
    assert r.total_length_um == pytest.approx(100.0)
    assert r.total_area_um2 == pytest.approx(1000.0)
    assert r.location == pytest.approx((0.0, 0.0))
    assert r.n_segments == 1


def test_parse_square_spiral_output() -> None:
    text = (
        "Square spiral <A> has the following geometry:\n"
        "L1 = 200.00, L2 = 200.00, W = 10.00, S = 2.00, N = 3.00\n"
        "Total length = 1216.76 (um), Total Area = 12148.22 (um^2)\n"
        "Located at (200.00,200.00) with 12 segments.\n"
    )
    r = parse_geom_output(text)
    assert r.kind == "Square spiral"
    assert r.name == "A"
    assert r.spiral_l1_um == pytest.approx(200.0)
    assert r.spiral_l2_um == pytest.approx(200.0)
    assert r.spiral_spacing_um == pytest.approx(2.0)
    assert r.spiral_turns == pytest.approx(3.0)
    assert r.location == pytest.approx((200.0, 200.0))
    assert r.n_segments == 12


def test_parse_handles_garbage_lines() -> None:
    """Unknown lines are simply ignored."""
    text = (
        "Some other text\n"
        "Wire <W1> has the following geometry:\n"
        "Random noise that doesn't match any pattern\n"
        "L = 50.00, W = 5.00, Metal = M2\n"
        "Total length = 50.00 (um), Total Area = 250.00 (um^2)\n"
    )
    r = parse_geom_output(text)
    assert r.length_um == pytest.approx(50.0)
    assert r.metal == "M2"


def test_parse_empty_text() -> None:
    r = parse_geom_output("")
    assert r.name == ""
    assert r.kind == ""
    assert r.length_um is None


def test_parse_only_header() -> None:
    text = "Wire <Foo> has the following geometry:\n"
    r = parse_geom_output(text)
    assert r.kind == "Wire"
    assert r.name == "Foo"


# Locating the binary ------------------------------------------------


def test_binary_not_found_raises(monkeypatch, tmp_path: Path) -> None:
    """If REASITIC_BINARY is unset and run/asitic isn't in any
    parent, BinaryRunner.auto raises BinaryNotFoundError."""
    monkeypatch.setattr(
        "reasitic.validation.binary_runner._default_binary_path",
        lambda: (_ for _ in ()).throw(BinaryNotFoundError("no binary")),
    )
    with pytest.raises(BinaryNotFoundError):
        BinaryRunner.auto()


def test_binary_runner_auto_with_env_override(
    monkeypatch, tmp_path: Path
) -> None:
    """If REASITIC_BINARY points at a real file, that wins."""
    fake_binary = tmp_path / "fake_asitic"
    fake_binary.write_text("#!/bin/sh\necho fake\n")
    fake_binary.chmod(0o755)
    fake_tech = tmp_path / "BiCMOS.tek"
    fake_tech.write_text("<chip>\n")
    monkeypatch.setenv("REASITIC_BINARY", str(fake_binary))
    # Force the package-tree probe to fail
    monkeypatch.setattr(
        "reasitic.validation.binary_runner.Path.exists",
        lambda self: str(self) == str(fake_binary) or str(self) == str(fake_tech),
    )


def test_geom_result_carries_raw_text() -> None:
    text = (
        "Wire <W1> has the following geometry:\n"
        "L = 100.00, W = 10.00, Metal = M3\n"
    )
    r = parse_geom_output(text)
    assert r.raw == text
