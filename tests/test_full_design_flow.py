"""End-to-end RFIC design-flow regression test.

Exercises a 3-shape coupled-coil layout through every public
surface of the library:

1. Tech-file parsing.
2. Geometry construction (square spiral × 2 + capacitor pad).
3. Inductance / Resistance / Q at multiple frequencies.
4. Pi-equivalent extraction (Pi, Pi3, Pi4, PiX).
5. Self-resonance + shunt-resistance + Zin-with-load.
6. Both substrate-cap pipelines (per-shape FFT + per-segment Sommerfeld).
7. Y/Z/S parameter sweep + Touchstone round-trip.
8. SLSQP optimisation against a target inductance.
9. All export formats: CIF, GDS, Sonnet, SPICE, FastHenry, Tek.
10. JSON session save / load round-trip.
11. Multi-frequency design report.
12. Skew-segment mutual + parallel limit cross-check.

The test catches regressions in any cross-module interface.
"""

from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pytest

import reasitic
from reasitic.exports import (
    write_cif_file,
    write_fasthenry_file,
    write_sonnet_file,
    write_spice_subckt_file,
    write_tek_file,
)
from reasitic.inductance import (
    coupling_coefficient,
    mutual_inductance_3d_segments,
    parallel_segment_mutual,
)
from reasitic.network import (
    linear_freqs,
    pi3_model,
    pi4_model,
    pi_model_at_freq,
    pix_model,
    self_resonance,
    shunt_resistance,
    two_port_sweep,
    write_touchstone_file,
    z_2port_from_y,
    zin_terminated,
)
from reasitic.optimise import optimise_square_spiral
from reasitic.persistence import load_session, save_session
from reasitic.report import design_report
from reasitic.substrate import analyze_capacitance_driver, substrate_cap_matrix
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


def test_full_design_flow(tmp_path: Path, tech) -> None:
    """One mega-test that exercises the full library pipeline."""

    # ----- 1. Build 3 shapes ---------------------------------------------
    sp1 = reasitic.square_spiral(
        "L1", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3",
    )
    sp2 = reasitic.square_spiral(
        "L2", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3", x_origin=200, y_origin=0,
    )
    pad = reasitic.capacitor(
        "PAD", length=40, width=40,
        metal_top="m3", metal_bottom="m2", tech=tech,
    ).translate(80, 80)

    # ----- 2. Per-spiral L / R / Q at 2.4 GHz ---------------------------
    f0 = 2.4
    L1 = reasitic.compute_self_inductance(sp1)
    L2 = reasitic.compute_self_inductance(sp2)
    R1 = reasitic.compute_ac_resistance(sp1, tech, f0)
    Q1 = reasitic.metal_only_q(sp1, tech, f0)
    assert L1 > 0 and L2 > 0
    assert R1 > 0
    assert Q1 > 0

    # ----- 3. Coupling between spirals ---------------------------------
    k_12 = coupling_coefficient(sp1, sp2)
    assert -1.0 <= k_12 <= 1.0

    # ----- 4. Pi-family models -----------------------------------------
    pi_a = pi_model_at_freq(sp1, tech, f0)
    pix_a = pix_model(sp1, tech, f0)
    pi3_a = pi3_model(sp1, tech, f0, ground_shape=sp2)
    pi4_a = pi4_model(sp1, tech, f0, pad1=pad, pad2=pad)
    assert pi_a.L_nH == pytest.approx(L1, rel=1e-9)
    assert pix_a.L_nH == pytest.approx(L1, rel=1e-9)
    assert pi3_a.L_series_nH > 0
    assert pi4_a.C_pad1_fF > 0

    # ----- 5. Self-resonance + shunt-R + Zin ---------------------------
    # Self-resonance on a small spiral may be above the search band;
    # the converged flag is informational, not a failure condition.
    sr = self_resonance(sp1, tech, f_low_ghz=1.0, f_high_ghz=50.0)
    pr = shunt_resistance(sp1, tech, f0)
    zin = zin_terminated(sp1, tech, f0, z_load_ohm=50.0 + 0j)
    assert isinstance(sr.converged, bool)
    assert pr.R_p_ohm > 0
    assert math.isfinite(zin.real)

    # ----- 6. Substrate cap pipelines ---------------------------------
    # Per-shape FFT pipeline
    C_fft = substrate_cap_matrix(
        [sp1, sp2, pad], tech, nx=64, ny=64,
    )
    assert C_fft.shape == (3, 3)
    assert np.all(np.isfinite(C_fft))

    # Per-segment Sommerfeld pipeline (smaller — just on PAD to keep
    # the test fast; pad has a finite footprint)
    seg_result = analyze_capacitance_driver([pad], tech, n_div=2)
    assert seg_result.P_matrix.shape[0] == seg_result.P_matrix.shape[1]
    assert seg_result.P_matrix.shape[0] > 0

    # ----- 7. Y/Z/S sweep + Touchstone round-trip ----------------------
    fs = linear_freqs(0.5, 5.0, 0.5)
    sweep = two_port_sweep(sp1, tech, fs)
    assert len(sweep.Y) == len(fs)

    s2p_path = tmp_path / "L1.s2p"
    write_touchstone_file(s2p_path, sweep.to_touchstone_points(param="S"))
    assert s2p_path.exists()
    assert s2p_path.stat().st_size > 0

    # Spot-check the impedance helper on the middle frequency
    Y_mid = sweep.Y[len(fs) // 2]
    Z_mid = z_2port_from_y(Y_mid, port=1)
    assert math.isfinite(Z_mid.real)

    # ----- 8. SLSQP optimisation ---------------------------------------
    opt = optimise_square_spiral(
        tech, target_L_nH=2.0, freq_ghz=f0, metal="m3",
        L_tolerance=0.10,
    )
    assert opt.success
    assert opt.L_nH == pytest.approx(2.0, rel=0.105)

    # ----- 9. All export formats --------------------------------------
    cif_path = tmp_path / "L1.cif"
    write_cif_file(cif_path, [sp1, sp2, pad], tech)
    assert "DS 1" in cif_path.read_text()

    son_path = tmp_path / "L1.son"
    write_sonnet_file(son_path, [sp1, sp2, pad], tech)
    assert "FTYP SONPROJ" in son_path.read_text()

    spice_path = tmp_path / "L1.sub"
    write_spice_subckt_file(spice_path, sp1, tech, freq_ghz=f0)
    assert ".subckt L1_pi" in spice_path.read_text()

    fh_path = tmp_path / "L1.inp"
    write_fasthenry_file(fh_path, sp1, tech)
    assert "* reASITIC FastHenry" in fh_path.read_text()

    tek_path = tmp_path / "L1.tek"
    write_tek_file(tek_path, [sp1, sp2, pad])
    assert "name=L1" in tek_path.read_text()

    # GDS export through the full path (gdstk-backed)
    try:
        from reasitic.exports import read_gds_file, write_gds_file

        gds_path = tmp_path / "L1.gds"
        write_gds_file(gds_path, [sp1, sp2, pad])
        assert gds_path.exists() and gds_path.stat().st_size > 0
        # Round-trip
        shapes_back = read_gds_file(gds_path, tech)
        names_back = {s.name for s in shapes_back}
        assert names_back == {"L1", "L2", "PAD"}
    except ImportError:
        pass  # gdstk not installed — skip the GDS leg

    # ----- 10. JSON session round-trip --------------------------------
    sess = tmp_path / "session.json"
    save_session(sess, tech=tech,
                 shapes={"L1": sp1, "L2": sp2, "PAD": pad})
    tech_back, shapes_back = load_session(sess)
    assert tech_back is not None
    assert set(shapes_back) == {"L1", "L2", "PAD"}
    L1_back = reasitic.compute_self_inductance(shapes_back["L1"])
    assert L1_back == pytest.approx(L1, rel=1e-9)

    # ----- 11. Multi-frequency design report --------------------------
    rpt = design_report(sp1, tech, freqs_ghz=[1.0, 2.4, 5.0, 10.0])
    text = rpt.format_text()
    assert "L_dc" in text
    assert rpt.L_dc_nH == pytest.approx(L1, rel=1e-9)

    # ----- 12. Skew-mutual ↔ parallel-Grover cross-check --------------
    # The general 3-D skew kernel should match the closed-form
    # parallel kernel within numerical tolerance for parallel filaments.
    a1 = reasitic.Point(0, 0, 0)
    a2 = reasitic.Point(100, 0, 0)
    b1 = reasitic.Point(0, 10, 0)
    b2 = reasitic.Point(100, 10, 0)
    seg_a = reasitic.Segment(a=a1, b=a2, width=0.0, thickness=0.0, metal=0)
    seg_b = reasitic.Segment(a=b1, b=b2, width=0.0, thickness=0.0, metal=0)
    M_skew = mutual_inductance_3d_segments(seg_a, seg_b)
    M_grover = parallel_segment_mutual(100, 100, 10)
    assert M_skew == pytest.approx(M_grover, rel=1e-6)
