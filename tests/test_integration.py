"""End-to-end integration test exercising the full design flow.

Builds a spiral, runs every analysis path, exports to every format,
round-trips through Save/Load, and verifies that the loaded shape
reproduces the original numerical results.
"""

from pathlib import Path

import numpy as np
import pytest

from reasitic import (
    Tech,
    parse_tech_file,
    square_spiral,
)
from reasitic.exports import (
    write_cif_file,
    write_sonnet,
    write_spice_subckt_file,
    write_tek_file,
)
from reasitic.network import (
    linear_freqs,
    two_port_sweep,
    write_touchstone_file,
)
from reasitic.network.analysis import (
    calc_transformer,
    pi3_model,
    pi4_model,
    pi_model_at_freq,
    self_resonance,
    shunt_resistance,
    zin_terminated,
)
from reasitic.optimise import optimise_square_spiral
from reasitic.persistence import load_session, save_session
from reasitic.report import design_report
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech() -> Tech:
    return parse_tech_file(_BICMOS)


def test_full_design_flow(tmp_path: Path, tech: Tech) -> None:
    # 1) Build geometry
    sp = square_spiral(
        "L1",
        length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    sp2 = square_spiral(
        "L2",
        length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3", x_origin=215,
    )
    shapes = {"L1": sp, "L2": sp2}

    # 2) Single-frequency analysis
    f = 2.4
    pi = pi_model_at_freq(sp, tech, f)
    z = zin_terminated(sp, tech, f, z_load_ohm=50.0 + 0j)
    sr = self_resonance(sp, tech, f_low_ghz=1.0, f_high_ghz=20.0)
    pr = shunt_resistance(sp, tech, f)
    pi3 = pi3_model(sp, tech, f, ground_shape=sp2)
    pi4 = pi4_model(sp, tech, f)
    trans = calc_transformer(sp, sp2, tech, f)

    assert pi.L_nH > 0
    assert z.real != 0
    assert sr.converged
    assert pr.R_p_ohm > pr.R_series_ohm  # Q > 0 → R_p > R_s
    assert pi3.L_series_nH > 0
    assert pi4.C_pad1_fF == 0.0  # no pad supplied
    assert -1.0 < trans.k < 1.0

    # 3) Frequency sweep + Touchstone
    fs = linear_freqs(1.0, 5.0, 1.0)
    sweep = two_port_sweep(sp, tech, fs)
    assert len(sweep.freqs_ghz) == 5
    s2p_path = tmp_path / "L1.s2p"
    write_touchstone_file(s2p_path, sweep.to_touchstone_points(param="S"))
    assert s2p_path.exists()
    assert "GHz S" in s2p_path.read_text()

    # 4) Layout exports
    cif_path = tmp_path / "L1.cif"
    write_cif_file(cif_path, [sp], tech)
    assert "DS 1" in cif_path.read_text()

    tek_path = tmp_path / "L1.tek"
    write_tek_file(tek_path, [sp])
    assert "name=L1" in tek_path.read_text()

    son_path = tmp_path / "L1.son"
    son_path.write_text(write_sonnet([sp], tech))
    assert "FTYP SONPROJ" in son_path.read_text()

    sp_path = tmp_path / "L1.sp"
    write_spice_subckt_file(sp_path, sp, tech, freq_ghz=f)
    assert ".subckt L1_pi" in sp_path.read_text()

    # 5) Persistence round-trip
    sess_path = tmp_path / "session.json"
    save_session(sess_path, tech=tech, shapes=shapes)
    tech2, shapes2 = load_session(sess_path)
    assert tech2 is not None
    assert set(shapes2) == {"L1", "L2"}
    # Reload-and-compute should match
    L_orig = pi.L_nH
    pi_loaded = pi_model_at_freq(shapes2["L1"], tech2, f)
    assert pi_loaded.L_nH == pytest.approx(L_orig, rel=1e-9)

    # 6) Optimisation
    opt = optimise_square_spiral(
        tech, target_L_nH=2.0, freq_ghz=f, metal="m3"
    )
    assert opt.success
    assert 1.5 < opt.L_nH < 2.5

    # 7) Design report
    rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
    assert len(rpt.points) == 3
    text = rpt.format_text()
    assert "L_dc" in text
    assert "f_SR" in text


def test_shapes_are_picklable(tech: Tech) -> None:
    """Sanity: dataclasses survive a JSON round-trip via persistence."""
    import json

    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    from reasitic.persistence import shape_from_dict, shape_to_dict

    d = shape_to_dict(sp)
    json.dumps(d)  # serialisable
    sp2 = shape_from_dict(d)
    # Numerical equivalence
    L1 = float(np.sum([v.x for p in sp.polygons for v in p.vertices]))
    L2 = float(np.sum([v.x for p in sp2.polygons for v in p.vertices]))
    assert pytest.approx(L2) == L1


def test_compute_self_inductance_invariant_under_translation(tech: Tech) -> None:
    """Translating a shape should leave its self-inductance unchanged."""
    from reasitic import compute_self_inductance

    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    L0 = compute_self_inductance(sp)
    L1 = compute_self_inductance(sp.translate(500.0, 300.0))
    assert pytest.approx(L0, rel=1e-12) == L1


def test_save_load_preserves_shape_count(tmp_path: Path, tech: Tech) -> None:
    shapes = {
        f"L{i}": square_spiral(
            f"L{i}", length=100 + 50 * i, width=10, spacing=2,
            turns=2, tech=tech, metal="m3",
        )
        for i in range(5)
    }
    out = tmp_path / "many.json"
    save_session(out, tech=tech, shapes=shapes)
    _, loaded = load_session(out)
    assert len(loaded) == 5
    assert set(loaded) == set(shapes)