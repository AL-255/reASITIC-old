#!/usr/bin/env python3
"""GUI browser for the ASITIC validation test set.

Usage:
    python3 reASITIC/tests/data/validation/browse.py

Reads every ``*.json`` ground-truth record in its own directory,
lists them on the left, and on selection plots the corresponding
LRQ panels (inductance, resistance, Q-factor across frequency)
plus the Touchstone S-parameter sweep loaded from
``analysis/<stem>.s2p``.

Requirements: Python 3, tkinter (stdlib), matplotlib, numpy.
"""
from __future__ import annotations

import json
import tkinter as tk
from pathlib import Path
from tkinter import ttk

import numpy as np
from matplotlib.backends.backend_tkagg import FigureCanvasTkAgg
from matplotlib.figure import Figure

HERE = Path(__file__).resolve().parent
ANALYSIS_DIR = HERE / "analysis"


def load_s2p(path: Path) -> np.ndarray | None:
    """Parse Touchstone v1 magnitude/angle S2P. Returns Nx9 array
    (freq_GHz, S11_mag, S11_phase, S12_mag, S12_phase, S21_mag,
    S21_phase, S22_mag, S22_phase) or ``None`` if unparseable."""
    rows: list[list[float]] = []
    for line in path.read_text().splitlines():
        s = line.strip()
        if not s or s.startswith(("!", "#")):
            continue
        try:
            toks = [float(t) for t in s.split()]
        except ValueError:
            continue
        if len(toks) == 9:
            rows.append(toks)
    return np.array(rows) if rows else None


class App:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        root.title("ASITIC validation browser")
        root.geometry("1280x820")

        # Discover JSONs once at startup, capturing tech +
        # create-command for the filter dropdowns.
        self.case_meta: dict[str, dict[str, str]] = {}
        for p in sorted(HERE.glob("*.json")):
            try:
                d = json.loads(p.read_text())
            except (OSError, ValueError):
                continue
            build = (d.get("build_command") or "").strip()
            cmd = build.split()[0].upper() if build else "?"
            self.case_meta[p.stem] = {
                "tech": (d.get("tech") or "?"),
                "cmd": cmd,
            }
        self.all_stems = sorted(self.case_meta)
        techs = sorted({m["tech"] for m in self.case_meta.values()})
        cmds = sorted({m["cmd"] for m in self.case_meta.values()})

        # ── Left panel: search + filterable listbox ───────────────
        left = ttk.Frame(root, padding=4)
        left.pack(side=tk.LEFT, fill=tk.Y)

        # Tech + create-command filter dropdowns.
        filters = ttk.Frame(left)
        filters.pack(fill=tk.X)
        ttk.Label(filters, text="tech").grid(row=0, column=0, sticky="w")
        self.tech_var = tk.StringVar(value="(all)")
        tech_box = ttk.Combobox(
            filters, textvariable=self.tech_var, state="readonly",
            values=["(all)"] + techs, width=10,
        )
        tech_box.grid(row=0, column=1, padx=(2, 8), sticky="ew")
        tech_box.bind("<<ComboboxSelected>>",
                      lambda *_: self._refresh_list())

        ttk.Label(filters, text="cmd").grid(row=0, column=2, sticky="w")
        self.cmd_var = tk.StringVar(value="(all)")
        cmd_box = ttk.Combobox(
            filters, textvariable=self.cmd_var, state="readonly",
            values=["(all)"] + cmds, width=12,
        )
        cmd_box.grid(row=0, column=3, padx=(2, 0), sticky="ew")
        cmd_box.bind("<<ComboboxSelected>>",
                     lambda *_: self._refresh_list())
        filters.columnconfigure(1, weight=1)
        filters.columnconfigure(3, weight=1)

        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        search = ttk.Entry(left, textvariable=self.search_var)
        search.pack(fill=tk.X, pady=(6, 0))
        ttk.Label(left, text="filter (case-insensitive substring)",
                  foreground="#666").pack(anchor="w")

        list_frame = ttk.Frame(left)
        list_frame.pack(fill=tk.BOTH, expand=True, pady=(4, 0))
        scroll = ttk.Scrollbar(list_frame)
        scroll.pack(side=tk.RIGHT, fill=tk.Y)
        self.listbox = tk.Listbox(
            list_frame, width=52, font=("monospace", 9),
            yscrollcommand=scroll.set, exportselection=False,
            activestyle="dotbox",
        )
        self.listbox.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)
        scroll.config(command=self.listbox.yview)
        self.listbox.bind("<<ListboxSelect>>", self.on_select)

        self.status_var = tk.StringVar(value="")
        ttk.Label(left, textvariable=self.status_var,
                  foreground="#444").pack(anchor="w", pady=(4, 0))

        # ── Right panel: matplotlib figure ────────────────────────
        right = ttk.Frame(root, padding=4)
        right.pack(side=tk.RIGHT, fill=tk.BOTH, expand=True)
        self.fig = Figure(figsize=(9, 8), constrained_layout=True)
        self.canvas = FigureCanvasTkAgg(self.fig, master=right)
        self.canvas.get_tk_widget().pack(fill=tk.BOTH, expand=True)

        self._refresh_list()
        if self.listbox.size() > 0:
            self.listbox.selection_set(0)
            self.listbox.event_generate("<<ListboxSelect>>")

    # ── List management ─────────────────────────────────────────
    def _display_text(self, stem: str, drop_cmd: bool, drop_tech: bool) -> str:
        """Render the listbox label, dropping tokens already implied
        by the current filter selection (cleaner display).

        The stem layout is ``<shape>_<tech>_<rest...>`` so dropping
        position 0 strips the shape prefix and dropping position 1
        strips the tech token.
        """
        if not (drop_cmd or drop_tech):
            return stem
        tokens = stem.split("_")
        drop: set[int] = set()
        if drop_cmd and len(tokens) > 0:
            drop.add(0)
        if drop_tech and len(tokens) > 1:
            drop.add(1)
        return "_".join(t for i, t in enumerate(tokens) if i not in drop) or stem

    def _refresh_list(self) -> None:
        query = self.search_var.get().lower().strip()
        tech_pick = self.tech_var.get()
        cmd_pick = self.cmd_var.get()
        drop_tech = tech_pick != "(all)"
        drop_cmd = cmd_pick != "(all)"
        self.listbox.delete(0, tk.END)
        # Parallel list of stems for the visible rows — the listbox
        # display can be a redacted form, but the on_select handler
        # still needs the full stem to find the JSON file.
        self.visible_stems: list[str] = []
        for stem in self.all_stems:
            meta = self.case_meta[stem]
            if drop_tech and meta["tech"] != tech_pick:
                continue
            if drop_cmd and meta["cmd"] != cmd_pick:
                continue
            if query and query not in stem.lower():
                continue
            self.listbox.insert(tk.END, self._display_text(stem, drop_cmd, drop_tech))
            self.visible_stems.append(stem)
        n_total = len(self.all_stems)
        n_shown = self.listbox.size()
        suffix = "" if n_shown == n_total else f" / {n_total}"
        self.status_var.set(f"{n_shown} case(s){suffix}")

    # ── Selection → plot ────────────────────────────────────────
    def on_select(self, _evt: object = None) -> None:
        sel = self.listbox.curselection()
        if not sel:
            return
        idx = sel[0]
        if idx >= len(self.visible_stems):
            return
        stem = self.visible_stems[idx]
        json_path = HERE / f"{stem}.json"
        if not json_path.exists():
            return
        record = json.loads(json_path.read_text())
        self.plot(record)

    def plot(self, d: dict) -> None:
        self.fig.clear()
        analysis = d.get("analysis", {}) or {}
        freqs = analysis.get("freq_points_ghz") or []
        pi2 = analysis.get("pi2_points") or []
        pi2_f = [p.get("freq_ghz") for p in pi2]

        s2p_path = ANALYSIS_DIR / f"{d['name']}.s2p"
        s2p = load_s2p(s2p_path) if s2p_path.exists() else None

        # Self-resonant frequency: each Pi2 invocation reports its
        # own f_res estimate. Use the lowest-frequency Pi2 point —
        # the linear-region extrapolation is most reliable there.
        srf_ghz: float | None = None
        if pi2:
            lowest = min(pi2, key=lambda p: p.get("freq_ghz") or float("inf"))
            srf_ghz = lowest.get("f_res_ghz")

        def _mark_srf(ax, x_range: tuple[float, float] | None) -> None:
            """Draw a red SRF vline iff it falls in ``x_range``.

            Pins xlim to the data range before plotting so the
            vline doesn't extend the axis. No-op when SRF is
            unknown, NaN, or outside the panel's frequency span.
            """
            if srf_ghz is None or x_range is None:
                return
            if not (srf_ghz == srf_ghz):  # NaN guard
                return
            lo, hi = x_range
            if not (lo <= srf_ghz <= hi):
                return
            ax.set_xlim(lo, hi)
            ax.axvline(
                srf_ghz, color="red", linestyle="--", linewidth=1.5,
                alpha=0.85, label=f"SRF ≈ {srf_ghz:.2f} GHz",
            )

        lrq_range = (min(freqs), max(freqs)) if freqs else None
        s_range = (
            (float(s2p[0, 0]), float(s2p[-1, 0]))
            if s2p is not None and s2p.shape[0] > 0 else None
        )

        ax_l = self.fig.add_subplot(2, 2, 1)
        ax_r = self.fig.add_subplot(2, 2, 2)
        ax_q = self.fig.add_subplot(2, 2, 3)
        ax_s = self.fig.add_subplot(2, 2, 4)

        # ── Inductance L(f) ─────────────────────────────────────
        if pi2:
            ax_l.plot(pi2_f, [p.get("L_nh") for p in pi2],
                      "o-", label="Pi2 model")
        if analysis.get("lrmat_l_h") and freqs:
            ax_l.plot(
                freqs,
                [(v * 1e9) if v is not None else None
                 for v in analysis["lrmat_l_h"]],
                "s--", label="LRMAT partial-L",
            )
        if analysis.get("ind_dc_nh") is not None:
            ax_l.axhline(
                analysis["ind_dc_nh"], linestyle=":", color="grey",
                alpha=0.6, label=f"DC = {analysis['ind_dc_nh']:.4g} nH",
            )
        _mark_srf(ax_l, lrq_range)
        ax_l.set_xlabel("frequency (GHz)")
        ax_l.set_ylabel("L (nH)")
        ax_l.set_title("Inductance")
        ax_l.grid(True, alpha=0.3)
        ax_l.legend(fontsize=8, loc="best")

        # ── Resistance R(f) ─────────────────────────────────────
        if pi2:
            ax_r.plot(pi2_f, [p.get("R_ohm") for p in pi2],
                      "o-", label="Pi2 series R")
        if analysis.get("res_hf_ohm") and freqs:
            ax_r.plot(freqs, analysis["res_hf_ohm"],
                      "s--", label="ResHF")
        if analysis.get("lrmat_r_ohm") and freqs:
            ax_r.plot(freqs, analysis["lrmat_r_ohm"],
                      "^:", label="LRMAT R")
        if analysis.get("res_dc_ohm") is not None:
            ax_r.axhline(
                analysis["res_dc_ohm"], linestyle=":", color="grey",
                alpha=0.6, label=f"DC = {analysis['res_dc_ohm']:.4g} Ω",
            )
        _mark_srf(ax_r, lrq_range)
        ax_r.set_xlabel("frequency (GHz)")
        ax_r.set_ylabel("R (Ω)")
        ax_r.set_title("Resistance")
        ax_r.grid(True, alpha=0.3)
        ax_r.legend(fontsize=8, loc="best")

        # ── Quality factor Q(f) ─────────────────────────────────
        if analysis.get("q") and freqs:
            ax_q.plot(freqs, analysis["q"],
                      "o-", label="Q (LF extrap)")
        if pi2:
            q_idx_labels = ["Q[0]", "Q[port1 gnd]", "Q[port2 gnd]"]
            markers = ["s", "^", "v"]
            for k, (lab, mk) in enumerate(zip(q_idx_labels, markers)):
                ys = [(p.get("q_three") or [None]*3)[k] for p in pi2]
                if any(y is not None for y in ys):
                    ax_q.plot(pi2_f, ys, mk + "--", alpha=0.7,
                              label=f"Pi2 {lab}")
        _mark_srf(ax_q, lrq_range)
        ax_q.set_xlabel("frequency (GHz)")
        ax_q.set_ylabel("Q")
        ax_q.set_title("Quality factor")
        ax_q.grid(True, alpha=0.3)
        ax_q.legend(fontsize=8, loc="best")

        # ── S-parameters from the .s2p sweep ────────────────────
        if s2p is not None and s2p.shape[0] > 0:
            f = s2p[:, 0]
            ax_s.plot(f, s2p[:, 1], "o-", label="|S11|")
            ax_s.plot(f, s2p[:, 5], "s-", label="|S21|")
            ax_s.plot(f, s2p[:, 7], "^-", label="|S22|")
            _mark_srf(ax_s, s_range)
            ax_s.set_xlabel("frequency (GHz)")
            ax_s.set_ylabel("|S| (linear)")
            ax_s.set_title("S-parameters (magnitude)")
            ax_s.grid(True, alpha=0.3)
            ax_s.legend(fontsize=8, loc="best")
            ax_s.set_ylim(0, max(1.05, ax_s.get_ylim()[1]))
        else:
            ax_s.text(0.5, 0.5, f"no S2P at\n{s2p_path.name}",
                      transform=ax_s.transAxes,
                      ha="center", va="center", color="#888")
            ax_s.set_xticks([]); ax_s.set_yticks([])

        geom = d.get("geom", {}) or {}
        title = (
            f"{d['name']}    [{d.get('tech', '?')}, "
            f"{geom.get('kind', '?')}]\n"
            f"{d.get('build_command', '')}"
        )
        self.fig.suptitle(title, fontsize=9, family="monospace")
        self.canvas.draw_idle()


def main() -> None:
    root = tk.Tk()
    try:
        ttk.Style().theme_use("clam")
    except tk.TclError:
        pass
    App(root)
    root.mainloop()


if __name__ == "__main__":
    main()
