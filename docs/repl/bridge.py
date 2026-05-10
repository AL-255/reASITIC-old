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
    vias = [
        {"index": i, "name": v.name or f"via{i}", "top": v.top, "bottom": v.bottom,
         "width": v.width, "space": v.space}
        for i, v in enumerate(tech.vias)
    ]
    return {
        "metals": metals,
        "vias": vias,
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


def _resolve_metal(metal_arg) -> tuple[int, str, str, float]:
    """Look up a metal by name or index. Returns (idx, name, color, thickness)."""
    tech = STATE["tech"]
    if tech is None:
        raise RuntimeError("Load a tech file first.")
    for m in tech.metals:
        nm = m.name or f"m{m.index}"
        if nm.lower() == str(metal_arg).lower() or str(m.index) == str(metal_arg):
            return m.index, nm, m.color or "white", m.t
    raise ValueError(f"unknown metal: {metal_arg}")



def _layout_polys_to_payload(shape, name: str) -> dict:
    """Convert a Shape with C-faithful CIF polygons into a draw.js payload.

    Used by the builders whose ``layout_polygons`` output IS the canonical
    CIF emission (SYMSQ, SYMPOLY, BALUN, MMSQ, TRANS, VIA): each polygon
    in the layout is a single closed quad/box, not a fat-stroke
    centerline. We pack one polygon per ``layout_polygons`` entry, with
    the polygon's vertices verbatim as a single ``segment_polys`` quad.
    """
    from reasitic.geometry import layout_polygons
    tech = STATE["tech"]
    polys_raw = layout_polygons(shape, tech)
    poly_payload: list[dict] = []
    all_x: list[float] = []
    all_y: list[float] = []
    for p in polys_raw:
        if p.metal >= len(tech.metals):
            via_idx = p.metal - len(tech.metals)
            via = tech.vias[via_idx] if 0 <= via_idx < len(tech.vias) else None
            mname = via.name if via else f"via{via_idx}"
            mcolor = (via.color if via else None) or "white"
            # Sort vias on top of every metal: draw.js stacks polygons in
            # ascending ``metal`` order, so a large positive value puts
            # the via cluster squares above the M-overlap pads where they
            # need to be visible.
            metal_idx = 10_000 + via_idx
        else:
            m = tech.metals[p.metal]
            mname = m.name or f"m{p.metal}"
            mcolor = m.color or "white"
            metal_idx = p.metal
        verts = list(p.vertices)
        # Drop the duplicated closing vertex if present.
        if (len(verts) >= 2
                and abs(verts[0].x - verts[-1].x) < 1e-9
                and abs(verts[0].y - verts[-1].y) < 1e-9):
            verts = verts[:-1]
        corners = [[v.x, v.y] for v in verts]
        for x, y in corners:
            all_x.append(x); all_y.append(y)
        poly_payload.append({
            "metal": metal_idx,
            "metal_name": mname,
            "color": mcolor,
            "width": p.width,
            "thickness": p.thickness,
            "points": [[v.x, v.y, v.z] for v in verts],
            "segment_polys": [corners] if corners else [],
        })

    bbox = ([min(all_x), min(all_y), max(all_x), max(all_y)]
            if all_x else [0.0, 0.0, 1.0, 1.0])
    return {
        "name": name,
        "bbox": bbox,
        "polygons": poly_payload,
        "ports": [],
        "metal_index": shape.metal,
        "turns": shape.turns,
        "width": shape.width,
        "spacing": shape.spacing,
        "sides": shape.sides,
    }


def build_shape(spec: dict) -> dict:
    """Build a Shape from the JS-side parameter dict and return its payload.

    Recognised ``kind`` values:

      square_spiral / polygon_spiral / ring / wire / capacitor / via
      symmetric_square / symmetric_polygon / multi_metal_square
      transformer_primary / transformer_secondary
      balun_primary / balun_secondary

    Per-command keys mirror the ./run/doc syntax. Optional keys are sent
    only when the user set a positive value; missing keys mean "apply the
    ASITIC default". Recognised optional keys:

      wid, ilen, iwid           — square family rectangular bounds (SQ, SYMSQ, SQMM, TRANS)
      w2                        — BALUN secondary metal width
      exit_metal                — explicit EXIT layer (SQ, SYMSQ, SYMPOLY, TRANS, SQMM)
      metal_top / metal_bottom  — CAP plate layers
      metal_transition          — BALUN METAL2 (inter-turn bridge layer)
      via_phase                 — VIA electrical phase

    Once a Shape is built, every kind is rendered through
    :func:`_layout_polys_to_payload`, i.e. the EXACT polygons the C
    binary writes to CIF/GDS (see ``layout_polygons`` in
    ``reasitic.geometry``). This is the same path the
    ``test_layout_polygons_against_cif`` suite verifies against the
    captured golden CIFs from the 1999 ASITIC binary.
    """
    tech = STATE["tech"]
    if tech is None:
        raise RuntimeError("Load a tech file first.")

    kind = spec.get("kind", "square_spiral")
    name = spec.get("name", "L1")
    metal = spec.get("metal") or (tech.metals[-1].name or 0)
    exit_metal = spec.get("exit_metal") or None
    width = float(spec.get("width", 10.0))
    length = float(spec.get("length", 170.0))
    spacing = float(spec.get("spacing", 3.0))
    turns = float(spec.get("turns", 2.0))
    sides = int(spec.get("sides", 8))
    radius = float(spec.get("radius", 100.0))
    x_origin = float(spec.get("x_origin", 0.0))
    y_origin = float(spec.get("y_origin", 0.0))
    phase = float(spec.get("phase", 0.0))
    orient = float(spec.get("orient", 0.0))
    # Optional rectangular / inner-bound params (ignored when 0 / unset).
    wid_opt = spec.get("wid")
    ilen_opt = spec.get("ilen")
    iwid_opt = spec.get("iwid")
    w2_opt = spec.get("w2")
    # CAP plates: ``metal_top`` (new UI) falls back to ``metal`` (legacy /
    # test-fixture compat). ``metal_bottom`` is required by the C and is
    # always passed by the UI / tests.
    metal_top = spec.get("metal_top") or None
    metal_bottom = spec.get("metal_bottom") or None
    # BALUN bridge / transition layer: ``metal_transition`` is the new UI
    # name; ``secondary_metal`` is the legacy alias still used by
    # tests/test_repl_layout_match.py.
    metal_transition = (
        spec.get("metal_transition")
        or spec.get("secondary_metal")
        or None
    )
    # Combine ORIENT (degrees, ASITIC convention) with PHASE (radians)
    # into the single ``phase`` argument the Python builder accepts.
    total_phase = phase + math.radians(orient)

    if wid_opt is not None and float(wid_opt) > 0 and abs(float(wid_opt) - length) > 1e-9:
        # The square-family Python builders currently take a single LEN
        # (square footprint). The C ASITIC supports rectangular LEN×WID
        # for SQ / SYMSQ / SQMM / TRANS but we haven't ported that path
        # yet — surface the constraint so users aren't silently misled.
        raise NotImplementedError(
            "Rectangular WID != LEN is not yet supported. "
            "Leave WID blank or set WID = LEN.",
        )
    if ilen_opt is not None and float(ilen_opt) > 0 and kind in (
        "square_spiral", "multi_metal_square",
    ):
        # SQ / SQMM in C support an inner-bound ILEN; the Python builder
        # doesn't yet — surface rather than silently ignore.
        raise NotImplementedError(
            "ILEN inner-bound is not yet supported for SQ / SQMM.",
        )
    if iwid_opt is not None and float(iwid_opt) > 0:
        raise NotImplementedError("IWID is not yet supported.")
    if w2_opt is not None and float(w2_opt) > 0 and float(w2_opt) != width:
        raise NotImplementedError(
            "Independent W2 (balun secondary width) is not yet supported. "
            "Leave W2 blank or set W2 = W1.",
        )

    if kind == "square_spiral":
        sh = reasitic.square_spiral(
            name, length=length, width=width, spacing=spacing, turns=turns,
            tech=tech, metal=metal,
            x_origin=x_origin, y_origin=y_origin, phase=total_phase,
        )
        # ASITIC's SQ adds a via + exit lead by default. If the user
        # supplied an EXIT layer, honour it; otherwise the canonical
        # builder defaults to one metal below (`shape.metal - 1`).
        if exit_metal:
            sh.exit_metal = _resolve_metal(exit_metal)[0]
    elif kind == "wire":
        sh = reasitic.wire(
            name, length=length, width=width, tech=tech, metal=metal,
            x_origin=x_origin, y_origin=y_origin, phase=total_phase,
        )
    elif kind == "ring":
        gap_deg = float(spec.get("gap", 0.0))
        n_sides = sides if sides >= 3 else 16
        ring_radius = float(spec.get("radius", length))
        sh = reasitic.ring(
            name, radius=ring_radius, width=width, gap=gap_deg,
            sides=n_sides, tech=tech, metal=metal,
            x_origin=x_origin, y_origin=y_origin, phase=total_phase,
        )
    elif kind == "capacitor":
        m_top = metal_top if metal_top else metal
        m_bot = metal_bottom if metal_bottom else metal
        sh = reasitic.capacitor(
            name, length=length, width=width,
            metal_top=m_top, metal_bottom=m_bot, tech=tech,
            x_origin=x_origin, y_origin=y_origin,
        )
    elif kind == "polygon_spiral":
        sh = reasitic.polygon_spiral(
            name, radius=radius, width=width, spacing=spacing,
            turns=turns, sides=sides if sides >= 3 else 8,
            tech=tech, metal=metal,
            x_origin=x_origin, y_origin=y_origin, phase=total_phase,
        )
    elif kind == "symmetric_square":
        ilen_val = float(ilen_opt) if ilen_opt and float(ilen_opt) > 0 else (width + spacing)
        sh = reasitic.symmetric_square(
            name, length=length, width=width, spacing=spacing, turns=turns,
            ilen=ilen_val,
            tech=tech, primary_metal=metal,
            exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin,
        )
    elif kind == "symmetric_polygon":
        ilen_val = float(ilen_opt) if ilen_opt and float(ilen_opt) > 0 else (width + spacing)
        sh = reasitic.symmetric_polygon(
            name, radius=radius, width=width, spacing=spacing, turns=turns,
            ilen=ilen_val,
            sides=sides if sides >= 4 else 8,
            tech=tech, primary_metal=metal,
            exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin,
        )
    elif kind == "multi_metal_square":
        # SQMM EXIT is the BOTTOM of the metal stack (required-ish in
        # the C; we default to one metal below the top).
        bottom = exit_metal if exit_metal else None
        if bottom is None:
            top_idx = _resolve_metal(metal)[0]
            for m in tech.metals:
                if m.index == top_idx - 1:
                    bottom = m.name or f"m{m.index}"
                    break
        sh = reasitic.multi_metal_square(
            name, length=length, width=width, spacing=spacing, turns=turns,
            tech=tech, metal=metal,
            exit_metal=bottom if bottom else metal,
            x_origin=x_origin, y_origin=y_origin,
        )
    elif kind in ("transformer_primary", "transformer_secondary"):
        which = "primary" if kind == "transformer_primary" else "secondary"
        sh = reasitic.transformer(
            name, length=length, width=width, spacing=spacing, turns=turns,
            tech=tech, metal=metal,
            exit_metal=exit_metal if exit_metal else None,
            x_origin=x_origin, y_origin=y_origin, which=which,
        )
    elif kind in ("balun_primary", "balun_secondary"):
        which = "primary" if kind == "balun_primary" else "secondary"
        # BALUN METAL2 (transition / bridge) drives the centre-tap via
        # cluster — pass it as exit_metal so the layout matches the C.
        bridge = metal_transition or None
        sh = reasitic.balun(
            name, length=length, width=width, spacing=spacing, turns=turns,
            tech=tech, primary_metal=metal,
            secondary_metal=bridge if bridge else metal,
            exit_metal=bridge if bridge else metal,
            x_origin=x_origin, y_origin=y_origin, which=which,
        )
    elif kind == "via":
        nx = int(spec.get("n_via_x", 1))
        ny = int(spec.get("n_via_y", nx))
        via_index = int(spec.get("via_index", 0))
        sh = reasitic.via(
            name, tech=tech, via_index=via_index, nx=nx, ny=ny,
            x_origin=x_origin, y_origin=y_origin,
        )
    else:
        raise ValueError(f"unknown shape kind: {kind}")

    STATE["shape"] = sh
    return _layout_polys_to_payload(sh, name)


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
    return _layout_polys_to_payload(sh, sh.name)
