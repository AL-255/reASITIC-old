"""Tests for OptPoly / OptArea / OptSymSq / BatchOpt / Eddy / SPICE / 3DTrans."""

import math
from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    transformer_3d,
)
from reasitic.exports import write_spice_subckt
from reasitic.inductance.eddy import eddy_correction, solve_inductance_with_eddy
from reasitic.optimise import (
    batch_opt_square,
    optimise_area_square_spiral,
    optimise_polygon_spiral,
    optimise_symmetric_square,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# OptPoly / OptArea / OptSymSq -----------------------------------------


def test_optpoly_meets_l_target(tech) -> None:
    res = optimise_polygon_spiral(
        tech, target_L_nH=1.0, freq_ghz=2.0, sides=8, metal="m3"
    )
    assert res.L_nH == pytest.approx(1.0, rel=0.10)


def test_optarea_smaller_footprint_than_q_opt(tech) -> None:
    """At a fixed L target, optimising for area should yield a
    spiral whose length is no larger than the Q-optimised one."""
    from reasitic.optimise import optimise_square_spiral

    target_L = 2.0
    f = 2.0
    q_res = optimise_square_spiral(tech, target_L_nH=target_L, freq_ghz=f, metal="m3")
    a_res = optimise_area_square_spiral(
        tech, target_L_nH=target_L, freq_ghz=f, metal="m3"
    )
    # Area-optimised should have smaller or equal length
    assert a_res.length_um <= q_res.length_um + 1.0


def test_optsymsq_returns_valid(tech) -> None:
    res = optimise_symmetric_square(
        tech, target_L_nH=1.0, freq_ghz=2.0, metal="m3"
    )
    assert res.L_nH > 0
    assert res.Q > 0


# BatchOpt --------------------------------------------------------------


def test_batch_opt_returns_one_row_per_target(tech) -> None:
    targets = [(1.0, 1.0), (2.0, 2.0), (5.0, 5.0)]
    arr = batch_opt_square(tech, targets=targets, metal="m3")
    assert len(arr) == 3
    assert "L_nH" in arr.dtype.names
    assert "Q" in arr.dtype.names
    assert "success" in arr.dtype.names


def test_batch_opt_dimensions_increase_with_target(tech) -> None:
    targets = [(0.5, 2.0), (5.0, 2.0)]
    arr = batch_opt_square(tech, targets=targets, metal="m3")
    # Higher L typically needs more turns or larger footprint
    assert arr["L_nH"][0] < arr["L_nH"][1]


# Eddy currents ---------------------------------------------------------


def test_eddy_correction_zero_at_dc(tech) -> None:
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    dL, dR = eddy_correction(sp, tech, freq_ghz=0.0)
    assert dL == 0.0
    assert dR == 0.0


def test_eddy_correction_finite_at_freq(tech) -> None:
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    dL, dR = eddy_correction(sp, tech, freq_ghz=2.0)
    assert math.isfinite(dL)
    assert math.isfinite(dR)


def test_solve_with_eddy_returns_finite(tech) -> None:
    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    L, R = solve_inductance_with_eddy(sp, tech, freq_ghz=2.0)
    assert math.isfinite(L)
    assert math.isfinite(R)
    assert L > 0
    assert R > 0


# 3DTrans ----------------------------------------------------------------


def test_3dtrans_two_metals_plus_via(tech) -> None:
    t = transformer_3d(
        "T1",
        length=100, width=10, spacing=2, turns=2,
        tech=tech, metal_top="m3", metal_bottom="m2",
    )
    metals = {p.metal for p in t.polygons}
    # 2 metals + 1 via metal-index → 3 distinct metal indices
    assert len(metals) == 3


def test_3dtrans_co_axial_footprint(tech) -> None:
    """The 3D trans should have its outer x-extent equal to
    ``length`` regardless of metal_top vs metal_bottom (no
    horizontal offset like the planar trans)."""
    t = transformer_3d(
        "T", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal_top="m3", metal_bottom="m2",
    )
    xmin, _, xmax, _ = t.bounding_box()
    assert xmax - xmin == pytest.approx(100.0, abs=1.0)


# SPICE export -----------------------------------------------------------


def test_spice_subckt_format(tech) -> None:
    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    text = write_spice_subckt(sp, tech, freq_ghz=2.0)
    assert ".subckt L1_pi p1 p2 gnd" in text
    assert "Lseries" in text
    assert "Rseries" in text
    assert "Cp1" in text
    assert "Cp2" in text
    assert text.rstrip().endswith(".ends")


def test_spice_subckt_writes_to_file(tmp_path: Path, tech) -> None:
    from reasitic.exports import write_spice_subckt_file

    sp = square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    out = tmp_path / "L1.sub"
    write_spice_subckt_file(out, sp, tech, freq_ghz=2.0)
    assert ".subckt L1_pi" in out.read_text()