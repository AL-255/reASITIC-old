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
    pi3_model,
    pi_model_at_freq,
    pix_model,
    self_resonance,
    shunt_resistance,
    spiral_y_at_freq,
    two_port_sweep,
    write_touchstone,
    z_2port_from_y,
    zin_terminated,
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
        "ports": _compute_ports(shape),
        "metal_index": shape.metal,
        "turns": shape.turns,
        "width": shape.width,
        "spacing": shape.spacing,
        "sides": shape.sides,
    }


def _compute_ports(shape) -> list[dict]:
    """Best-effort port markers for the layout view.

    For shapes whose ``.polygons`` is a single centerline polyline (wire,
    ring, square_spiral, polygon_spiral, multi_metal_square) we use the
    first / last polyline vertex as port 1 / port 2. ``via`` gets a single
    marker at the cluster centre, and ``capacitor`` gets one at the
    plate centre.

    Each port carries its ``metal_name`` and tech-file ``color`` so the
    canvas can render the marker in the same colour as the layer it sits
    on.

    For shapes whose ``.polygons`` is already the canonical CIF
    quad-per-side emission (``transformer_*``, ``balun_*``, ``symsq``,
    ``sympoly``), we don't have a per-kind port-resolution pass yet —
    those return ``[]`` and the layout shows no port markers (see §9 in
    TODO.md).
    """
    tech = STATE["tech"]
    polys = shape.polygons

    def metal_info(metal_idx: int) -> tuple[str, str]:
        for m in tech.metals:
            if m.index == metal_idx:
                return (m.name or f"m{metal_idx}", m.color or "white")
        return (f"m{metal_idx}", "white")

    if shape.kind == "via":
        name, color = metal_info(shape.metal)
        return [{
            "x": shape.x_origin, "y": shape.y_origin, "label": "V",
            "metal_name": name, "color": color,
        }]
    if shape.kind == "capacitor":
        cx = shape.x_origin + shape.length * 0.5
        cy = shape.y_origin + shape.width * 0.5
        name, color = metal_info(shape.metal)
        return [{
            "x": cx, "y": cy, "label": "C",
            "metal_name": name, "color": color,
        }]
    if len(polys) == 1 and len(polys[0].vertices) >= 2:
        first = polys[0].vertices[0]
        last = polys[0].vertices[-1]
        name, color = metal_info(polys[0].metal)
        ports = [{
            "x": first.x, "y": first.y, "label": "P1",
            "metal_name": name, "color": color,
        }]
        if abs(first.x - last.x) > 1e-9 or abs(first.y - last.y) > 1e-9:
            ports.append({
                "x": last.x, "y": last.y, "label": "P2",
                "metal_name": name, "color": color,
            })
        return ports
    return []


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

    # ``spec`` comes through PyProxy.toPy from JS, so missing / hidden
    # inputs arrive as ``None`` (JS ``undefined``) rather than absent
    # keys. ``dict.get(..., default)`` therefore returns ``None`` and a
    # bare ``float(None)`` crashes. _f / _i / _opt_str centralise the
    # None-tolerant defaulting.
    def _f(key, default):
        v = spec.get(key, default)
        if v is None:
            return float(default)
        try:
            f = float(v)
        except (TypeError, ValueError):
            return float(default)
        # NaN appears when the user blanks a hidden input; treat as
        # "not set" so we fall back to the shape's natural default.
        return float(default) if (f != f) else f

    def _i(key, default):
        v = spec.get(key, default)
        if v is None:
            return int(default)
        try:
            return int(float(v))
        except (TypeError, ValueError):
            return int(default)

    def _opt(key):
        v = spec.get(key)
        if v is None or v == "":
            return None
        return v

    kind = spec.get("kind", "square_spiral") or "square_spiral"
    name = spec.get("name", "L1") or "L1"
    metal = _opt("metal") or (tech.metals[-1].name or 0)
    exit_metal = _opt("exit_metal")
    width = _f("width", 10.0)
    length = _f("length", 170.0)
    spacing = _f("spacing", 3.0)
    turns = _f("turns", 2.0)
    sides = _i("sides", 8)
    radius = _f("radius", 100.0)
    x_origin = _f("x_origin", 0.0)
    y_origin = _f("y_origin", 0.0)
    phase = _f("phase", 0.0)
    orient = _f("orient", 0.0)
    # Optional rectangular / inner-bound params. ``_opt_pos`` returns
    # ``None`` when the value is missing / blank / NaN / non-positive, so
    # callers can treat "value present and meaningful" as "is not None".
    def _opt_pos(key):
        v = spec.get(key)
        if v is None or v == "":
            return None
        try:
            f = float(v)
        except (TypeError, ValueError):
            return None
        if f != f or f <= 0:  # NaN or non-positive
            return None
        return f

    wid_opt = _opt_pos("wid")
    ilen_opt = _opt_pos("ilen")
    iwid_opt = _opt_pos("iwid")
    w2_opt = _opt_pos("w2")
    # CAP plates: ``metal_top`` (new UI) falls back to ``metal`` (legacy /
    # test-fixture compat). ``metal_bottom`` is required by the C and is
    # always passed by the UI / tests.
    metal_top = _opt("metal_top")
    metal_bottom = _opt("metal_bottom")
    # BALUN bridge / transition layer: ``metal_transition`` is the new UI
    # name; ``secondary_metal`` is the legacy alias still used by
    # tests/test_repl_layout_match.py.
    metal_transition = (
        _opt("metal_transition") or _opt("secondary_metal")
    )
    # Combine ORIENT (degrees, ASITIC convention) with PHASE (radians)
    # into the single ``phase`` argument the Python builder accepts.
    total_phase = phase + math.radians(orient)

    if wid_opt is not None and abs(wid_opt - length) > 1e-9:
        # The square-family Python builders currently take a single LEN
        # (square footprint). The C ASITIC supports rectangular LEN×WID
        # for SQ / SYMSQ / SQMM / TRANS but we haven't ported that path
        # yet — surface the constraint so users aren't silently misled.
        raise NotImplementedError(
            "Rectangular WID != LEN is not yet supported. "
            "Leave WID blank or set WID = LEN.",
        )
    if ilen_opt is not None and kind in (
        "square_spiral", "multi_metal_square",
    ):
        # SQ / SQMM in C support an inner-bound ILEN; the Python builder
        # doesn't yet — surface rather than silently ignore.
        raise NotImplementedError(
            "ILEN inner-bound is not yet supported for SQ / SQMM.",
        )
    if iwid_opt is not None:
        raise NotImplementedError("IWID is not yet supported.")
    if w2_opt is not None and w2_opt != width:
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
        gap_deg = _f("gap", 0.0)
        n_sides = sides if sides >= 3 else 16
        ring_radius = _f("radius", length)
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
        nx = max(1, _i("n_via_x", 1))
        ny = max(1, _i("n_via_y", nx))
        via_index = max(0, _i("via_index", 0))
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
    # Search the SRF over a generous bracket around the requested freq so
    # we surface it even when the user is well below / above resonance.
    sr_freq = _find_srf(sh, tech,
                        f_start=max(0.01, freq_ghz * 0.05),
                        f_stop=max(freq_ghz * 10.0, 50.0))
    return {
        "freq_ghz": freq_ghz,
        "L_nH": L,
        "R_dc_ohm": R_dc,
        "R_ac_ohm": R_ac,
        "Q": Q,
        "n_segments": n_segs,
        "total_length_um": total_len,
        "self_resonance_ghz": sr_freq,
    }


def _find_srf(sh, tech, *, f_start: float, f_stop: float) -> float | None:
    """Best-effort SRF lookup. Returns ``None`` if the search doesn't
    converge (the bracket may not contain a resonance, or the model may
    be unstable for this geometry).

    Calls ``reasitic.network.self_resonance``, which returns a
    ``SelfResonance`` dataclass with ``.freq_ghz`` and ``.converged``.
    """
    try:
        sr = self_resonance(sh, tech, f_low_ghz=f_start, f_high_ghz=f_stop)
        if not sr or not getattr(sr, "converged", False):
            return None
        f = getattr(sr, "freq_ghz", None)
        if f is None or not math.isfinite(f):
            return None
        return float(f)
    except Exception:
        return None


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


def analyze_pi2(freq_ghz: float) -> dict:
    """ASITIC ``Pi2`` — Pi-equivalent via EM analysis (no user ground).

    Implemented as :func:`reasitic.network.pi3_model` with
    ``ground_shape=None`` (Pi3's default — back-plane is grounded, no
    additional user-supplied ground spiral).
    """
    sh, tech = _require()
    r = pi3_model(sh, tech, freq_ghz, ground_shape=None)
    return {
        "freq_ghz": freq_ghz,
        "L_series_nH": r.L_series_nH,
        "R_series_ohm": r.R_series_ohm,
        "C_p1_to_gnd_fF": r.C_p1_to_gnd_fF,
        "C_p2_to_gnd_fF": r.C_p2_to_gnd_fF,
        "R_sub_p1_ohm": r.R_sub_p1_ohm,
        "R_sub_p2_ohm": r.R_sub_p2_ohm,
    }


def analyze_pix(freq_ghz: float) -> dict:
    """ASITIC ``PiX`` — extended Pi with substrate-loss conductance broken out."""
    sh, tech = _require()
    r = pix_model(sh, tech, freq_ghz)
    return {
        "freq_ghz": freq_ghz,
        "L_nH": r.L_nH,
        "R_series_ohm": r.R_series_ohm,
        "C_sub1_fF": r.C_sub1_fF,
        "C_sub2_fF": r.C_sub2_fF,
        "R_sub1_ohm": r.R_sub1_ohm,
        "R_sub2_ohm": r.R_sub2_ohm,
    }


def analyze_capacitance(freq_ghz: float) -> dict:
    """ASITIC ``Capacitance`` — port + substrate capacitance breakdown.

    The Pi-equivalent gives ``C_p1`` / ``C_p2`` (port-to-port and
    port-to-ground caps), and ``PiX`` adds the substrate-side
    ``C_sub1`` / ``C_sub2`` + the substrate loss resistors.
    """
    sh, tech = _require()
    pi = pi_model_at_freq(sh, tech, freq_ghz)
    px = pix_model(sh, tech, freq_ghz)
    return {
        "freq_ghz": freq_ghz,
        "C_p1_fF": pi.C_p1_fF,
        "C_p2_fF": pi.C_p2_fF,
        "g_p1": pi.g_p1,
        "g_p2": pi.g_p2,
        "C_sub1_fF": px.C_sub1_fF,
        "C_sub2_fF": px.C_sub2_fF,
        "R_sub1_ohm": px.R_sub1_ohm,
        "R_sub2_ohm": px.R_sub2_ohm,
    }


def analyze_resis_hf(freq_ghz: float) -> dict:
    """ASITIC ``ResisHF`` — high-frequency series resistance breakdown.

    Computes the DC resistance (sheet-resistance integral) and the AC
    resistance (skin-effect-aware) at ``freq_ghz``. The ratio + delta
    quantify how much the conductor's loss has grown vs. DC.
    """
    sh, tech = _require()
    R_dc = reasitic.compute_dc_resistance(sh, tech)
    R_ac = reasitic.compute_ac_resistance(sh, tech, freq_ghz)
    ratio = (R_ac / R_dc) if R_dc > 0 else float("nan")
    return {
        "freq_ghz": freq_ghz,
        "R_dc_ohm": R_dc,
        "R_ac_ohm": R_ac,
        "delta_R_ohm": R_ac - R_dc,
        "ratio": ratio,
    }


def analyze_shunt_resistance(freq_ghz: float) -> dict:
    """ASITIC ``ShuntR`` — equivalent shunt input resistance.

    Returns single-ended and differential ``R_p`` together with Q and the
    series L/R the parallel equivalent was derived from.
    """
    sh, tech = _require()
    se = shunt_resistance(sh, tech, freq_ghz, differential=False)
    diff = shunt_resistance(sh, tech, freq_ghz, differential=True)
    return {
        "freq_ghz": freq_ghz,
        "single_ended": {
            "R_p_ohm": se.R_p_ohm, "Q": se.Q,
            "L_nH": se.L_nH, "R_series_ohm": se.R_series_ohm,
        },
        "differential": {
            "R_p_ohm": diff.R_p_ohm, "Q": diff.Q,
            "L_nH": diff.L_nH, "R_series_ohm": diff.R_series_ohm,
        },
    }


def analyze_zin(freq_ghz: float) -> dict:
    """ASITIC ``Zin`` — complex input impedance, three configurations.

    * port-2 grounded (``Z11`` from the 2-port Z)
    * port-1 grounded (``Z22`` analogue — Z looking into port 2)
    * differential (one port driven against the other)

    Also reports the impedance with port-2 terminated in 50 Ω since the
    REPL's S-parameter sweep already assumes a 50 Ω reference.
    """
    sh, tech = _require()
    Y = spiral_y_at_freq(sh, tech, freq_ghz)
    z_p1 = z_2port_from_y(Y, port=1)
    z_p2 = z_2port_from_y(Y, port=2)
    z_diff = z_2port_from_y(Y, differential=True)
    z_50 = zin_terminated(sh, tech, freq_ghz)
    return {
        "freq_ghz": freq_ghz,
        "z_p1_grounded": {"real": z_p1.real, "imag": z_p1.imag},
        "z_p2_grounded": {"real": z_p2.real, "imag": z_p2.imag},
        "z_differential": {"real": z_diff.real, "imag": z_diff.imag},
        "z_50ohm_terminated": {"real": z_50.real, "imag": z_50.imag},
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
    # Self-resonance — best-effort lookup inside the swept band first.
    sr_freq = _find_srf(sh, tech, f_start=f1, f_stop=f2)
    return {
        "freqs_ghz": list(fs),
        "abs_S11": s11,
        "abs_S12": s12,
        "abs_S21": s21,
        "abs_S22": s22,
        "self_resonance_ghz": sr_freq,
    }


def analyze_lrq_sweep(f1: float, f2: float, step: float) -> dict:
    """L · R · Q vs frequency across a linear sweep.

    Returned arrays are aligned with ``freqs_ghz``. ``L_nH`` is the
    geometry-only self-inductance (constant across the sweep) and
    ``R_dc_ohm`` likewise; ``R_ac_ohm`` and ``Q`` use the same
    frequency-aware primitives as :func:`analyze_lrq`.
    """
    sh, tech = _require()
    if step <= 0:
        raise ValueError("Sweep step must be > 0")
    if f2 <= f1:
        raise ValueError("Sweep f2 must be > f1")
    fs = list(linear_freqs(f1, f2, step))

    L = reasitic.compute_self_inductance(sh)
    R_dc = reasitic.compute_dc_resistance(sh, tech)
    L_arr = [L for _ in fs]
    R_dc_arr = [R_dc for _ in fs]
    R_ac_arr = [reasitic.compute_ac_resistance(sh, tech, f) for f in fs]
    Q_arr = [reasitic.metal_only_q(sh, tech, f) for f in fs]
    # Search the SRF inside the swept band first; if not found, widen the
    # search so we can warn users whose sweep sits entirely below / above.
    sr_freq = _find_srf(sh, tech, f_start=f1, f_stop=f2)
    if sr_freq is None:
        sr_freq = _find_srf(sh, tech, f_start=max(0.01, f1 * 0.05),
                            f_stop=max(f2 * 10.0, 50.0))
    return {
        "freqs_ghz": fs,
        "L_nH": L_arr,
        "R_dc_ohm": R_dc_arr,
        "R_ac_ohm": R_ac_arr,
        "Q": Q_arr,
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


def export_gds_bytes() -> bytes:
    """Render the current shape as a GDS-II byte stream.

    The C-faithful canonical CIF polygons (computed by
    ``reasitic.geometry.layout_polygons``) are emitted via gdstk so the
    GDS file matches the canvas's metal/via layout exactly. Requires
    ``gdstk``; in the in-browser REPL this is loaded by ``worker.js`` at
    boot via Pyodide's package index — when the package isn't available
    the click handler reports a clear ImportError.
    """
    sh, tech = _require()
    from reasitic.exports.gds import write_gds
    return write_gds([sh], tech=tech, library_name="REASITIC")


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
