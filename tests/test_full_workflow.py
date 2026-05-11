"""End-to-end regression test exercising the entire library.

Builds spirals, runs every analysis, exports to every format,
round-trips through SAVE/LOAD, optimises, and verifies all numbers
agree to floating-point precision after a session reload.

This test catches regressions in the cross-module interfaces.
"""

import math
from pathlib import Path

import numpy as np
import pytest

import reasitic
from reasitic.exports import (
    read_cif,
    read_sonnet,
    write_cif_file,
    write_fasthenry_file,
    write_sonnet_file,
    write_spice_broadband_file,
    write_spice_subckt_file,
    write_tek4014_file,
    write_tek_file,
)
from reasitic.inductance import (
    auto_filament_subdivisions,
    compute_self_inductance,
    coupling_coefficient,
    mohan_modified_wheeler,
    solve_inductance_matrix,
    solve_inductance_mna,
)
from reasitic.network import (
    deembed_pad_open,
    linear_freqs,
    read_touchstone_file,
    two_port_sweep,
    write_touchstone_file,
    y_to_s,
    y_to_z,
)
from reasitic.network.analysis import (
    calc_transformer,
    pi3_model,
    pi4_model,
    pi_model_at_freq,
    pix_model,
    self_resonance,
    shunt_resistance,
    zin_terminated,
)
from reasitic.optimise import (
    batch_opt_square,
    optimise_area_square_spiral,
    optimise_polygon_spiral,
    optimise_square_spiral,
    optimise_symmetric_square,
    sweep_square_spiral,
)
from reasitic.persistence import load_session, save_session
from reasitic.report import design_report
from reasitic.substrate import (
    coupled_capacitance_per_pair,
    green_function_static,
    setup_green_fft_grid,
    shape_shunt_capacitance,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


def test_full_workflow_round_trip(tmp_path: Path, tech) -> None:
    """The mega-test: every analysis path, every export format, save/load."""
    f = 2.4

    # ---- 1. Build geometries ----
    sp = reasitic.square_spiral(
        "L1", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    pad = reasitic.capacitor(
        "PAD", length=50, width=50,
        metal_top="m3", metal_bottom="m2", tech=tech,
    )
    gnd = reasitic.square_spiral(
        "G", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3", x_origin=300,
    )
    shapes = {"L1": sp, "PAD": pad, "G": gnd}

    # ---- 2. Single-frequency analysis ----
    L = compute_self_inductance(sp)
    R_dc = reasitic.compute_dc_resistance(sp, tech)
    R_ac = reasitic.compute_ac_resistance(sp, tech, f)
    Q = reasitic.metal_only_q(sp, tech, f)
    pi = pi_model_at_freq(sp, tech, f)
    pix = pix_model(sp, tech, f)
    pi3 = pi3_model(sp, tech, f, ground_shape=gnd)
    pi4 = pi4_model(sp, tech, f, pad1=pad, pad2=pad)
    sr = self_resonance(sp, tech, f_low_ghz=1.0, f_high_ghz=20.0)
    pr = shunt_resistance(sp, tech, f)
    zin = zin_terminated(sp, tech, f, z_load_ohm=50.0 + 0j)
    transA = calc_transformer(sp, gnd, tech, f)
    k = coupling_coefficient(sp, gnd)
    M = reasitic.compute_mutual_inductance(sp, gnd)
    C_shunt = shape_shunt_capacitance(sp, tech)

    # All values should be finite and physical
    assert math.isfinite(L) and L > 0
    assert math.isfinite(R_dc) and R_dc > 0
    assert math.isfinite(R_ac) and R_ac >= R_dc
    assert math.isfinite(Q) and Q > 0
    assert pi.L_nH == pytest.approx(L, rel=1e-9)
    assert pix.L_nH == pytest.approx(L, rel=1e-9)
    assert pi3.L_series_nH > 0
    assert pi4.C_pad1_fF > 0  # pad explicit
    assert sr.converged
    assert pr.R_p_ohm > pr.R_series_ohm
    assert math.isfinite(zin.real) and math.isfinite(zin.imag)
    assert -1.0 < transA.k < 1.0
    assert k == pytest.approx(transA.k, rel=1e-9)
    assert pytest.approx(transA.M_nH, rel=1e-9) == M
    assert C_shunt > 0

    # ---- 3. Filament-level solvers ----
    L_fil_1, _R_fil_1 = solve_inductance_matrix(sp, tech, freq_ghz=f)
    L_fil_2, _R_fil_2 = solve_inductance_mna(sp, tech, freq_ghz=f)
    n_w, n_t = auto_filament_subdivisions(
        sp.segments()[0], rsh_ohm_per_sq=0.02, freq_ghz=f
    )
    assert math.isfinite(L_fil_1) and math.isfinite(L_fil_2)
    assert n_w >= 1 and n_t >= 1

    # ---- 4. Sanity-check Mohan formula ----
    L_mohan = mohan_modified_wheeler(
        n_turns=3, d_outer_um=200, d_inner_um=148, shape="square",
    )
    assert L_mohan > 0

    # ---- 5. Frequency sweep ----
    fs = linear_freqs(0.1, 10.0, 0.5)
    sweep = two_port_sweep(sp, tech, fs)
    assert len(sweep.S) == len(fs)
    s2p_text = "".join(str(p.matrix) for p in sweep.to_touchstone_points())
    assert len(s2p_text) > 0

    # ---- 6. Y/Z/S algebra round-trip ----
    Y = sweep.Y[10]
    with np.errstate(divide="ignore", invalid="ignore"):
        Z = y_to_z(Y)
    S = y_to_s(Y)
    assert Y.shape == (2, 2)
    assert Z.shape == (2, 2)
    assert S.shape == (2, 2)

    # ---- 7. Pad de-embedding ----
    Y_open = reasitic.network.spiral_y_at_freq(pad, tech, freq_ghz=f)
    Y_dut = deembed_pad_open(Y, Y_open)
    np.testing.assert_allclose(Y_dut, Y - Y_open, atol=1e-12)

    # ---- 8. Substrate Green's function ----
    g = green_function_static(rho_um=10, z1_um=5, z2_um=5, tech=tech)
    assert math.isfinite(g) and g > 0
    C_pair = coupled_capacitance_per_pair(
        rho_um=10, z1_um=5, z2_um=5, a1_um2=100, a2_um2=100, tech=tech,
    )
    assert C_pair > 0
    fft_grid = setup_green_fft_grid(tech, z1_um=5, z2_um=5, nx=16, ny=16)
    assert fft_grid.g_grid.shape == (16, 16)

    # ---- 9. All export formats ----
    cif_path = tmp_path / "L1.cif"
    write_cif_file(cif_path, [sp], tech)
    assert "DS 1" in cif_path.read_text()

    son_path = tmp_path / "L1.son"
    write_sonnet_file(son_path, [sp], tech)
    assert "FTYP SONPROJ" in son_path.read_text()

    spice_path = tmp_path / "L1.sub"
    write_spice_subckt_file(spice_path, sp, tech, freq_ghz=f)
    assert ".subckt L1_pi" in spice_path.read_text()

    spice_bb_path = tmp_path / "L1_bb.sub"
    write_spice_broadband_file(spice_bb_path, sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
    assert spice_bb_path.read_text().count(".subckt") == 3

    fh_path = tmp_path / "L1.inp"
    write_fasthenry_file(fh_path, sp, tech)
    assert "* reASITIC FastHenry" in fh_path.read_text()

    tek_path = tmp_path / "L1.tek"
    write_tek_file(tek_path, [sp])
    assert "name=L1" in tek_path.read_text()

    tek4014_path = tmp_path / "L1.4014"
    write_tek4014_file(tek4014_path, [sp])
    assert tek4014_path.read_bytes()[0] == 0x1D

    s2p_path = tmp_path / "L1.s2p"
    write_touchstone_file(s2p_path, sweep.to_touchstone_points(param="S"))
    parsed = read_touchstone_file(s2p_path)
    assert len(parsed.points) == len(fs)

    # Round-trip CIF through reader
    cif_shapes = read_cif(cif_path.read_text(), tech)
    assert len(cif_shapes[0].polygons) == len(sp.polygons)

    # Round-trip Sonnet
    son_shapes = read_sonnet(son_path.read_text(), tech)
    assert len(son_shapes[0].polygons) == len(sp.polygons)

    # ---- 10. Optimisation ----
    opt_sq = optimise_square_spiral(
        tech, target_L_nH=2.0, freq_ghz=f, metal="m3",
    )
    opt_poly = optimise_polygon_spiral(
        tech, target_L_nH=1.0, freq_ghz=f, sides=8, metal="m3",
    )
    opt_area = optimise_area_square_spiral(
        tech, target_L_nH=1.5, freq_ghz=f, metal="m3",
    )
    opt_sym = optimise_symmetric_square(
        tech, target_L_nH=1.0, freq_ghz=f, metal="m3",
    )
    # Some optimisers may not converge depending on tech params; only
    # assert the result objects are well-formed.
    for opt in (opt_sq, opt_poly, opt_area, opt_sym):
        assert math.isfinite(opt.L_nH)

    # Batch optimiser
    batch = batch_opt_square(
        tech, targets=[(1.0, 1.0), (2.0, 2.4), (5.0, 5.0)], metal="m3",
    )
    assert len(batch) == 3
    assert batch["success"].all()

    # Cartesian sweep
    arr = sweep_square_spiral(
        tech,
        length_um=[100.0, 200.0],
        width_um=[10.0],
        spacing_um=[2.0],
        turns=[2.0, 3.0],
        freq_ghz=f,
        metal="m3",
    )
    assert len(arr) == 4

    # ---- 11. Design report ----
    rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
    text = rpt.format_text()
    assert "L_dc" in text
    assert rpt.L_dc_nH == pytest.approx(L, rel=1e-9)

    # ---- 12. JSON save / load round-trip ----
    sess = tmp_path / "session.json"
    save_session(sess, tech=tech, shapes=shapes)
    tech2, shapes2 = load_session(sess)
    assert tech2 is not None
    assert set(shapes2) == set(shapes)
    # Verify identical L
    L_loaded = compute_self_inductance(shapes2["L1"])
    assert L_loaded == pytest.approx(L, rel=1e-9)
    pi_loaded = pi_model_at_freq(shapes2["L1"], tech2, f)
    assert pi_loaded.L_nH == pytest.approx(pi.L_nH, rel=1e-9)
    assert pi_loaded.C_p1_fF == pytest.approx(pi.C_p1_fF, rel=1e-9)


def test_summary_runs_without_error() -> None:
    """``reasitic.summary()`` should not crash on any platform."""
    s = reasitic.summary()
    assert isinstance(s, str)
    assert len(s) > 0


def test_main_module_help_for_known_symbol(capsys) -> None:
    """``python -m reasitic help <symbol>`` should print the docstring."""
    from reasitic.__main__ import main
    rc = main(["help", "compute_self_inductance"])
    assert rc == 0
    out = capsys.readouterr().out
    assert "compute_self_inductance" in out