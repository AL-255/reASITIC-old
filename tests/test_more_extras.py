"""Tests for Mohan formula, Sonnet round-trip, Y de-embedding."""

from pathlib import Path

import numpy as np
import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
)
from reasitic.exports import (
    read_sonnet,
    read_sonnet_file,
    write_sonnet,
    write_sonnet_file,
)
from reasitic.inductance import mohan_modified_wheeler
from reasitic.network import (
    deembed_pad_open,
    deembed_pad_open_short,
    spiral_y_at_freq,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Mohan modified-Wheeler -----------------------------------------------


def test_mohan_square_known_value() -> None:
    """Mohan 1999 example: d_out = 200 μm, d_in = 100 μm, n = 5,
    K1 = 2.34, K2 = 2.75 → L_mw ≈ 5.75 nH (computed directly from
    the formula).
    """
    L = mohan_modified_wheeler(
        n_turns=5, d_outer_um=200, d_inner_um=100, shape="square"
    )
    assert pytest.approx(5.75, rel=0.05) == L


def test_mohan_octagonal_lower_K() -> None:
    """Octagonal has K1 = 2.25 < 2.34 → slightly lower L for same
    geometry."""
    L_sq = mohan_modified_wheeler(
        n_turns=3, d_outer_um=200, d_inner_um=100, shape="square"
    )
    L_oc = mohan_modified_wheeler(
        n_turns=3, d_outer_um=200, d_inner_um=100, shape="octagonal"
    )
    assert L_oc < L_sq


def test_mohan_zero_for_collapsed_geometry() -> None:
    """Both d_outer ≤ d_inner cases collapse to L=0 (degenerate)."""
    assert mohan_modified_wheeler(
        n_turns=5, d_outer_um=100, d_inner_um=100, shape="square"
    ) == 0.0
    assert mohan_modified_wheeler(
        n_turns=5, d_outer_um=50, d_inner_um=100, shape="square"
    ) == 0.0


def test_mohan_rejects_unknown_shape() -> None:
    with pytest.raises(ValueError):
        mohan_modified_wheeler(
            n_turns=3, d_outer_um=200, d_inner_um=100, shape="triangle"
        )


def test_mohan_scales_quadratically_with_n() -> None:
    L1 = mohan_modified_wheeler(
        n_turns=2, d_outer_um=200, d_inner_um=100, shape="square"
    )
    L2 = mohan_modified_wheeler(
        n_turns=4, d_outer_um=200, d_inner_um=100, shape="square"
    )
    assert pytest.approx(4.0, rel=1e-9) == L2 / L1


# Sonnet round-trip -----------------------------------------------------


def test_sonnet_round_trip(tech) -> None:
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=2,
        tech=tech, metal="m3",
    )
    text = write_sonnet([sp], tech)
    shapes = read_sonnet(text, tech)
    assert len(shapes) == 1
    # Two turns → 2 polygons, each with 5 vertices (closed square)
    assert len(shapes[0].polygons) == 2


def test_sonnet_layer_resolution(tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    text = write_sonnet([sp], tech)
    shapes = read_sonnet(text, tech)
    m3_idx = tech.metal_by_name("m3").index
    assert shapes[0].polygons[0].metal == m3_idx


def test_sonnet_file_round_trip(tmp_path: Path, tech) -> None:
    sp = square_spiral(
        "S", length=100, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    out = tmp_path / "S.son"
    write_sonnet_file(out, [sp], tech)
    shapes = read_sonnet_file(out, tech)
    assert len(shapes[0].polygons) == 1


# Y-parameter de-embedding ----------------------------------------------


def test_deembed_open_subtracts(tech) -> None:
    """Y_DUT = Y_meas − Y_open."""
    Y_meas = np.array([[0.005 + 0.01j, -0.001j], [-0.001j, 0.005 + 0.01j]])
    Y_open = np.array([[0.001 + 0.005j, 0.0j], [0.0j, 0.001 + 0.005j]])
    Y_dut = deembed_pad_open(Y_meas, Y_open)
    np.testing.assert_allclose(Y_dut, Y_meas - Y_open, atol=1e-12)


def test_deembed_open_rejects_non_2x2() -> None:
    Y_meas = np.eye(3, dtype=complex)
    Y_open = np.eye(3, dtype=complex)
    with pytest.raises(ValueError):
        deembed_pad_open(Y_meas, Y_open)


def test_deembed_open_short_smoke(tech) -> None:
    """Smoke test that the open-short formula returns finite values."""
    Y_meas = np.array([[0.01 + 0.005j, -0.005j], [-0.005j, 0.01 + 0.005j]])
    Y_open = np.array([[0.002 + 0.001j, 0.0j], [0.0j, 0.002 + 0.001j]])
    Y_short = np.array([[0.05 + 0.001j, -0.04j], [-0.04j, 0.05 + 0.001j]])
    Y_dut = deembed_pad_open_short(Y_meas, Y_open, Y_short)
    assert Y_dut.shape == (2, 2)
    assert np.all(np.isfinite(Y_dut))


def test_deembed_open_short_recovers_simple_case(tech) -> None:
    """If Y_meas - Y_open == Y_short - Y_open then de-embedded should
    map to (1/Y_short_open - 1/Y_short_open)^{-1} → singular. Verify
    we don't crash with a small-magnitude difference instead."""
    Y_meas = np.array([[0.01j, 0j], [0j, 0.01j]])
    Y_open = np.array([[0.001j, 0j], [0j, 0.001j]])
    Y_short = np.array([[0.005j, 0j], [0j, 0.005j]])
    Y_dut = deembed_pad_open_short(Y_meas, Y_open, Y_short)
    assert Y_dut.shape == (2, 2)


def test_deembed_with_real_spiral(tech) -> None:
    """The de-embedded Y should equal Y_meas - Y_open exactly."""
    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    pad = square_spiral(
        "PAD", length=50, width=10, spacing=2, turns=1,
        tech=tech, metal="m3",
    )
    Y_meas = spiral_y_at_freq(sp, tech, freq_ghz=2.4)
    Y_open = spiral_y_at_freq(pad, tech, freq_ghz=2.4)
    Y_dut = deembed_pad_open(Y_meas, Y_open)
    # Algebraic identity
    np.testing.assert_allclose(Y_dut, Y_meas - Y_open, atol=1e-12)