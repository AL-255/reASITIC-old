"""Minimal command-line interface for reASITIC.

A tiny REPL that loads a tech file, parses ASITIC-style ``NAME=VALUE``
arguments, and runs a subset of the original commands.

Currently supported:

* ``LOAD-TECH <path>`` (alias: ``T``) — load a ``.tek`` file
* Geometry builders:
  * ``W NAME=...:LEN=...:WID=...:METAL=...`` — wire
  * ``SQ NAME=...:LEN=...:W=...:S=...:N=...:METAL=...`` — square spiral
  * ``SP NAME=...:RADIUS=...:W=...:S=...:N=...:SIDES=...:METAL=...`` — polygon spiral
  * ``RING NAME=...:RADIUS=...:W=...:METAL=...:SIDES=...`` — ring
  * ``VIA NAME=...:VIA=<idx>:NX=...:NY=...:XORG=...:YORG=...`` — via
  * ``3DTRANS NAME=...:LEN=...:W=...:S=...:N=...:METAL_TOP=...:METAL_BOTTOM=...:VIA=...``
* Analysis commands:
  * ``IND <name>`` — self-inductance in nH
  * ``RES <name> [freq_ghz]`` — DC (and optional AC) resistance in Ω
  * ``Q <name> <freq_ghz>`` — metal-only quality factor
  * ``K <name1> <name2>`` — mutual inductance / coupling coefficient
  * ``2PORT <name> <f0> <f1> <step>`` — frequency sweep, prints each f
  * ``PI <name> <freq_ghz>`` — Pi-model L/R/C breakout
  * ``ZIN <name> <freq_ghz> [Z_re Z_im]`` — input impedance with load
  * ``SELFRES <name> <f_lo> <f_hi>`` — self-resonance frequency
  * ``CAP <name>`` — substrate shunt capacitance in F
  * ``METAREA <name>`` — metal area in μm²
  * ``LISTSEGS <name>`` — print all segments
  * ``LRMAT <name> [path]`` — partial-L matrix
  * ``SHUNTR <name> <freq_ghz> [S|D]`` — parallel resistance
  * ``PI3 <name> <freq_ghz> [<gnd_name>]`` — 3-port Pi model
  * ``PI4 <name> <freq_ghz> [<pad1> [<pad2>]]`` — 4-port Pi model
  * ``CALCTRANS <pri> <sec> <freq_ghz>`` — transformer analysis
* Export / persistence:
  * ``SAVE <path>`` / ``LOAD <path>`` — JSON session round-trip
  * ``CIFSAVE <path> [name [name ...]]`` — write CIF
  * ``TEKSAVE <path> [name [name ...]]`` — write Tek/gnuplot dump
  * ``SONNETSAVE <path> [name [name ...]]`` — write Sonnet ``.son``
  * ``S2PSAVE <name> <f0> <f1> <step> <path>`` — Touchstone export
* Optimisation:
  * ``OPTSQ <target_L_nH> <freq_ghz> [metal]`` — square-spiral OptSq
  * ``OPTPOLY <target_L_nH> <freq_ghz> [sides] [metal]`` — polygon-spiral
  * ``OPTAREA <target_L_nH> <freq_ghz> [metal]`` — minimise footprint
  * ``OPTSYMSQ <target_L_nH> <freq_ghz> [metal]`` — symmetric square
  * ``BATCHOPT [<targets_file>]`` — batch optimise across many points
  * ``SWEEP LMIN=...:LMAX=...:...:FREQ=...:[PATH=...]`` — Cartesian (L, W, S, N) sweep
  * ``SPICESAVE <name> <freq_ghz> <path>`` — emit SPICE Pi-model
* Misc:
  * ``GEOM <name>`` — geometry summary
  * ``LIST`` — list shapes
  * ``QUIT`` / ``EXIT``
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from reasitic import (
    Polygon,
    Shape,
    Tech,
    balun,
    capacitor,
    multi_metal_square,
    parse_tech_file,
    polygon_spiral,
    ring,
    square_spiral,
    symmetric_polygon,
    symmetric_square,
    transformer,
    transformer_3d,
    via,
    wire,
)
from reasitic.exports import (
    write_cif_file,
    write_sonnet,
    write_spice_subckt_file,
    write_tek_file,
)
from reasitic.inductance import (
    compute_mutual_inductance,
    compute_self_inductance,
    coupling_coefficient,
)
from reasitic.info import (
    format_lr_matrix,
    format_segments,
    metal_area,
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
    pix_model,
    self_resonance,
    shunt_resistance,
    zin_terminated,
)
from reasitic.optimise import (
    OptResult,
    batch_opt_square,
    optimise_area_square_spiral,
    optimise_polygon_spiral,
    optimise_square_spiral,
    optimise_symmetric_square,
    sweep_square_spiral,
    sweep_to_tsv,
)
from reasitic.persistence import load_session, load_viewport, save_session
from reasitic.quality import metal_only_q
from reasitic.resistance import compute_ac_resistance, compute_dc_resistance
from reasitic.substrate import shape_shunt_capacitance

_COMMAND_CATEGORIES = """\
Categories of commands (use HELP <command> for details):

  Create:    SQ, SP, RING, W, VIA, 3DTRANS, BALUN, CAPACITOR
  Edit:      MOVE, MOVETO, ROTATE, FLIPV, FLIPH, ERASE, RENAME, COPY
  Calc:      IND, RES, Q, K, CAP, METAREA, LISTSEGS, LRMAT
  Network:   PI, ZIN, SELFRES, SHUNTR, PI3, PI4, CALCTRANS, 2PORT,
             2PORTGND, 2PORTPAD, 3PORT, REPORT
  Optimise:  OPTSQ, OPTPOLY, OPTAREA, OPTSYMSQ, BATCHOPT, SWEEP
  Export:    SAVE, LOAD, CIFSAVE, TEKSAVE, SONNETSAVE, S2PSAVE, SPICESAVE
  Session:   VERBOSE, TIMER, SAVEMAT, LOG, RECORD, EXEC, CAT, VERSION,
             HELP, LIST, GEOM, QUIT
"""

_COMMAND_HELP = {
    "SQ": "SQ NAME=...:LEN=...:W=...:S=...:N=...:METAL=... — Square spiral",
    "SP": "SP NAME=...:RADIUS=...:W=...:S=...:N=...:SIDES=...:METAL=... — Polygon spiral",
    "RING": "RING NAME=...:RADIUS=...:W=...:METAL=...:SIDES=... — Single ring",
    "W": "W NAME=...:LEN=...:WID=...:METAL=... — Single wire",
    "VIA": "VIA NAME=...:VIA=<idx>:NX=...:NY=... — Via cluster",
    "3DTRANS": (
        "3DTRANS NAME=...:LEN=...:W=...:S=...:N=...:METAL_TOP=...:METAL_BOTTOM=..."
        " — 3D transformer"
    ),
    "IND": "IND <name> — Self-inductance in nH",
    "RES": "RES <name> [freq_ghz] — DC and optional AC resistance",
    "Q": "Q <name> <freq_ghz> — Metal-only quality factor",
    "K": "K <name1> <name2> — Mutual inductance and coupling coefficient",
    "CAP": "CAP <name> — Substrate shunt capacitance",
    "METAREA": "METAREA <name> — Metal area in μm²",
    "LISTSEGS": "LISTSEGS <name> — List all conductor segments",
    "LRMAT": "LRMAT <name> [path] — Partial-L matrix",
    "PI": "PI <name> <freq_ghz> — Pi-equivalent (L_s, R_s, C_p1, C_p2)",
    "PIX": "PIX <name> <freq_ghz> — Extended Pi with R-C substrate split",
    "PI3": "PI3 <name> <freq_ghz> [<gnd>] — 3-port Pi model",
    "PI4": "PI4 <name> <freq_ghz> [<pad1> [<pad2>]] — 4-port Pi model",
    "ZIN": "ZIN <name> <freq_ghz> [Z_re Z_im] — Input impedance with load",
    "SELFRES": "SELFRES <name> <f_lo> <f_hi> — Self-resonance frequency",
    "SHUNTR": "SHUNTR <name> <freq_ghz> [S|D] — Parallel-equivalent resistance",
    "CALCTRANS": "CALCTRANS <pri> <sec> <freq_ghz> — Transformer L, M, k, n analysis",
    "2PORT": "2PORT <name> <f0> <f1> <step> — Frequency sweep of S parameters",
    "2PORTGND": "2PORTGND <name> <gnd> <f0> <f1> <step> — Sweep with ground spiral",
    "2PORTPAD": "2PORTPAD <name> <pad1> <pad2> <f0> <f1> <step> — Sweep with bond pads",
    "2PORTTRANS": "2PORTTRANS <pri> <sec> <f0> <f1> <step> — Transformer 2-port sweep",
    "2PZIN": "2PZIN <name> <freq_ghz> [Z_re Z_im] — 2-port input impedance",
    "3PORT": "3PORT <name> <gnd> <freq_ghz> — 3-port reduction",
    "REPORT": "REPORT <name> <freq_ghz> [<freq_ghz> ...] — Multi-frequency design report",
    "OPTSQ": "OPTSQ <target_L_nH> <freq_ghz> [metal] — Square-spiral optimiser",
    "OPTPOLY": "OPTPOLY <target_L_nH> <freq_ghz> [sides] [metal] — Polygon-spiral optimiser",
    "OPTAREA": "OPTAREA <target_L_nH> <freq_ghz> [metal] — Area-minimising optimiser",
    "OPTSYMSQ": "OPTSYMSQ <target_L_nH> <freq_ghz> [metal] — Symmetric square optimiser",
    "BATCHOPT": "BATCHOPT [<targets_file>] — Batch optimiser",
    "SWEEP": "SWEEP LMIN=...:LMAX=...:LSTEP=...:WMIN=...:...:FREQ=... — Cartesian sweep",
    "MOVE": "MOVE <name> <dx> <dy> — Translate a shape",
    "MOVETO": "MOVETO <name> <x> <y> — Set shape origin",
    "ROTATE": "ROTATE <name> <angle_deg> — Rotate about origin",
    "FLIPV": "FLIPV <name> — Mirror across x-axis",
    "FLIPH": "FLIPH <name> — Mirror across y-axis",
    "ERASE": "ERASE <name> ... — Delete one or more shapes",
    "RENAME": "RENAME <old> <new> — Rename a shape",
    "COPY": "COPY <src> <dst> — Duplicate a shape",
    "HIDE": "HIDE <name> ... — Toggle visibility (no-op headless)",
    "BEFRIEND": "BEFRIEND <s1> <s2> — Mark two shapes as electrically connected",
    "UNFRIEND": "UNFRIEND <s1> <s2> — Remove a befriended pair",
    "INTERSECT": "INTERSECT <name> — Detect self-intersecting polygons",
    "TRANS": "TRANS NAME=...:LEN=...:W=...:S=...:N=...:METAL=...:METAL2=... — Planar transformer",
    "BALUN": "BALUN NAME=...:LEN=...:W=...:S=...:N=...:METAL=...:METAL2=... — Planar balun",
    "CAPACITOR": "CAPACITOR NAME=...:LEN=...:WID=...:METAL1=...:METAL2=... — MIM capacitor",
    "SYMSQ": "SYMSQ NAME=...:LEN=...:W=...:S=...:N=...:METAL=... — Symmetric square spiral",
    "SYMPOLY": (
        "SYMPOLY NAME=...:RAD=...:W=...:S=...:N=...:SIDES=...:METAL=..."
        " — Symmetric polygon spiral"
    ),
    "MMSQUARE": (
        "MMSQUARE NAME=...:LEN=...:W=...:S=...:N=...:METALS=m1,m2,m3"
        " — Multi-metal series spiral"
    ),
    "OPTSYMPOLY": (
        "OPTSYMPOLY <target_L_nH> <freq_ghz> [sides] [metal]"
        " — Symmetric polygon optimiser"
    ),
    "LDIV": "LDIV <name> <n_l> <n_w> <n_t> — Inductance with filament discretisation",
    "SPLIT": "SPLIT <name> <segment_index> <new_name> — Split a shape",
    "JOIN": "JOIN <s1> <s2> [<s3> ...] — Concatenate polygon lists into <s1>",
    "PHASE": "PHASE <name> <+1|-1> — Set current direction sign",
    "MODIFYTECHLAYER": "MODIFYTECHLAYER <rho|t|eps> <layer> <value> — Edit tech layer",
    "CELL": "CELL [max_l] [max_w] [max_t] — Cell-size constraints",
    "AUTOCELL": "AUTOCELL <alpha> <beta> — Adaptive cell size",
    "CHIP": "CHIP [chipx] [chipy] — Resize chip extents",
    "EDDY": "EDDY [on|off] — Toggle eddy-current calculation",
    "PAUSE": "PAUSE — No-op (for binary parity)",
    "INPUT": "INPUT <path> — Alias for EXEC",
    "SAVE": "SAVE <path> — Save the current session as JSON",
    "LOAD": "LOAD <path> — Load a JSON session",
    "CIFSAVE": "CIFSAVE <path> [<name> ...] — Write CIF layout",
    "TEKSAVE": "TEKSAVE <path> [<name> ...] — Write gnuplot/Tek dump",
    "SONNETSAVE": "SONNETSAVE <path> [<name> ...] — Write Sonnet .son",
    "S2PSAVE": "S2PSAVE <name> <f0> <f1> <step> <path> — Touchstone S2P export",
    "SPICESAVE": "SPICESAVE <name> <freq_ghz> <path> — SPICE Pi-model",
    "VERBOSE": "VERBOSE [true|false] — Toggle diagnostic output",
    "TIMER": "TIMER [true|false] — Toggle per-command timing",
    "SAVEMAT": "SAVEMAT [true|false] — Toggle matrix dumps",
    "LOG": "LOG [<filename>] — Start/stop a session log",
    "RECORD": "RECORD [<filename>] — Start/stop macro recording",
    "EXEC": "EXEC <path> — Execute commands from a script file",
    "CAT": "CAT <path> — Print contents of a file",
    "VERSION": "VERSION — Print build info",
    "HELP": "HELP [<command>] — Print this help",
    "GEOM": "GEOM <name> — Print geometry summary",
    "LIST": "LIST — List all built shapes",
    "QUIT": "QUIT / EXIT — Leave the REPL",
}


def _polygons_overlap(p_i: Polygon, p_j: Polygon) -> bool:
    """Cheap bounding-box test for polygon overlap (xy plane)."""
    if not p_i.vertices or not p_j.vertices:
        return False
    xs_i = [v.x for v in p_i.vertices]
    ys_i = [v.y for v in p_i.vertices]
    xs_j = [v.x for v in p_j.vertices]
    ys_j = [v.y for v in p_j.vertices]
    if min(xs_i) > max(xs_j) or max(xs_i) < min(xs_j):
        return False
    return not (min(ys_i) > max(ys_j) or max(ys_i) < min(ys_j))


def _frange(lo: float, hi: float, step: float) -> list[float]:
    """Inclusive linear range; matches `linear_freqs` semantics."""
    if step <= 0:
        raise ValueError("step must be > 0")
    if hi < lo:
        raise ValueError("hi must be >= lo")
    n = round((hi - lo) / step) + 1
    return [lo + i * step for i in range(n)]


def _parse_kv_args(arg_string: str) -> dict[str, str]:
    """Parse ``NAME=value:other=value`` style arguments.

    Both ``:`` and whitespace separate fields. Values are taken as
    strings; numeric coercion is the caller's responsibility.
    """
    out: dict[str, str] = {}
    parts = arg_string.replace(":", " ").split()
    for tok in parts:
        if "=" not in tok:
            continue
        k, _, v = tok.partition("=")
        out[k.strip().upper()] = v.strip()
    return out


class Repl:
    def __init__(self, tech: Tech | None = None) -> None:
        self.tech: Tech | None = tech
        self.shapes: dict[str, Shape] = {}
        # Toggles
        self.verbose: bool = False
        self.timer: bool = False
        self.save_mat: bool = False
        # Recording
        self.log_path: Path | None = None
        self.macro: list[str] | None = None
        # Shape relations
        self.friendships: set[frozenset[str]] = set()
        self.selected_shape: str | None = None
        # Viewport state (binary parity; mostly cosmetic in headless mode)
        self.viewport: dict[str, float] = {
            "scale": 1.0,
            "pan_x": 0.0,
            "pan_y": 0.0,
            "origin_x": 0.0,
            "origin_y": 0.0,
            "grid": 0.0,
            "snap": 0.0,
        }

    # Command handlers ----------------------------------------------------

    def cmd_load_tech(self, path: str) -> None:
        self.tech = parse_tech_file(path)
        print(f"Loaded tech file <{path}>")

    def cmd_wire(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = wire(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["WID"]),
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
            tech=self.tech,
        )
        self.shapes[sh.name] = sh

    def cmd_square(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = square_spiral(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_spiral(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = polygon_spiral(
            args["NAME"],
            radius=float(args["RADIUS"]) if "RADIUS" in args else float(args["LEN"]) * 0.5,
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            sides=int(float(args.get("SIDES", "8"))),
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
            tech=self.tech,
        )
        self.shapes[sh.name] = sh

    def cmd_ind(self, name: str) -> None:
        sh = self.shapes[name]
        L = compute_self_inductance(sh)
        print(f"L({name}) = {L:.6f} nH")

    def cmd_res(self, name: str, freq_ghz: float | None = None) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        R_dc = compute_dc_resistance(sh, self.tech)
        if freq_ghz is None:
            print(f"R_dc({name}) = {R_dc:.6f} Ohm")
            return
        R_ac = compute_ac_resistance(sh, self.tech, freq_ghz)
        print(f"R_dc({name}) = {R_dc:.6f} Ohm")
        print(f"R_ac({name}, {freq_ghz} GHz) = {R_ac:.6f} Ohm")

    def cmd_coupling(self, name_a: str, name_b: str) -> None:
        sh_a = self.shapes[name_a]
        sh_b = self.shapes[name_b]
        M = compute_mutual_inductance(sh_a, sh_b)
        k = coupling_coefficient(sh_a, sh_b)
        print(f"M({name_a}, {name_b}) = {M:.6f} nH")
        print(f"k({name_a}, {name_b}) = {k:.4f}")

    def cmd_q(self, name: str, freq_ghz: float) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        Q = metal_only_q(sh, self.tech, freq_ghz)
        L = compute_self_inductance(sh)
        R = compute_ac_resistance(sh, self.tech, freq_ghz)
        print(f"Q_metal({name}, {freq_ghz} GHz) = {Q:.3f}")
        print(f"  L = {L:.4f} nH, R_ac = {R:.4f} Ohm")

    def cmd_geom(self, name: str) -> None:
        sh = self.shapes[name]
        segs = sh.segments()
        total_length = sum(s.length for s in segs)
        xmin, ymin, xmax, ymax = sh.bounding_box()
        print(f"Shape <{sh.name}> ({len(sh.polygons)} polygons, {len(segs)} segments)")
        print(f"  width = {sh.width:.2f}, spacing = {sh.spacing:.2f}, turns = {sh.turns:.2f}")
        print(f"  total length = {total_length:.2f} um")
        print(f"  bounding box = ({xmin:.2f}, {ymin:.2f}) -- ({xmax:.2f}, {ymax:.2f})")

    def cmd_list(self) -> None:
        if not self.shapes:
            print("(no shapes built)")
            return
        for name, sh in self.shapes.items():
            print(f"  {name}: {len(sh.polygons)} polygons, {len(sh.segments())} segments")

    # Tech-edit & cell-size commands -------------------------------------

    def cmd_modify_tech_layer(
        self, prop: str, layer_index: int, value: float
    ) -> None:
        """MODIFYTECHLAYER <rho|t|eps> <layer> <value> (case 222)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        if not (0 <= layer_index < len(self.tech.layers)):
            print(f"Layer {layer_index} out of range")
            return
        layer = self.tech.layers[layer_index]
        prop = prop.lower()
        if prop == "rho":
            layer.rho = value
        elif prop == "t":
            layer.t = value
        elif prop == "eps":
            layer.eps = value
        else:
            print(f"Unknown property {prop!r}; use rho|t|eps")
            return
        print(f"Set layer {layer_index}.{prop} = {value}")

    def cmd_cell(self, *, max_l: float = 0.0, max_w: float = 0.0,
                 max_t: float = 0.0) -> None:
        """CELL [<max_length> <max_width> <max_thickness>] (case 207).

        Sets per-direction cell-size limits used by the filament
        discretiser. We store them on the Repl state for later use.
        """
        if not hasattr(self, "cell_constraints"):
            self.cell_constraints: dict[str, float] = {}
        for k, v in [("max_l", max_l), ("max_w", max_w), ("max_t", max_t)]:
            if v > 0:
                self.cell_constraints[k] = v
        print(f"Cell constraints: {self.cell_constraints}")

    def cmd_auto_cell(self, alpha: float = 0.5, beta: float = 1.0) -> None:
        """AUTOCELL <alpha> <beta> (case 212).

        Records two scalars used by the filament discretiser to
        adapt cell size automatically (the binary uses these to
        scale (alpha)·skin_depth and (beta)·width for cell choice).
        """
        if not hasattr(self, "auto_cell_alpha"):
            self.auto_cell_alpha = alpha
            self.auto_cell_beta = beta
        else:
            self.auto_cell_alpha = alpha
            self.auto_cell_beta = beta
        print(f"AutoCell: alpha={alpha:g}, beta={beta:g}")

    def cmd_chip(self, x: float | None = None, y: float | None = None) -> None:
        """CHIP [chipx] [chipy] (case 217) — resize the chip extents."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        if x is not None:
            self.tech.chip.chipx = x
        if y is not None:
            self.tech.chip.chipy = y
        print(
            f"Chip: chipx={self.tech.chip.chipx}, chipy={self.tech.chip.chipy}"
        )

    def cmd_eddy(self, on: bool | None = None) -> None:
        """CALCEDDY [on|off] (case 221)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        if on is not None:
            self.tech.chip.eddy = on
        print(f"Eddy: {'on' if self.tech.chip.eddy else 'off'}")

    # View commands (no-op headless) -------------------------------------

    def cmd_view_set(self, key: str, value: float) -> None:
        """Set a viewport-state field; reported on next LIST."""
        self.viewport[key] = value
        if self.verbose:
            print(f"viewport.{key} = {value}")

    def cmd_no_op_view(self, label: str) -> None:
        """No-op stub for view-related commands (SCALE, PAN, ZOOM, BB,
        REFRESH, ORIGIN, GRID, SNAP, RULER, SHOWPHASE, etc.). The
        binary uses these to update the X11 window; we silently accept
        them so scripts that mix view and analysis commands run
        without errors."""
        if self.verbose:
            print(f"({label} — no-op headless)")

    # Pause / Input session controls -------------------------------------

    def cmd_pause(self) -> None:
        """PAUSE (case 216) — wait for keypress (no-op headless)."""
        if self.verbose:
            print("(PAUSE — no-op headless)")

    def cmd_input(self, path: str | None = None) -> None:
        """INPUT [<filename>] (case 215) — redirect stdin from a file.

        We just exec the file like ``EXEC`` but accept the alias for
        binary compatibility.
        """
        if path:
            self.cmd_exec_script(path)

    # Help / Version -----------------------------------------------------

    def cmd_version(self) -> None:
        from reasitic import __version__
        print(f"reASITIC version {__version__}")
        print("Reverse-engineered Python implementation of ASITIC")

    def cmd_help(self, topic: str | None = None) -> None:
        """HELP [topic] — print command help."""
        if topic:
            self._help_for_command(topic.upper())
        else:
            print(_COMMAND_CATEGORIES)

    def _help_for_command(self, name: str) -> None:
        info = _COMMAND_HELP.get(name)
        if info is None:
            print(f"No help for command: {name!r}")
            return
        print(info)

    # Toggles & session controls ------------------------------------------

    def cmd_verbose(self, value: str | None = None) -> None:
        """VERBOSE [true|false] — toggle diagnostic output."""
        if value is not None:
            self.verbose = value.lower() in ("1", "true", "yes", "on")
        else:
            self.verbose = not self.verbose
        print(f"Verbose: {'on' if self.verbose else 'off'}")

    def cmd_timer(self, value: str | None = None) -> None:
        """TIMER [true|false] — toggle per-command timing."""
        if value is not None:
            self.timer = value.lower() in ("1", "true", "yes", "on")
        else:
            self.timer = not self.timer
        print(f"Timer: {'on' if self.timer else 'off'}")

    def cmd_savemat(self, value: str | None = None) -> None:
        """SAVEMAT [true|false] — toggle dumping the L matrix to disk."""
        if value is not None:
            self.save_mat = value.lower() in ("1", "true", "yes", "on")
        else:
            self.save_mat = not self.save_mat
        print(f"SaveMat: {'on' if self.save_mat else 'off'}")

    def cmd_log(self, path: str | None = None) -> None:
        """LOG [<filename>] — start/stop logging input + output to a file."""
        if path:
            self.log_path = Path(path)
            self.log_path.write_text(
                f"# reASITIC LOG started at {Path(__file__).name}\n"
            )
            print(f"Logging to <{path}>")
        else:
            if self.log_path:
                print(f"Stopped logging to <{self.log_path}>")
                self.log_path = None
            else:
                print("Logging is off")

    def cmd_record(self, path: str | None = None) -> None:
        """RECORD [<filename>] — start/stop a macro recording."""
        if self.macro is None:
            self.macro = []
            print("Recording macro — call RECORD without args to stop.")
        else:
            text = "\n".join(self.macro)
            if path:
                Path(path).write_text(text + "\n")
                print(f"Saved macro to <{path}>")
            else:
                print(text)
            self.macro = None

    def cmd_exec_script(self, path: str) -> None:
        """EXEC <path> — execute commands from a script file."""
        for line in Path(path).read_text().splitlines():
            line = line.strip()
            if not line or line.startswith("#"):
                continue
            print(f"reASITIC> {line}")
            if not self.execute(line):
                return

    def cmd_cat(self, path: str) -> None:
        """CAT <path> — print contents of a file."""
        try:
            print(Path(path).read_text(), end="")
        except OSError as e:
            print(f"Error: {e}")

    # Shape-management commands --------------------------------------------

    def cmd_erase(self, names: list[str]) -> None:
        """ERASE <name> ... — delete one or more shapes."""
        for n in names:
            if n in self.shapes:
                del self.shapes[n]
                print(f"Erased <{n}>")
            else:
                print(f"No shape named <{n}>")

    def cmd_rename(self, old: str, new: str) -> None:
        """RENAME <old> <new>."""
        if old not in self.shapes:
            print(f"No shape named <{old}>")
            return
        if new in self.shapes:
            print(f"Shape <{new}> already exists; refusing to overwrite")
            return
        sh = self.shapes.pop(old)
        # Update the name on the dataclass too
        sh.name = new
        self.shapes[new] = sh
        print(f"Renamed <{old}> → <{new}>")

    def cmd_copy(self, src: str, dst: str) -> None:
        """COPY <src> <dst>."""
        if src not in self.shapes:
            print(f"No shape named <{src}>")
            return
        from copy import deepcopy
        cp = deepcopy(self.shapes[src])
        cp.name = dst
        self.shapes[dst] = cp
        print(f"Copied <{src}> → <{dst}>")

    def cmd_split(self, name: str, index: int, new_name: str) -> None:
        """SPLIT <name> <segment_index> <new_name>.

        Splits a shape's polygon list into two halves at the given
        polygon index, keeping the head as ``<name>`` and creating a
        new shape ``<new_name>`` with the tail polygons.
        """
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        sh = self.shapes[name]
        if index < 0 or index > len(sh.polygons):
            print(f"Index {index} out of range [0, {len(sh.polygons)}]")
            return
        head = sh.polygons[:index]
        tail = sh.polygons[index:]
        if not tail:
            print("Tail is empty; nothing to split")
            return
        sh.polygons = head
        from copy import deepcopy
        new_sh = deepcopy(sh)
        new_sh.name = new_name
        new_sh.polygons = tail
        self.shapes[new_name] = new_sh
        print(f"Split <{name}> at {index} → <{name}> + <{new_name}>")

    def cmd_join(self, names: list[str]) -> None:
        """JOIN <s1> <s2> [<s3> ...] — concatenate polygon lists.

        The result is stored back into ``<s1>``; the others are
        deleted from the shapes dict.
        """
        if len(names) < 2:
            print("Usage: JOIN <s1> <s2> [<s3> ...]")
            return
        target = names[0]
        if target not in self.shapes:
            print(f"No shape named <{target}>")
            return
        for n in names[1:]:
            if n not in self.shapes:
                print(f"No shape named <{n}>; skipping")
                continue
            self.shapes[target].polygons.extend(self.shapes[n].polygons)
            del self.shapes[n]
        print(f"Joined → <{target}> ({len(names)} input shapes)")

    def cmd_movex(self, name: str, dx: float) -> None:
        """MOVEX <name> <dx> — translate in x only."""
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        self.shapes[name] = self.shapes[name].translate(dx, 0.0)

    def cmd_movey(self, name: str, dy: float) -> None:
        """MOVEY <name> <dy> — translate in y only."""
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        self.shapes[name] = self.shapes[name].translate(0.0, dy)

    def cmd_flip(self, name: str) -> None:
        """FLIP <name> — reverse current direction (case 414).

        Reverses polygon order and vertex order within each polygon
        (so the spiral traces in the opposite direction).
        """
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        sh = self.shapes[name]
        sh.polygons = list(reversed(sh.polygons))
        for p in sh.polygons:
            p.vertices = list(reversed(p.vertices))
        sh.orientation = -1 if sh.orientation == 0 else -sh.orientation

    def cmd_joinshunt(self, names: list[str]) -> None:
        """JOINSHUNT <s1> <s2> [...] — mark shapes as parallel-friends.

        Mirrors case 421. Adds friendship pairs so analysis paths
        can treat the shapes as a parallel (shunt) combination.
        """
        if len(names) < 2:
            print("Usage: JOINSHUNT <s1> <s2> [<s3> ...]")
            return
        for n in names[1:]:
            if n in self.shapes and names[0] in self.shapes:
                self.friendships.add(frozenset({names[0], n}))
        print(f"JoinShunt: marked {len(names)} shapes as parallel-friends")

    def cmd_select(self, name: str | None = None) -> None:
        """SELECT [<name>] — highlight a shape (case 422).

        Headless mode records the selection but doesn't draw it.
        """
        self.selected_shape = name
        if name:
            print(f"Selected: <{name}>")
        else:
            print("Selection cleared")

    def cmd_unselect(self) -> None:
        """UNSELECT (case 423) — clear the current selection."""
        self.selected_shape = None
        print("Selection cleared")

    def cmd_sptowire(self, name: str) -> None:
        """SPTOWIRE <name> — break a spiral into N single-polygon wires.

        Mirrors case 424. Useful for analysing each turn of a spiral
        separately.
        """
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        sh = self.shapes[name]
        from copy import deepcopy
        for i, poly in enumerate(sh.polygons):
            new_name = f"{name}_{i}"
            new_sh = deepcopy(sh)
            new_sh.name = new_name
            new_sh.polygons = [poly]
            self.shapes[new_name] = new_sh
        del self.shapes[name]
        print(f"SpToWire: split <{name}> into {len(sh.polygons)} wires")

    def cmd_phase(self, name: str, sign: int) -> None:
        """PHASE <name> <+1|-1> — flip current direction (no-op
        in our simple geometry model; we record the sign on the
        shape's ``orientation`` field)."""
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        if sign not in (1, -1):
            print("Phase sign must be +1 or -1")
            return
        self.shapes[name].orientation = sign
        print(f"<{name}> orientation = {sign:+d}")

    def cmd_befriend(self, name1: str, name2: str) -> None:
        """BEFRIEND <s1> <s2> — mark two shapes as electrically
        connected for analysis (case 417).

        We track the friendship pairs in a set on the REPL state;
        analysis paths can use this to merge segment lists when
        computing inductance / resistance.
        """
        if name1 not in self.shapes or name2 not in self.shapes:
            print("One of the shapes doesn't exist")
            return
        self.friendships.add(frozenset({name1, name2}))
        print(f"Befriended <{name1}> ↔ <{name2}>")

    def cmd_unfriend(self, name1: str, name2: str) -> None:
        """UNFRIEND <s1> <s2> — remove the friendship link (case 418)."""
        key = frozenset({name1, name2})
        if key in self.friendships:
            self.friendships.remove(key)
            print(f"Unfriended <{name1}> ↔ <{name2}>")
        else:
            print(f"<{name1}> and <{name2}> were not befriended")

    def cmd_intersect(self, name: str) -> None:
        """INTERSECT/FINDI <name> — check if a shape's polygons
        self-intersect (case 419)."""
        if name not in self.shapes:
            print(f"No shape named <{name}>")
            return
        sh = self.shapes[name]
        # Pairwise polygon-edge intersection check (axis-aligned only)
        intersections = 0
        for i, p_i in enumerate(sh.polygons):
            for p_j in sh.polygons[i + 1:]:
                if _polygons_overlap(p_i, p_j):
                    intersections += 1
        if intersections == 0:
            print(f"<{name}> has no detected self-intersections")
        else:
            print(f"<{name}> has {intersections} pair(s) of intersecting polygons")

    def cmd_hide(self, names: list[str]) -> None:
        """HIDE <name> ... — toggle visibility (no-op storage flag).

        We don't model the X11 visibility state; HIDE is a no-op
        included for command-name parity with the binary.
        """
        for n in names:
            if n in self.shapes:
                print(f"(visibility toggle on <{n}> — no-op in headless mode)")

    # New geometry builders ----------------------------------------------

    def cmd_ring(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = ring(
            args["NAME"],
            radius=float(args.get("RADIUS", args.get("RAD", "0"))),
            width=float(args["W"]),
            gap=float(args.get("GAP", "0")),
            sides=int(float(args.get("SIDES", "32"))),
            tech=self.tech,
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_via(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = via(
            args["NAME"],
            tech=self.tech,
            via_index=int(float(args.get("VIA", "0"))),
            nx=int(float(args.get("NX", "1"))),
            ny=int(float(args.get("NY", "1"))),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    # Analysis -----------------------------------------------------------

    def cmd_2port_gnd(
        self, name: str, gnd_name: str, f0: float, f1: float, step: float
    ) -> None:
        """2-port sweep with explicit ground spiral coupling included
        in the series leg (mirrors case 529, ``2PortGnd``)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        gnd = self.shapes[gnd_name]
        # The ground-coupling reduces the effective series L by M.
        # We construct an "effective" series path by translating the
        # spiral and computing M, then printing the adjusted Pi at
        # each frequency.
        from reasitic.inductance import compute_mutual_inductance
        M = compute_mutual_inductance(sh, gnd)
        fs = linear_freqs(f0, f1, step)
        sweep = two_port_sweep(sh, self.tech, fs)
        print(f"# 2PortGnd <{name}, gnd={gnd_name}>: M={M:.4f} nH")
        print(f"# {'f_GHz':>7} {'L_eff_nH':>10} {'Q':>7}")
        from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI

        for f, pi in zip(fs, sweep.pi, strict=True):
            omega = TWO_PI * f * GHZ_TO_HZ
            L_eff = pi.Z_s.imag / omega / NH_TO_H - M
            R = pi.Z_s.real
            Q = omega * L_eff * NH_TO_H / max(R, 1e-30)
            print(f"  {f:7.3f} {L_eff:10.4f} {Q:7.2f}")

    def cmd_2port_pad(
        self,
        name: str,
        pad1_name: str,
        pad2_name: str,
        f0: float,
        f1: float,
        step: float,
    ) -> None:
        """2-port sweep with pad capacitors at each port (case 530)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        pad1 = self.shapes[pad1_name]
        pad2 = self.shapes[pad2_name]
        from reasitic.network.analysis import pi4_model

        fs = linear_freqs(f0, f1, step)
        print(f"# 2PortPad <{name}, pads={pad1_name},{pad2_name}>")
        print(f"# {'f_GHz':>7} {'L_nH':>8} {'C_pad1_fF':>10} {'C_pad2_fF':>10}")
        for f in fs:
            res = pi4_model(sh, self.tech, f, pad1=pad1, pad2=pad2)
            print(
                f"  {f:7.3f} {res.L_series_nH:8.4f}"
                f" {res.C_pad1_fF:10.3f} {res.C_pad2_fF:10.3f}"
            )

    def cmd_3port(
        self, name: str, gnd_name: str, freq_ghz: float
    ) -> None:
        """3-port reduction to 2-port Y at one frequency (case 536)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        import numpy as np

        from reasitic.network import (
            reduce_3port_z_to_2port_y,
            spiral_y_at_freq,
            y_to_z,
        )

        sh = self.shapes[name]
        gnd = self.shapes[gnd_name]
        # Build the 3-port Z for (signal pos, signal neg, ground)
        Y_sig = spiral_y_at_freq(sh, self.tech, freq_ghz)
        Y_gnd = spiral_y_at_freq(gnd, self.tech, freq_ghz)
        with np.errstate(divide="ignore", invalid="ignore"):
            Z_sig = y_to_z(Y_sig)
            Z_gnd = y_to_z(Y_gnd)
        # Build a 3x3 Z by stacking diagonal blocks (ports 0,1 are
        # signal, port 2 is ground)
        Z3 = np.zeros((3, 3), dtype=complex)
        Z3[:2, :2] = Z_sig
        Z3[2, 2] = Z_gnd[0, 0]
        Y2 = reduce_3port_z_to_2port_y(Z3)
        print(f"3Port <{name}, gnd={gnd_name}> at {freq_ghz:g} GHz:")
        print("  Y reduced (port-3 grounded):")
        for i in range(2):
            for j in range(2):
                print(
                    f"    Y[{i},{j}] = {Y2[i, j].real:.4e}"
                    f" + {Y2[i, j].imag:.4e}j S"
                )

    def cmd_2port_trans(
        self,
        pri_name: str,
        sec_name: str,
        f0: float,
        f1: float,
        step: float,
    ) -> None:
        """2-port transformer sweep (case 524, 2PortTrans).

        Reports L_pri, L_sec, M, k, n at every frequency point.
        """
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.network.analysis import calc_transformer
        pri = self.shapes[pri_name]
        sec = self.shapes[sec_name]
        fs = linear_freqs(f0, f1, step)
        print(f"# 2PortTrans <{pri_name}, {sec_name}>")
        print(
            f"# {'f_GHz':>7} {'L_pri':>8} {'L_sec':>8} {'M':>8}"
            f" {'k':>8} {'Q_pri':>7}"
        )
        for f in fs:
            r = calc_transformer(pri, sec, self.tech, f)
            print(
                f"  {f:7.3f} {r.L_pri_nH:8.4f} {r.L_sec_nH:8.4f}"
                f" {r.M_nH:8.4f} {r.k:8.4f} {r.Q_pri:7.2f}"
            )

    def cmd_2pzin(
        self,
        name: str,
        freq_ghz: float,
        z_load_re: float = 50.0,
        z_load_im: float = 0.0,
    ) -> None:
        """2-port input impedance with arbitrary load (case 537)."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.network.analysis import zin_terminated
        sh = self.shapes[name]
        z_load = complex(z_load_re, z_load_im)
        try:
            z = zin_terminated(sh, self.tech, freq_ghz, z_load_ohm=z_load)
        except ValueError as e:
            print(f"2PZin({name}): {e}")
            return
        # Also report in admittance form
        y = 1.0 / z if z != 0 else complex("nan")
        print(
            f"2PZin({name}, {freq_ghz:g} GHz, ZL={z_load}) = "
            f"{z.real:.3f}{z.imag:+.3f}j Ohm "
            f"({y.real:.4e}{y.imag:+.4e}j S)"
        )

    def cmd_2port(self, name: str, f0: float, f1: float, step: float) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        fs = linear_freqs(f0, f1, step)
        sweep = two_port_sweep(sh, self.tech, fs)
        print(f"# 2Port {name}  ({len(fs)} freq points)")
        print(f"# {'f_GHz':>7} {'|S11|':>10} {'∠S11':>8} {'|S21|':>10} {'∠S21':>8}")
        import math
        for f, S in zip(fs, sweep.S, strict=True):
            mag11 = abs(S[0, 0])
            ang11 = math.degrees(math.atan2(S[0, 0].imag, S[0, 0].real))
            mag21 = abs(S[1, 0])
            ang21 = math.degrees(math.atan2(S[1, 0].imag, S[1, 0].real))
            print(f"  {f:7.3f} {mag11:10.6f} {ang11:8.2f} {mag21:10.6f} {ang21:8.2f}")

    def cmd_cap(self, name: str) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        C = shape_shunt_capacitance(sh, self.tech)
        print(f"C_shunt({name}) = {C * 1e15:.3f} fF")

    # Persistence --------------------------------------------------------

    def cmd_save(self, path: str) -> None:
        save_session(
            path,
            tech=self.tech,
            shapes=self.shapes,
            viewport=self.viewport,
        )
        print(f"Saved {len(self.shapes)} shapes to <{path}>")

    def cmd_load(self, path: str) -> None:
        tech, shapes = load_session(path)
        if tech is not None:
            self.tech = tech
        self.shapes.update(shapes)
        vp = load_viewport(path)
        if vp:
            self.viewport.update(vp)
        print(f"Loaded {len(shapes)} shapes from <{path}>")

    # Exports ------------------------------------------------------------

    def _select_shapes(self, names: list[str]) -> list[Shape]:
        if not names:
            return list(self.shapes.values())
        return [self.shapes[n] for n in names]

    def cmd_cifsave(self, path: str, names: list[str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        shapes = self._select_shapes(names)
        write_cif_file(path, shapes, self.tech)
        print(f"Wrote CIF to <{path}> ({len(shapes)} shapes)")

    def cmd_teksave(self, path: str, names: list[str]) -> None:
        shapes = self._select_shapes(names)
        write_tek_file(path, shapes)
        print(f"Wrote Tek/gnuplot to <{path}> ({len(shapes)} shapes)")

    def cmd_sonnetsave(self, path: str, names: list[str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        shapes = self._select_shapes(names)
        Path(path).write_text(write_sonnet(shapes, self.tech))
        print(f"Wrote Sonnet to <{path}> ({len(shapes)} shapes)")

    def cmd_spicesave(
        self, name: str, freq_ghz: float, path: str
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        write_spice_subckt_file(path, sh, self.tech, freq_ghz)
        print(f"Wrote SPICE sub-circuit to <{path}>")

    def cmd_s2psave(
        self, name: str, f0: float, f1: float, step: float, path: str
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        fs = linear_freqs(f0, f1, step)
        sweep = two_port_sweep(sh, self.tech, fs)
        write_touchstone_file(path, sweep.to_touchstone_points(param="S"))
        print(f"Wrote Touchstone S2P to <{path}> ({len(fs)} freq points)")

    # Shape transforms ---------------------------------------------------

    def cmd_move(self, name: str, dx: float, dy: float) -> None:
        sh = self.shapes[name]
        self.shapes[name] = sh.translate(dx, dy)

    def cmd_moveto(self, name: str, x: float, y: float) -> None:
        sh = self.shapes[name]
        self.shapes[name] = sh.translate(x - sh.x_origin, y - sh.y_origin)

    def cmd_flipv(self, name: str) -> None:
        self.shapes[name] = self.shapes[name].flip_vertical()

    def cmd_fliph(self, name: str) -> None:
        self.shapes[name] = self.shapes[name].flip_horizontal()

    def cmd_rotate(self, name: str, angle_deg: float) -> None:
        import math as _m
        self.shapes[name] = self.shapes[name].rotate_xy(_m.radians(angle_deg))

    def cmd_report(self, name: str, freqs: list[float]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.report import design_report
        sh = self.shapes[name]
        rpt = design_report(sh, self.tech, freqs_ghz=freqs)
        print(rpt.format_text(), end="")

    def cmd_trans(self, args: dict[str, str]) -> None:
        """TRANS: planar two-coil transformer."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = transformer(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metal_primary=args.get("METAL", 0),
            metal_secondary=args.get("METAL2"),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_balun(self, args: dict[str, str]) -> None:
        """BALUN: stacked counter-wound spirals."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = balun(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metal=args.get("METAL", 0),
            metal2=args.get("METAL2"),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_capacitor(self, args: dict[str, str]) -> None:
        """CAPACITOR: MIM capacitor."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = capacitor(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args.get("WID", args["LEN"])),
            metal_top=args["METAL1"],
            metal_bottom=args["METAL2"],
            tech=self.tech,
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_symsq(self, args: dict[str, str]) -> None:
        """SYMSQ: symmetric centre-tapped square spiral."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = symmetric_square(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_sympoly(self, args: dict[str, str]) -> None:
        """SYMPOLY: symmetric centre-tapped polygon spiral."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = symmetric_polygon(
            args["NAME"],
            radius=float(args.get("RAD", args.get("RADIUS", "0"))),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            sides=int(float(args.get("SIDES", "8"))),
            tech=self.tech,
            metal=args.get("METAL", 0),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_mmsquare(self, args: dict[str, str]) -> None:
        """MMSQUARE: multi-metal series square inductor."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        # METALS is a comma-separated list, e.g. METALS=m1,m2,m3
        metals_str = args.get("METALS", args.get("METAL", "0"))
        metals: list[int | str] = [m.strip() for m in metals_str.split(",")]
        sh = multi_metal_square(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metals=metals,
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    def cmd_3dtrans(self, args: dict[str, str]) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = transformer_3d(
            args["NAME"],
            length=float(args["LEN"]),
            width=float(args["W"]),
            spacing=float(args["S"]),
            turns=float(args["N"]),
            tech=self.tech,
            metal_top=args.get("METAL_TOP", args.get("METAL", 0)),
            metal_bottom=args.get("METAL_BOTTOM", args.get("METAL2", 0)),
            via_index=int(float(args.get("VIA", "0"))),
            x_origin=float(args.get("XORG", "0")),
            y_origin=float(args.get("YORG", "0")),
        )
        self.shapes[sh.name] = sh

    # Pi / Zin / SelfRes / ShuntR / Pi3 / Pi4 / CalcTrans ----------------

    def cmd_pi2(
        self, name: str, freq_ghz: float, gnd_name: str | None = None
    ) -> None:
        """PI2 <name> <freq> [<gnd>] — same as PI3 but with the
        binary's case-515 numbering. Aliased here for parity."""
        self.cmd_pi3(name, freq_ghz, gnd_name)

    def cmd_2port_x(
        self, name: str, f0: float, f1: float, step: float
    ) -> None:
        """2PORTX <name> <f0> <f1> <step> — sweep using the extended
        PiX model (case 539). Reports R_sub / C_sub at each f."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.network.analysis import pix_model
        sh = self.shapes[name]
        fs = linear_freqs(f0, f1, step)
        print(f"# 2PortX <{name}>")
        print(
            f"# {'f_GHz':>7} {'L_nH':>8} {'R_s':>8}"
            f" {'R_sub1':>8} {'C_sub1_fF':>10}"
        )
        for f in fs:
            r = pix_model(sh, self.tech, f)
            print(
                f"  {f:7.3f} {r.L_nH:8.4f} {r.R_series_ohm:8.4f}"
                f" {r.R_sub1_ohm:8.3f} {r.C_sub1_fF:10.3f}"
            )

    def cmd_resishf(self, name: str, freq_ghz: float) -> None:
        """RESISHF <name> <freq_ghz> (case 527).

        High-frequency resistance: same as the AC branch of RES.
        Aliased for binary parity.
        """
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.resistance import compute_ac_resistance
        sh = self.shapes[name]
        R_ac = compute_ac_resistance(sh, self.tech, freq_ghz)
        print(f"R_ac({name}, {freq_ghz} GHz) = {R_ac:.6f} Ohm")

    def cmd_ccell(self, max_l: float = 0.0, max_w: float = 0.0) -> None:
        """CCELL [max_l] [max_w] (case 211) — centred-cell constraints.

        Unlike CELL, CCELL doesn't take a thickness; the binary uses
        it for 2D-only filament discretisation.
        """
        if not hasattr(self, "cell_constraints"):
            self.cell_constraints = {}
        if max_l > 0:
            self.cell_constraints["max_l"] = max_l
        if max_w > 0:
            self.cell_constraints["max_w"] = max_w
        print(f"CCell constraints: {self.cell_constraints}")

    def cmd_setmaxnw(self, value: int = 0) -> None:
        """SETMAXNW [value] (case 218) — set the max sub-filament count."""
        if value > 0:
            self.max_nw = value
        print(f"MaxNW: {getattr(self, 'max_nw', 'unset')}")

    def cmd_sweep_mm(self, args: dict[str, str]) -> None:
        """SWEEPMM (case 715) — multi-metal sweep variant of SWEEP.

        We treat it as an alias for SWEEP since our SWEEP already
        accepts a METALS list.
        """
        self.cmd_sweep(args)

    def cmd_pix(self, name: str, freq_ghz: float) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        r = pix_model(sh, self.tech, freq_ghz)
        print(f"PiX-model for <{name}> at {freq_ghz:g} GHz:")
        print(f"  L_series = {r.L_nH:.4f} nH")
        print(f"  R_series = {r.R_series_ohm:.4f} Ohm")
        print(f"  Port 1: R_sub = {r.R_sub1_ohm:.3f} Ω, C_sub = {r.C_sub1_fF:.3f} fF")
        print(f"  Port 2: R_sub = {r.R_sub2_ohm:.3f} Ω, C_sub = {r.C_sub2_fF:.3f} fF")

    def cmd_pi(self, name: str, freq_ghz: float) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        pi = pi_model_at_freq(sh, self.tech, freq_ghz)
        print(f"Pi-model for <{name}> at {freq_ghz:g} GHz:")
        print(f"  L_series = {pi.L_nH:.4f} nH")
        print(f"  R_series = {pi.R_series:.4f} Ohm")
        print(f"  C_p1 = {pi.C_p1_fF:.3f} fF, g_p1 = {pi.g_p1:.3e} S")
        print(f"  C_p2 = {pi.C_p2_fF:.3f} fF, g_p2 = {pi.g_p2:.3e} S")

    def cmd_zin(
        self, name: str, freq_ghz: float, *, z_load: complex = 50.0 + 0j
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        try:
            z = zin_terminated(sh, self.tech, freq_ghz, z_load_ohm=z_load)
        except ValueError as e:
            print(f"Zin({name}): {e}")
            return
        print(
            f"Zin({name}, {freq_ghz:g} GHz, ZL={z_load}) "
            f"= {z.real:.3f}{z.imag:+.3f}j Ohm"
        )

    def cmd_shuntr(
        self, name: str, freq_ghz: float, mode: str = "S"
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        diff = mode.upper() == "D"
        r = shunt_resistance(sh, self.tech, freq_ghz, differential=diff)
        print(f"ShuntR({name}, {freq_ghz:g} GHz, {mode}-mode):")
        print(f"  R_p = {r.R_p_ohm:.3f} Ohm, Q = {r.Q:.3f}")
        print(f"  L = {r.L_nH:.4f} nH, R_series = {r.R_series_ohm:.3f} Ohm")

    def cmd_pi3(
        self, name: str, freq_ghz: float, gnd_name: str | None = None
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        gnd = self.shapes.get(gnd_name) if gnd_name else None
        res = pi3_model(sh, self.tech, freq_ghz, ground_shape=gnd)
        print(f"Pi3-model for <{name}> at {freq_ghz:g} GHz:")
        print(f"  L_series = {res.L_series_nH:.4f} nH")
        print(f"  R_series = {res.R_series_ohm:.4f} Ohm")
        print(f"  C_p1_to_gnd = {res.C_p1_to_gnd_fF:.3f} fF")
        print(f"  C_p2_to_gnd = {res.C_p2_to_gnd_fF:.3f} fF")

    def cmd_pi4(
        self,
        name: str,
        freq_ghz: float,
        pad1_name: str | None = None,
        pad2_name: str | None = None,
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        pad1 = self.shapes.get(pad1_name) if pad1_name else None
        pad2 = self.shapes.get(pad2_name) if pad2_name else None
        res = pi4_model(sh, self.tech, freq_ghz, pad1=pad1, pad2=pad2)
        print(f"Pi4-model for <{name}> at {freq_ghz:g} GHz:")
        print(f"  L_series = {res.L_series_nH:.4f} nH")
        print(f"  R_series = {res.R_series_ohm:.4f} Ohm")
        print(f"  C_pad1 = {res.C_pad1_fF:.3f} fF, C_sub1 = {res.C_sub1_fF:.3f} fF")
        print(f"  C_pad2 = {res.C_pad2_fF:.3f} fF, C_sub2 = {res.C_sub2_fF:.3f} fF")

    def cmd_calctrans(
        self, pri_name: str, sec_name: str, freq_ghz: float
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        pri = self.shapes[pri_name]
        sec = self.shapes[sec_name]
        t = calc_transformer(pri, sec, self.tech, freq_ghz)
        print(f"CalcTrans <{pri_name}, {sec_name}> at {freq_ghz:g} GHz:")
        print(f"  L_pri = {t.L_pri_nH:.4f} nH, R_pri = {t.R_pri_ohm:.3f} Ohm,"
              f" Q_pri = {t.Q_pri:.2f}")
        print(f"  L_sec = {t.L_sec_nH:.4f} nH, R_sec = {t.R_sec_ohm:.3f} Ohm,"
              f" Q_sec = {t.Q_sec:.2f}")
        print(f"  M = {t.M_nH:.4f} nH, k = {t.k:.4f}, n = {t.n_turns_ratio:.3f}")

    def cmd_selfres(self, name: str, f_lo: float, f_hi: float) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        sh = self.shapes[name]
        res = self_resonance(sh, self.tech, f_low_ghz=f_lo, f_high_ghz=f_hi)
        if res.converged:
            print(f"Self-resonance({name}) = {res.freq_ghz:.4f} GHz")
            print(f"  Q just below resonance = {res.Q_at_resonance:.2f}")
        else:
            print(
                f"Self-resonance({name}): no zero crossing in "
                f"[{f_lo:g}, {f_hi:g}] GHz "
                f"(likely a lossless-substrate model with no shunt cap)"
            )

    # Info commands ------------------------------------------------------

    def cmd_listsegs(self, name: str) -> None:
        sh = self.shapes[name]
        print(format_segments(sh), end="")

    def cmd_metarea(self, name: str) -> None:
        sh = self.shapes[name]
        print(f"MetalArea({name}) = {metal_area(sh):.2f} um^2")

    def cmd_lrmat(self, name: str, path: str | None = None) -> None:
        sh = self.shapes[name]
        text = format_lr_matrix(sh)
        if path:
            Path(path).write_text(text)
            print(f"Wrote LRMAT to <{path}>")
        else:
            print(text, end="")

    # Sweep --------------------------------------------------------------

    def cmd_sweep(self, args: dict[str, str]) -> None:
        """SWEEP NAME=...:LMIN=...:LMAX=...:LSTEP=...:WMIN=...:WMAX=...:WSTEP=...
                 SMIN=...:SMAX=...:SSTEP=...:NMIN=...:NMAX=...:NSTEP=...:FREQ=...:METAL=...
                 [PATH=<output.tsv>]
        """
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        f = float(args.get("FREQ", "1.0"))
        metal = args.get("METAL", 0)
        Ls = _frange(float(args["LMIN"]), float(args["LMAX"]), float(args["LSTEP"]))
        Ws = _frange(float(args["WMIN"]), float(args["WMAX"]), float(args["WSTEP"]))
        Ss = _frange(float(args["SMIN"]), float(args["SMAX"]), float(args["SSTEP"]))
        Ns = _frange(float(args["NMIN"]), float(args["NMAX"]), float(args["NSTEP"]))
        arr = sweep_square_spiral(
            self.tech,
            length_um=Ls,
            width_um=Ws,
            spacing_um=Ss,
            turns=Ns,
            freq_ghz=f,
            metal=metal,
        )
        path = args.get("PATH")
        if path:
            Path(path).write_text(sweep_to_tsv(arr))
            print(f"Sweep: {len(arr)} points written to <{path}>")
        else:
            print(sweep_to_tsv(arr), end="")

    # Optimisation -------------------------------------------------------

    def cmd_optsq(
        self, target_L_nH: float, freq_ghz: float, metal: str | int = 0
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        res = optimise_square_spiral(
            self.tech,
            target_L_nH=target_L_nH,
            freq_ghz=freq_ghz,
            metal=metal,
        )
        self._print_opt_result("OptSq", res)

    def cmd_optpoly(
        self,
        target_L_nH: float,
        freq_ghz: float,
        sides: int = 8,
        metal: str | int = 0,
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        res = optimise_polygon_spiral(
            self.tech,
            target_L_nH=target_L_nH,
            freq_ghz=freq_ghz,
            sides=sides,
            metal=metal,
        )
        self._print_opt_result(f"OptPoly({sides})", res)

    def cmd_optarea(
        self, target_L_nH: float, freq_ghz: float, metal: str | int = 0
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        res = optimise_area_square_spiral(
            self.tech,
            target_L_nH=target_L_nH,
            freq_ghz=freq_ghz,
            metal=metal,
        )
        self._print_opt_result("OptArea", res)

    def cmd_ldiv(
        self, name: str, n_l: int, n_w: int, n_t: int
    ) -> None:
        """LDIV <name> <n_l> <n_w> <n_t> (case 800).

        Print the inductance with given filament discretisation. The
        binary's LDIV shows the L matrix split per length / width /
        thickness; we print the impedance-matrix solve at low freq
        with the given (n_w, n_t) subdivision (n_l is ignored — we
        don't subdivide along length yet).
        """
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        from reasitic.inductance import solve_inductance_mna
        sh = self.shapes[name]
        L, R = solve_inductance_mna(
            sh, self.tech, freq_ghz=0.001, n_w=n_w, n_t=n_t
        )
        print(
            f"LDiv({name}, n_l={n_l}, n_w={n_w}, n_t={n_t}):"
            f" L = {L:.4f} nH, R = {R:.4f} Ohm"
        )

    def cmd_optsympoly(
        self,
        target_L_nH: float,
        freq_ghz: float,
        sides: int = 8,
        metal: str | int = 0,
    ) -> None:
        """OPTSYMPOLY (case 714) — symmetric polygon-spiral optimiser.

        We implement this as a thin wrapper around the existing
        polygon-spiral optimiser, treating the SymPoly variant the
        same as a regular polygon spiral for the purposes of L/Q
        targeting (the symmetric topology adds a small Q penalty
        that we don't model in detail here).
        """
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        res = optimise_polygon_spiral(
            self.tech,
            target_L_nH=target_L_nH,
            freq_ghz=freq_ghz,
            sides=sides,
            metal=metal,
        )
        self._print_opt_result(f"OptSymPoly({sides})", res)

    def cmd_optsymsq(
        self, target_L_nH: float, freq_ghz: float, metal: str | int = 0
    ) -> None:
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        res = optimise_symmetric_square(
            self.tech,
            target_L_nH=target_L_nH,
            freq_ghz=freq_ghz,
            metal=metal,
        )
        self._print_opt_result("OptSymSq", res)

    def _print_opt_result(self, label: str, res: OptResult) -> None:
        print(f"{label}: success={res.success}")
        print(
            f"  L={res.length_um:.2f}um W={res.width_um:.2f} S={res.spacing_um:.2f}"
            f" N={res.turns:.2f}"
        )
        print(f"  L={res.L_nH:.4f} nH, Q={res.Q:.2f} ({res.message})")

    def cmd_batchopt(self, path: str | None = None) -> None:
        """BatchOpt: read targets from stdin (or file), run OptSq each."""
        if self.tech is None:
            raise RuntimeError("no tech file loaded")
        if path:
            text = Path(path).read_text()
        else:
            print("BatchOpt: enter <target_L_nH> <freq_ghz> per line, blank to end")
            lines = []
            while True:
                try:
                    ln = input("  ")
                except EOFError:
                    break
                if not ln.strip():
                    break
                lines.append(ln)
            text = "\n".join(lines)
        targets = []
        for line in text.splitlines():
            parts = line.split()
            if len(parts) >= 2:
                targets.append((float(parts[0]), float(parts[1])))
        if not targets:
            print("BatchOpt: no targets")
            return
        arr = batch_opt_square(self.tech, targets=targets)
        names = arr.dtype.names
        if names is None:
            print("BatchOpt: empty result")
            return
        print("\t".join(names))
        for row in arr:
            print("\t".join(f"{row[name]:.4g}" for name in names))

    # Dispatcher ----------------------------------------------------------

    def execute(self, line: str) -> bool:
        """Execute one line, catching errors. Returns False on quit."""
        try:
            return self._execute_inner(line)
        except (ValueError, KeyError, RuntimeError, FileNotFoundError) as e:
            print(f"Error: {e}")
            if self.verbose:
                import traceback
                traceback.print_exc()
            return True

    def _execute_inner(self, line: str) -> bool:
        line = line.strip()
        if not line or line.startswith("#"):
            return True
        # Optional macro recording
        if self.macro is not None and not line.upper().startswith("RECORD"):
            self.macro.append(line)
        # Optional log file
        if self.log_path is not None:
            with self.log_path.open("a") as fp:
                fp.write(line + "\n")
        head, _, rest = line.partition(" ")
        head_upper = head.upper()

        # `Q` alone is the Q-factor command, not quit; only QUIT/EXIT
        # leave the loop. Matches the original ASITIC convention.
        if head_upper in ("QUIT", "EXIT"):
            return False
        if head_upper in ("LOAD-TECH", "T", "TECH"):
            self.cmd_load_tech(rest.strip())
        elif head_upper in ("W", "WIRE"):
            self.cmd_wire(_parse_kv_args(rest))
        elif head_upper in ("SQ", "SQUARE"):
            self.cmd_square(_parse_kv_args(rest))
        elif head_upper in ("SP", "SPIRAL"):
            self.cmd_spiral(_parse_kv_args(rest))
        elif head_upper in ("IND", "L"):
            self.cmd_ind(rest.strip())
        elif head_upper in ("RES", "R"):
            parts = rest.split()
            if not parts:
                print("Usage: RES <name> [freq_ghz]")
                return True
            freq = float(parts[1]) if len(parts) > 1 else None
            self.cmd_res(parts[0], freq)
        elif head_upper == "Q":
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: Q <name> <freq_ghz>")
                return True
            self.cmd_q(parts[0], float(parts[1]))
        elif head_upper in ("K", "COUPLING"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: K <name1> <name2>")
                return True
            self.cmd_coupling(parts[0], parts[1])
        elif head_upper == "GEOM":
            self.cmd_geom(rest.strip())
        elif head_upper == "LIST":
            self.cmd_list()
        elif head_upper == "RING":
            self.cmd_ring(_parse_kv_args(rest))
        elif head_upper == "VIA":
            self.cmd_via(_parse_kv_args(rest))
        elif head_upper in ("2PORT", "TWOPORT"):
            parts = rest.split()
            if len(parts) != 4:
                print("Usage: 2PORT <name> <f0_ghz> <f1_ghz> <step_ghz>")
                return True
            self.cmd_2port(parts[0], float(parts[1]), float(parts[2]), float(parts[3]))
        elif head_upper == "CAP":
            self.cmd_cap(rest.strip())
        elif head_upper in ("SAVE", "BSAVE", "BWRITE", "BPUT", "BSTORE",
                              "WRITE", "PUT", "STORE"):
            # The binary's BSAVE / SAVE / BWRITE etc. all map to our
            # single JSON-based persistence (binary format compatibility
            # is sacrificed for portability — we use JSON instead).
            self.cmd_save(rest.strip())
        elif head_upper in ("LOAD", "READ", "BLOAD", "BREAD", "BGET", "BLD",
                              "GET", "LD"):
            self.cmd_load(rest.strip())
        elif head_upper == "CIFSAVE":
            parts = rest.split()
            if not parts:
                print("Usage: CIFSAVE <path> [<name> ...]")
                return True
            self.cmd_cifsave(parts[0], parts[1:])
        elif head_upper in ("TEKSAVE", "PRINTTEKFILE"):
            parts = rest.split()
            if not parts:
                print("Usage: TEKSAVE <path> [<name> ...]")
                return True
            self.cmd_teksave(parts[0], parts[1:])
        elif head_upper == "SONNETSAVE":
            parts = rest.split()
            if not parts:
                print("Usage: SONNETSAVE <path> [<name> ...]")
                return True
            self.cmd_sonnetsave(parts[0], parts[1:])
        elif head_upper == "S2PSAVE":
            parts = rest.split()
            if len(parts) != 5:
                print(
                    "Usage: S2PSAVE <name> <f0_ghz> <f1_ghz> <step_ghz> <path>"
                )
                return True
            self.cmd_s2psave(
                parts[0], float(parts[1]), float(parts[2]), float(parts[3]), parts[4]
            )
        elif head_upper == "OPTSQ":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: OPTSQ <target_L_nH> <freq_ghz> [metal]")
                return True
            metal: str | int = parts[2] if len(parts) > 2 else 0
            self.cmd_optsq(float(parts[0]), float(parts[1]), metal)
        elif head_upper in ("PI", "PIMODEL"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: PI <name> <freq_ghz>")
                return True
            self.cmd_pi(parts[0], float(parts[1]))
        elif head_upper in ("PIX", "PIMODELX"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: PIX <name> <freq_ghz>")
                return True
            self.cmd_pix(parts[0], float(parts[1]))
        elif head_upper == "ZIN":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: ZIN <name> <freq_ghz> [<Z_load_re> <Z_load_im>]")
                return True
            zload = 50.0 + 0j
            if len(parts) >= 4:
                zload = complex(float(parts[2]), float(parts[3]))
            self.cmd_zin(parts[0], float(parts[1]), z_load=zload)
        elif head_upper in ("SELFRES", "SR"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: SELFRES <name> <f_lo_ghz> <f_hi_ghz>")
                return True
            self.cmd_selfres(parts[0], float(parts[1]), float(parts[2]))
        elif head_upper in ("LISTSEGS", "PSEGS"):
            self.cmd_listsegs(rest.strip())
        elif head_upper in ("METAREA", "METALAREA"):
            self.cmd_metarea(rest.strip())
        elif head_upper in ("LRMAT", "LMAT"):
            parts = rest.split()
            if not parts:
                print("Usage: LRMAT <name> [<output_path>]")
                return True
            path = parts[1] if len(parts) > 1 else None
            self.cmd_lrmat(parts[0], path)
        elif head_upper in ("SWEEP", "SW"):
            self.cmd_sweep(_parse_kv_args(rest))
        elif head_upper == "3DTRANS":
            self.cmd_3dtrans(_parse_kv_args(rest))
        elif head_upper in ("SHUNTR", "PR"):
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: SHUNTR <name> <freq_ghz> [S|D]")
                return True
            mode = parts[2] if len(parts) > 2 else "S"
            self.cmd_shuntr(parts[0], float(parts[1]), mode)
        elif head_upper == "PI3":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: PI3 <name> <freq_ghz> [<gnd_name>]")
                return True
            gnd = parts[2] if len(parts) > 2 else None
            self.cmd_pi3(parts[0], float(parts[1]), gnd)
        elif head_upper == "PI4":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: PI4 <name> <freq_ghz> [<pad1> [<pad2>]]")
                return True
            pad1 = parts[2] if len(parts) > 2 else None
            pad2 = parts[3] if len(parts) > 3 else None
            self.cmd_pi4(parts[0], float(parts[1]), pad1, pad2)
        elif head_upper in ("CALCTRANS", "TT"):
            parts = rest.split()
            if len(parts) < 3:
                print("Usage: CALCTRANS <pri> <sec> <freq_ghz>")
                return True
            self.cmd_calctrans(parts[0], parts[1], float(parts[2]))
        elif head_upper == "OPTPOLY":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: OPTPOLY <target_L_nH> <freq_ghz> [sides] [metal]")
                return True
            sides = int(float(parts[2])) if len(parts) > 2 else 8
            opt_metal: str | int = parts[3] if len(parts) > 3 else 0
            self.cmd_optpoly(float(parts[0]), float(parts[1]), sides, opt_metal)
        elif head_upper == "OPTAREA":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: OPTAREA <target_L_nH> <freq_ghz> [metal]")
                return True
            opt_metal_a: str | int = parts[2] if len(parts) > 2 else 0
            self.cmd_optarea(float(parts[0]), float(parts[1]), opt_metal_a)
        elif head_upper in ("OPTSYMSQ", "OPTBALSQ"):
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: OPTSYMSQ <target_L_nH> <freq_ghz> [metal]")
                return True
            opt_metal_s: str | int = parts[2] if len(parts) > 2 else 0
            self.cmd_optsymsq(float(parts[0]), float(parts[1]), opt_metal_s)
        elif head_upper in ("OPTSYMPOLY", "OPTLSYMPOLY", "OPTBALPOLY"):
            parts = rest.split()
            if len(parts) < 2:
                print(
                    "Usage: OPTSYMPOLY <target_L_nH> <freq_ghz> [sides] [metal]"
                )
                return True
            sides = int(float(parts[2])) if len(parts) > 2 else 8
            opt_metal_p: str | int = parts[3] if len(parts) > 3 else 0
            self.cmd_optsympoly(
                float(parts[0]), float(parts[1]), sides, opt_metal_p
            )
        elif head_upper in ("LDIV", "SHOWLDIV"):
            parts = rest.split()
            if len(parts) != 4:
                print("Usage: LDIV <name> <n_l> <n_w> <n_t>")
                return True
            self.cmd_ldiv(
                parts[0],
                int(float(parts[1])),
                int(float(parts[2])),
                int(float(parts[3])),
            )
        # Move-axis variants
        elif head_upper in ("MOVEX", "MVX"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: MOVEX <name> <dx>")
                return True
            self.cmd_movex(parts[0], float(parts[1]))
        elif head_upper in ("MOVEY", "MVY"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: MOVEY <name> <dy>")
                return True
            self.cmd_movey(parts[0], float(parts[1]))
        elif head_upper in ("FLIP", "REVERSE", "REV", "REORDER"):
            self.cmd_flip(rest.strip())
        elif head_upper in ("JOINSHUNT", "ADDSHUNT", "MATESHUNT", "SHUNT"):
            self.cmd_joinshunt(rest.split())
        elif head_upper in ("SELECT", "HIGHLIGHT", "CHOOSE", "FAVORITE"):
            self.cmd_select(rest.strip() or None)
        elif head_upper in ("UNSELECT", "UNHIGHLIGHT", "UNCHOOSE", "UNFAVORITE"):
            self.cmd_unselect()
        elif head_upper in ("SPTOWIRE", "DEMOLISH", "SP2WIRE", "BREAKUP"):
            self.cmd_sptowire(rest.strip())
        # Pi2 / 2PortX / extended forms
        elif head_upper in ("PI2", "PIMODEL2"):
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: PI2 <name> <freq_ghz> [<gnd>]")
                return True
            gnd = parts[2] if len(parts) > 2 else None
            self.cmd_pi2(parts[0], float(parts[1]), gnd)
        elif head_upper in ("2PORTX", "TWOPORTX", "2PX"):
            parts = rest.split()
            if len(parts) != 4:
                print("Usage: 2PORTX <name> <f0> <f1> <step>")
                return True
            self.cmd_2port_x(
                parts[0], float(parts[1]), float(parts[2]), float(parts[3])
            )
        elif head_upper in ("RESISHF", "RESHF", "RHF", "RF"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: RESISHF <name> <freq_ghz>")
                return True
            self.cmd_resishf(parts[0], float(parts[1]))
        elif head_upper in ("CCELL", "CCELLSIZE", "CCELLUNIT", "CMAXCELL"):
            parts = rest.split()
            ml = float(parts[0]) if len(parts) >= 1 else 0.0
            mw = float(parts[1]) if len(parts) >= 2 else 0.0
            self.cmd_ccell(ml, mw)
        elif head_upper in ("SETMAXNW", "MAXNW"):
            v = int(float(rest.strip())) if rest.strip() else 0
            self.cmd_setmaxnw(v)
        elif head_upper in ("SWEEPMM", "SWEEPOPTMM", "OPTSWEEPMM", "SWMM"):
            self.cmd_sweep_mm(_parse_kv_args(rest))
        elif head_upper in ("BCAT", "BDIR", "BHEAD", "BCONTENTS"):
            if not rest.strip():
                print("Usage: BCAT <path>")
                return True
            self.cmd_cat(rest.strip())
        elif head_upper in ("BATCHOPT", "OPTBATCH"):
            path = rest.strip() if rest.strip() else None
            self.cmd_batchopt(path)
        elif head_upper == "SPICESAVE":
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: SPICESAVE <name> <freq_ghz> <path>")
                return True
            self.cmd_spicesave(parts[0], float(parts[1]), parts[2])
        elif head_upper in ("MOVE", "MV"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: MOVE <name> <dx> <dy>")
                return True
            self.cmd_move(parts[0], float(parts[1]), float(parts[2]))
        elif head_upper in ("MOVETO", "SETORIG"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: MOVETO <name> <x> <y>")
                return True
            self.cmd_moveto(parts[0], float(parts[1]), float(parts[2]))
        elif head_upper in ("FLIPV", "VFLIP"):
            self.cmd_flipv(rest.strip())
        elif head_upper in ("FLIPH", "HFLIP"):
            self.cmd_fliph(rest.strip())
        elif head_upper in ("ROTATE", "ROT"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: ROTATE <name> <angle_deg>")
                return True
            self.cmd_rotate(parts[0], float(parts[1]))
        elif head_upper == "REPORT":
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: REPORT <name> <freq_ghz> [<freq_ghz> ...]")
                return True
            self.cmd_report(parts[0], [float(p) for p in parts[1:]])
        elif head_upper in ("2PORTGND", "2PG"):
            parts = rest.split()
            if len(parts) != 5:
                print("Usage: 2PORTGND <name> <gnd> <f0> <f1> <step>")
                return True
            self.cmd_2port_gnd(
                parts[0], parts[1],
                float(parts[2]), float(parts[3]), float(parts[4]),
            )
        elif head_upper in ("2PORTPAD", "2PP"):
            parts = rest.split()
            if len(parts) != 6:
                print("Usage: 2PORTPAD <name> <pad1> <pad2> <f0> <f1> <step>")
                return True
            self.cmd_2port_pad(
                parts[0], parts[1], parts[2],
                float(parts[3]), float(parts[4]), float(parts[5]),
            )
        elif head_upper in ("3PORT", "3P"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: 3PORT <name> <gnd> <freq_ghz>")
                return True
            self.cmd_3port(parts[0], parts[1], float(parts[2]))
        elif head_upper in ("2PORTTRANS", "2PT"):
            parts = rest.split()
            if len(parts) != 5:
                print("Usage: 2PORTTRANS <pri> <sec> <f0> <f1> <step>")
                return True
            self.cmd_2port_trans(
                parts[0], parts[1],
                float(parts[2]), float(parts[3]), float(parts[4]),
            )
        elif head_upper in ("2PZIN", "2PZ"):
            parts = rest.split()
            if len(parts) < 2:
                print("Usage: 2PZIN <name> <freq_ghz> [Z_re Z_im]")
                return True
            zl_re = float(parts[2]) if len(parts) > 2 else 50.0
            zl_im = float(parts[3]) if len(parts) > 3 else 0.0
            self.cmd_2pzin(parts[0], float(parts[1]), zl_re, zl_im)
        elif head_upper == "ERASE":
            self.cmd_erase(rest.split())
        elif head_upper == "RENAME":
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: RENAME <old> <new>")
                return True
            self.cmd_rename(parts[0], parts[1])
        elif head_upper in ("COPY", "CP"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: COPY <src> <dst>")
                return True
            self.cmd_copy(parts[0], parts[1])
        elif head_upper == "HIDE":
            self.cmd_hide(rest.split())
        elif head_upper in ("BEFRIEND", "FRIEND"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: BEFRIEND <s1> <s2>")
                return True
            self.cmd_befriend(parts[0], parts[1])
        elif head_upper in ("UNFRIEND", "DEFRIEND"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: UNFRIEND <s1> <s2>")
                return True
            self.cmd_unfriend(parts[0], parts[1])
        elif head_upper in ("INTERSECT", "FINDI"):
            self.cmd_intersect(rest.strip())
        # Builders
        elif head_upper in ("TRANS", "T"):
            self.cmd_trans(_parse_kv_args(rest))
        elif head_upper in ("BALUN", "B"):
            self.cmd_balun(_parse_kv_args(rest))
        elif head_upper in ("CAPACITOR", "CCAP"):
            self.cmd_capacitor(_parse_kv_args(rest))
        elif head_upper in ("SYMSQ", "BALSQ", "CENTERSQ"):
            self.cmd_symsq(_parse_kv_args(rest))
        elif head_upper in ("SYMPOLY", "BALPOLY", "CENTERPOLY"):
            self.cmd_sympoly(_parse_kv_args(rest))
        elif head_upper in ("MMSQUARE", "MMSQ", "SQMM"):
            self.cmd_mmsquare(_parse_kv_args(rest))
        # Edit
        elif head_upper in ("SPLIT", "UNJOIN", "BREAK"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: SPLIT <name> <segment_index> <new_name>")
                return True
            self.cmd_split(parts[0], int(float(parts[1])), parts[2])
        elif head_upper in ("JOIN", "ADD", "MATE"):
            self.cmd_join(rest.split())
        elif head_upper in ("PHASE", "PH"):
            parts = rest.split()
            if len(parts) != 2:
                print("Usage: PHASE <name> <+1|-1>")
                return True
            self.cmd_phase(parts[0], int(float(parts[1])))
        # Tech edits
        elif head_upper in ("MODIFYTECHLAYER", "TECHLAYER"):
            parts = rest.split()
            if len(parts) != 3:
                print("Usage: MODIFYTECHLAYER <rho|t|eps> <layer> <value>")
                return True
            self.cmd_modify_tech_layer(
                parts[0], int(float(parts[1])), float(parts[2])
            )
        elif head_upper in ("CELL", "CELLSIZE"):
            parts = rest.split()
            kw = {}
            if len(parts) >= 1:
                kw["max_l"] = float(parts[0])
            if len(parts) >= 2:
                kw["max_w"] = float(parts[1])
            if len(parts) >= 3:
                kw["max_t"] = float(parts[2])
            self.cmd_cell(**kw)
        elif head_upper in ("AUTOCELL", "ACELL"):
            parts = rest.split()
            alpha = float(parts[0]) if len(parts) >= 1 else 0.5
            beta = float(parts[1]) if len(parts) >= 2 else 1.0
            self.cmd_auto_cell(alpha, beta)
        elif head_upper == "CHIP":
            parts = rest.split()
            x = float(parts[0]) if len(parts) >= 1 else None
            y = float(parts[1]) if len(parts) >= 2 else None
            self.cmd_chip(x, y)
        elif head_upper in ("EDDY", "CALCEDDY"):
            val = rest.strip().lower()
            on = None
            if val in ("on", "true", "1"):
                on = True
            elif val in ("off", "false", "0"):
                on = False
            self.cmd_eddy(on)
        # View commands — track state where it's a single scalar
        elif head_upper in ("SCALE", "ZOOM"):
            parts = rest.split()
            if parts:
                try:
                    self.cmd_view_set("scale", float(parts[0]))
                    return True
                except ValueError:
                    pass
            self.cmd_no_op_view(head_upper)
        elif head_upper == "PAN":
            parts = rest.split()
            if len(parts) >= 2:
                try:
                    self.cmd_view_set("pan_x", float(parts[0]))
                    self.cmd_view_set("pan_y", float(parts[1]))
                    return True
                except ValueError:
                    pass
            self.cmd_no_op_view(head_upper)
        elif head_upper in ("ORIGIN", "ORIG", "OR", "CENTER"):
            parts = rest.split()
            if len(parts) >= 2:
                try:
                    self.cmd_view_set("origin_x", float(parts[0]))
                    self.cmd_view_set("origin_y", float(parts[1]))
                    return True
                except ValueError:
                    pass
            self.cmd_no_op_view(head_upper)
        elif head_upper == "GRID":
            parts = rest.split()
            if parts:
                try:
                    self.cmd_view_set("grid", float(parts[0]))
                    return True
                except ValueError:
                    pass
            self.cmd_no_op_view(head_upper)
        elif head_upper == "SNAP":
            parts = rest.split()
            if parts:
                try:
                    self.cmd_view_set("snap", float(parts[0]))
                    return True
                except ValueError:
                    pass
            self.cmd_no_op_view(head_upper)
        elif head_upper in (
            "VPAN", "HPAN", "PANOUT", "REFRESH",
            "RULER", "SHOWPHASE", "VPC",
            "BB", "BOUNDINGBOX", "FULLVIEW", "FV", "ORIGIN3D",
            "SCALE3D", "ROTATE3D", "METAL", "OPENGL", "TEKIO",
            "OPTIONS", "SETMAXNW", "PRINTTEKFILE",
        ):
            self.cmd_no_op_view(head_upper)
        # Pause / Input
        elif head_upper in ("PAUSE", "WAIT"):
            self.cmd_pause()
        elif head_upper in ("INPUT", "REDIRECT"):
            path = rest.split()[0] if rest.strip() else None
            self.cmd_input(path)
        elif head_upper == "VERBOSE":
            self.cmd_verbose(rest.strip() or None)
        elif head_upper in ("TIMER", "TIME"):
            self.cmd_timer(rest.strip() or None)
        elif head_upper == "SAVEMAT":
            self.cmd_savemat(rest.strip() or None)
        elif head_upper == "RECORD":
            self.cmd_record(rest.strip() or None)
        elif head_upper == "EXEC":
            if not rest.strip():
                print("Usage: EXEC <path>")
                return True
            self.cmd_exec_script(rest.strip())
        elif head_upper == "CAT":
            if not rest.strip():
                print("Usage: CAT <path>")
                return True
            self.cmd_cat(rest.strip())
        elif head_upper in ("VERSION", "VER"):
            self.cmd_version()
        elif head_upper == "LOG":
            self.cmd_log(rest.strip() or None)
        elif head_upper in ("HELP", "?"):
            self.cmd_help(rest.strip() or None)
        else:
            print(f"Unknown command: {head!r}")
        return True


def _print_status(repl: Repl) -> None:
    """Print a summary of the REPL state (loaded tech, shapes, viewport)."""
    if repl.tech:
        print(f"Tech: {repl.tech.chip.tech_file or '(in-memory)'}"
              f" — {len(repl.tech.metals)} metals,"
              f" {len(repl.tech.layers)} layers,"
              f" {len(repl.tech.vias)} vias")
    else:
        print("Tech: (none)")
    print(f"Shapes: {len(repl.shapes)}")
    for name, sh in repl.shapes.items():
        print(f"  {name}: {len(sh.polygons)} polygons,"
              f" {len(sh.segments())} segments")
    print(
        f"Viewport: scale={repl.viewport['scale']},"
        f" pan=({repl.viewport['pan_x']}, {repl.viewport['pan_y']}),"
        f" origin=({repl.viewport['origin_x']}, {repl.viewport['origin_y']})"
    )
    print(
        f"Toggles: verbose={repl.verbose}, timer={repl.timer},"
        f" save_mat={repl.save_mat}"
    )


def main(argv: list[str] | None = None) -> int:
    """Entry point for the ``reasitic`` console script."""
    parser = argparse.ArgumentParser(prog="reasitic")
    parser.add_argument("-t", "--tech", type=Path, help="tech file to load on startup")
    parser.add_argument(
        "-x", "--exec", dest="script", type=Path, help="run commands from a script file"
    )
    parser.add_argument("-c", "--command", help="run a single command and exit")
    parser.add_argument(
        "--version", action="store_true", help="print the version and exit"
    )
    parser.add_argument(
        "--status", action="store_true",
        help="print loaded-tech / shape summary and exit (use with -t and -x)",
    )
    args = parser.parse_args(argv)

    if args.version:
        from reasitic import __version__
        print(f"reASITIC {__version__}")
        return 0

    repl = Repl()
    if args.tech:
        repl.cmd_load_tech(str(args.tech))

    if args.command:
        repl.execute(args.command)
        if args.status:
            _print_status(repl)
        return 0

    if args.script:
        for line in args.script.read_text().splitlines():
            if not repl.execute(line):
                break
        if args.status:
            _print_status(repl)
        return 0

    if args.status:
        _print_status(repl)
        return 0

    # Interactive
    print("reASITIC — type 'help' for help, 'quit' to exit")
    try:
        while True:
            try:
                line = input("reASITIC> ")
            except EOFError:
                break
            if not repl.execute(line):
                break
    except KeyboardInterrupt:
        print()
    return 0


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
