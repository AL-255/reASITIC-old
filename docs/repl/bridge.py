"""In-browser REPL bridge between the JS UI and the reasitic library.

The JS side:
  * loads a .tek tech file and calls ``load_tech(text)`` once;
  * calls ``build_shape(spec)`` whenever the user changes parameters;
  * calls ``analyze_*`` and ``export_*`` for the action buttons.

Each public function returns a plain dict / str so PyProxy.toJs can hand
it to JavaScript without surprises.
"""

from __future__ import annotations

import io
import math
import sys
import traceback

import reasitic
from reasitic.exports.spice import write_spice_subckt
from reasitic.network import (
    linear_freqs,
    pi_model_at_freq,
    self_resonance,
    two_port_sweep,
    write_touchstone,
)


# Global state — single tech and single shape at a time keeps the UI simple.
STATE: dict = {"tech": None, "shape": None, "tech_text": ""}


def load_tech(text: str) -> dict:
    """Parse a .tek file from raw text and stash it in module state."""
    tech = reasitic.parse_tech(text)
    STATE["tech"] = tech
    STATE["tech_text"] = text
    metals = [
        {"index": m.index, "name": m.name or f"m{m.index}", "color": m.color, "t": m.t, "rsh": m.rsh}
        for m in tech.metals
    ]
    return {
        "metals": metals,
        "n_layers": len(tech.layers),
        "n_vias": len(tech.vias),
        "chip": {"chipx": tech.chip.chipx, "chipy": tech.chip.chipy},
    }


def _resolve_metal_color(tech, metal_idx: int) -> tuple[str, str]:
    """(name, color) for a metal index."""
    for m in tech.metals:
        if m.index == metal_idx:
            return (m.name or f"m{metal_idx}", m.color or "white")
    return (f"m{metal_idx}", "white")


def _shape_to_payload(shape) -> dict:
    """Convert a Shape into a JSON-friendly payload for draw.js."""
    tech = STATE["tech"]
    polys = []
    for p in shape.polygons:
        name, color = _resolve_metal_color(tech, p.metal)
        polys.append(
            {
                "metal": p.metal,
                "metal_name": name,
                "color": color,
                "width": p.width,
                "thickness": p.thickness,
                "points": [[v.x, v.y, v.z] for v in p.vertices],
            }
        )

    # Endpoints of the very first and very last segment of the spiral are the
    # natural port locations. For wires the two polygon endpoints suffice.
    ports = []
    if shape.polygons:
        first = shape.polygons[0].vertices
        last = shape.polygons[-1].vertices
        if first:
            ports.append({"x": first[0].x, "y": first[0].y})
        if last:
            ports.append({"x": last[-1].x, "y": last[-1].y})

    bx0, by0, bx1, by1 = shape.bounding_box()
    if bx0 == bx1 and by0 == by1:
        bx0, by0, bx1, by1 = -1.0, -1.0, 1.0, 1.0
    return {
        "name": shape.name,
        "bbox": [bx0, by0, bx1, by1],
        "polygons": polys,
        "ports": ports,
        "metal_index": shape.metal,
        "turns": shape.turns,
        "width": shape.width,
        "spacing": shape.spacing,
        "sides": shape.sides,
    }


def build_shape(spec: dict) -> dict:
    """Build a Shape from the JS-side parameter dict and return its payload.

    spec keys:
      kind: "square_spiral" | "polygon_spiral" | "symmetric_square" | "wire"
      length, width, spacing, turns, sides, metal, name
    """
    tech = STATE["tech"]
    if tech is None:
        raise RuntimeError("Load a tech file first.")

    kind = spec.get("kind", "square_spiral")
    name = spec.get("name", "L1")
    metal = spec.get("metal", tech.metals[-1].name or 0)
    width = float(spec.get("width", 10.0))
    length = float(spec.get("length", 170.0))
    spacing = float(spec.get("spacing", 3.0))
    turns = float(spec.get("turns", 2.0))
    sides = int(spec.get("sides", 8))

    if kind == "square_spiral":
        sh = reasitic.square_spiral(
            name, length=length, width=width, spacing=spacing,
            turns=turns, tech=tech, metal=metal,
        )
    elif kind == "polygon_spiral":
        sh = reasitic.polygon_spiral(
            name, radius=length, width=width, spacing=spacing,
            turns=turns, tech=tech, sides=sides, metal=metal,
        )
    elif kind == "symmetric_square":
        sh = reasitic.symmetric_square(
            name, length=length, width=width, spacing=spacing,
            turns=turns, tech=tech, metal=metal,
        )
    elif kind == "wire":
        sh = reasitic.wire(
            name, length=length, width=width, tech=tech, metal=metal,
        )
    else:
        raise ValueError(f"unknown shape kind: {kind}")

    STATE["shape"] = sh
    return _shape_to_payload(sh)


# --- Analysis -------------------------------------------------------------

def _require() -> tuple:
    sh = STATE["shape"]
    tech = STATE["tech"]
    if sh is None or tech is None:
        raise RuntimeError("Build a shape first.")
    return sh, tech


def analyze_lrq(freq_ghz: float) -> dict:
    sh, tech = _require()
    L = reasitic.compute_self_inductance(sh)
    R_dc = reasitic.compute_dc_resistance(sh, tech)
    R_ac = reasitic.compute_ac_resistance(sh, tech, freq_ghz)
    Q = reasitic.metal_only_q(sh, tech, freq_ghz)
    n_segs = len(sh.segments())
    total_len = sum(s.length for s in sh.segments())
    return {
        "freq_ghz": freq_ghz,
        "L_nH": L,
        "R_dc_ohm": R_dc,
        "R_ac_ohm": R_ac,
        "Q": Q,
        "n_segments": n_segs,
        "total_length_um": total_len,
    }


def analyze_pi(freq_ghz: float) -> dict:
    sh, tech = _require()
    pi = pi_model_at_freq(sh, tech, freq_ghz)
    return {
        "freq_ghz": freq_ghz,
        "L_nH": pi.L_nH,
        "R_series": pi.R_series,
        "C_p1_fF": pi.C_p1_fF,
        "C_p2_fF": pi.C_p2_fF,
        "g_p1": pi.g_p1,
        "g_p2": pi.g_p2,
    }


def analyze_sweep(f1: float, f2: float, step: float) -> dict:
    sh, tech = _require()
    if step <= 0:
        raise ValueError("Sweep step must be > 0")
    if f2 <= f1:
        raise ValueError("Sweep f2 must be > f1")
    fs = linear_freqs(f1, f2, step)
    sweep = two_port_sweep(sh, tech, fs)
    s11 = []
    s21 = []
    s12 = []
    s22 = []
    for f, S in zip(fs, sweep.S, strict=True):
        s11.append(abs(S[0, 0]))
        s12.append(abs(S[0, 1]))
        s21.append(abs(S[1, 0]))
        s22.append(abs(S[1, 1]))
    # Self-resonance on best-effort basis
    sr_freq = None
    try:
        sr = self_resonance(sh, tech, f_start=f1, f_stop=f2)
        if sr and getattr(sr, "f_self_res", None):
            sr_freq = sr.f_self_res
    except Exception:
        sr_freq = None
    return {
        "freqs_ghz": list(fs),
        "abs_S11": s11,
        "abs_S12": s12,
        "abs_S21": s21,
        "abs_S22": s22,
        "self_resonance_ghz": sr_freq,
    }


def export_s2p(f1: float, f2: float, step: float) -> str:
    sh, tech = _require()
    fs = linear_freqs(f1, f2, step)
    sweep = two_port_sweep(sh, tech, fs)
    pts = sweep.to_touchstone_points(param="S")
    return write_touchstone(pts, param="S", fmt="MA", z0_ohm=50.0)


def export_spice(freq_ghz: float) -> str:
    sh, tech = _require()
    return write_spice_subckt(sh, tech, freq_ghz)


def geom_info() -> dict:
    sh, tech = _require()
    n_segs = len(sh.segments())
    total_len = sum(s.length for s in sh.segments())
    metal_name, _ = _resolve_metal_color(tech, sh.metal)
    return {
        "name": sh.name,
        "metal": metal_name,
        "metal_index": sh.metal,
        "turns": sh.turns,
        "width_um": sh.width,
        "spacing_um": sh.spacing,
        "sides": sh.sides,
        "n_polygons": len(sh.polygons),
        "n_segments": n_segs,
        "total_segment_length_um": total_len,
        "bbox": list(sh.bounding_box()),
    }


# --- Free-form REPL ------------------------------------------------------

def run_repl(source: str) -> dict:
    """Execute user Python with `shape`, `tech`, and `reasitic` in scope.

    Captures stdout/stderr; returns {"stdout": ..., "stderr": ..., "ok": bool}.
    """
    g = {
        "__name__": "__repl__",
        "reasitic": reasitic,
        "shape": STATE["shape"],
        "tech": STATE["tech"],
        "math": math,
    }
    out_buf = io.StringIO()
    err_buf = io.StringIO()
    old_out, old_err = sys.stdout, sys.stderr
    sys.stdout, sys.stderr = out_buf, err_buf
    ok = True
    try:
        exec(compile(source, "<repl>", "exec"), g)
    except BaseException:
        ok = False
        traceback.print_exc(file=err_buf)
    finally:
        sys.stdout, sys.stderr = old_out, old_err
    # If the user reassigned shape, sync it.
    if "shape" in g and g["shape"] is not None:
        STATE["shape"] = g["shape"]
    return {"ok": ok, "stdout": out_buf.getvalue(), "stderr": err_buf.getvalue()}


def version_info() -> str:
    return reasitic.summary()


def current_shape_payload():
    """Return the draw.js payload for the currently bound shape, or None."""
    sh = STATE["shape"]
    if sh is None or STATE["tech"] is None:
        return None
    return _shape_to_payload(sh)
