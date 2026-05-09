"""reASITIC interactive GUI — a single-window layout viewer + console.

Mirrors the original ASITIC X11 front-end (``decomp/output/asitic_repl.c``):

* A 2-D top-down layout view (``xui_render_layout_view``) with pan/zoom,
  chip outline (``xui_draw_chip_outline``) and a substrate grid
  (``xui_draw_grid_or_ruler``).
* A status bar showing current zoom and world cursor coordinates.
* An embedded REPL pane that drives :class:`reasitic.cli.Repl` exactly
  the way the original binary's terminal-side readline did, so every
  one of the 117 binary commands works in the GUI.
* Mouse interactions: drag to pan, scroll wheel to zoom around the
  cursor, click on a shape to select it (highlights its bounding box,
  matching ``xui_draw_zoom_box_around_current_shape``).
"""

from __future__ import annotations

import io
from contextlib import redirect_stderr, redirect_stdout

from reasitic.cli import Repl
from reasitic.gui.renderer import (
    LAYOUT_TAG,
    render_all,
)
from reasitic.gui.viewport import Viewport


class GuiApp:
    """The reASITIC graphical workspace.

    The GUI is a thin presentation layer over an embedded
    :class:`~reasitic.cli.Repl`. Each command typed into the console
    pane is forwarded verbatim to ``repl.execute`` (with stdout / stderr
    captured into the console widget) and then the layout view is
    redrawn from ``repl.shapes``. This means *every* command that works
    in the headless CLI also works in the GUI, with identical output.
    """

    # ------------------------------------------------------------------
    # Construction
    # ------------------------------------------------------------------

    def __init__(self, *, repl: Repl | None = None,
                 width: int = 1100, height: int = 720,
                 title: str = "reASITIC") -> None:
        """Build the Tk window. Tk imports are deferred so the rest of
        ``reasitic.gui`` stays importable on headless boxes."""
        import tkinter as tk
        from tkinter import scrolledtext

        self._tk = tk
        self.repl = repl or Repl()
        self.viewport = Viewport(canvas_width=width, canvas_height=int(height * 0.65))
        self.selected: str | None = None
        # Default grid spacing — overridden by the SETGRID command and
        # by tech files via the SNAPGRID option.
        self.grid_step_um: float = 0.0
        self._drag_origin: tuple[int, int] | None = None

        self.root = tk.Tk()
        self.root.title(title)
        self.root.geometry(f"{width}x{height}")
        self.root.configure(bg="#181818")

        # ----- Menu bar ------------------------------------------------
        self._build_menu()

        # ----- Toolbar -------------------------------------------------
        toolbar = tk.Frame(self.root, bg="#202020", height=32)
        toolbar.pack(side=tk.TOP, fill=tk.X)
        for label, cb in (
            ("Fit",      self.action_fit),
            ("Zoom +",   lambda: self._zoom_centre(1.25)),
            ("Zoom −",   lambda: self._zoom_centre(0.8)),
            ("Reset",    self.action_reset_view),
            ("Grid",     self.action_toggle_grid),
            ("Redraw",   self.refresh_view),
        ):
            tk.Button(toolbar, text=label, command=cb, bg="#303030",
                      fg="#dddddd", relief=tk.FLAT, padx=10).pack(
                          side=tk.LEFT, padx=2, pady=4)

        # ----- Vertical splitter: canvas (top) + console (bottom) -----
        paned = tk.PanedWindow(self.root, orient=tk.VERTICAL,
                               sashrelief=tk.RAISED, bg="#181818")
        paned.pack(fill=tk.BOTH, expand=True)

        # Canvas
        canvas_frame = tk.Frame(paned, bg="#101010")
        self.canvas = tk.Canvas(canvas_frame,
                                bg="#101010",
                                highlightthickness=0)
        self.canvas.pack(fill=tk.BOTH, expand=True)
        paned.add(canvas_frame, stretch="always")

        # Console
        console_frame = tk.Frame(paned, bg="#101010")
        self.console = scrolledtext.ScrolledText(
            console_frame, wrap=tk.WORD, height=10,
            bg="#101010", fg="#dddddd",
            insertbackground="#dddddd",
            font=("TkFixedFont", 10),
        )
        self.console.pack(fill=tk.BOTH, expand=True, padx=2, pady=2)
        self.console.configure(state=tk.DISABLED)

        prompt_row = tk.Frame(console_frame, bg="#181818")
        prompt_row.pack(fill=tk.X)
        tk.Label(prompt_row, text="reASITIC>", bg="#181818",
                 fg="#9cdcfe", font=("TkFixedFont", 10)).pack(side=tk.LEFT)
        self.entry = tk.Entry(prompt_row, bg="#101010", fg="#dddddd",
                              insertbackground="#dddddd",
                              font=("TkFixedFont", 10),
                              relief=tk.FLAT)
        self.entry.pack(side=tk.LEFT, fill=tk.X, expand=True, padx=4)
        self.entry.bind("<Return>", self._on_entry_return)
        self.entry.bind("<Up>",     self._on_history_prev)
        self.entry.bind("<Down>",   self._on_history_next)
        self._history: list[str] = []
        self._history_idx: int = 0
        paned.add(console_frame, stretch="never")

        # ----- Status bar ---------------------------------------------
        self.status = tk.Label(self.root, text="", bg="#202020",
                               fg="#bbbbbb", anchor="w",
                               font=("TkDefaultFont", 9))
        self.status.pack(side=tk.BOTTOM, fill=tk.X)

        # ----- Bindings -----------------------------------------------
        self.canvas.bind("<Configure>",        self._on_canvas_resize)
        self.canvas.bind("<ButtonPress-1>",    self._on_lmb_press)
        self.canvas.bind("<B1-Motion>",        self._on_lmb_drag)
        self.canvas.bind("<ButtonRelease-1>",  self._on_lmb_release)
        self.canvas.bind("<Motion>",           self._on_motion)
        # Linux scroll wheel comes through as Button-4 / Button-5
        self.canvas.bind("<Button-4>",
                         lambda e: self._zoom_at_event(e, 1.2))
        self.canvas.bind("<Button-5>",
                         lambda e: self._zoom_at_event(e, 1 / 1.2))
        # Windows/macOS deliver <MouseWheel> with delta sign
        self.canvas.bind("<MouseWheel>",
                         lambda e: self._zoom_at_event(
                             e, 1.2 if e.delta > 0 else 1 / 1.2))
        self.root.bind("<g>",     lambda _e: self.action_toggle_grid())
        self.root.bind("<f>",     lambda _e: self.action_fit())
        self.root.bind("<r>",     lambda _e: self.refresh_view())
        self.root.bind("<Escape>", lambda _e: self._clear_selection())

        self._println("reASITIC GUI ready. Type 'help' for help.")

    # ------------------------------------------------------------------
    # Menu
    # ------------------------------------------------------------------

    def _build_menu(self) -> None:
        tk = self._tk
        menubar = tk.Menu(self.root)

        m_file = tk.Menu(menubar, tearoff=False)
        m_file.add_command(label="Load tech…",   command=self._menu_load_tech)
        m_file.add_command(label="Load session…", command=self._menu_load_session)
        m_file.add_command(label="Save session…", command=self._menu_save_session)
        m_file.add_separator()
        m_file.add_command(label="Quit", accelerator="Ctrl+Q",
                           command=self.root.destroy)
        menubar.add_cascade(label="File", menu=m_file)

        m_view = tk.Menu(menubar, tearoff=False)
        m_view.add_command(label="Fit",          accelerator="F",
                           command=self.action_fit)
        m_view.add_command(label="Reset view",   command=self.action_reset_view)
        m_view.add_command(label="Toggle grid",  accelerator="G",
                           command=self.action_toggle_grid)
        m_view.add_command(label="Redraw",       accelerator="R",
                           command=self.refresh_view)
        menubar.add_cascade(label="View", menu=m_view)

        m_help = tk.Menu(menubar, tearoff=False)
        m_help.add_command(label="REPL help", command=lambda: self._run("help"))
        m_help.add_command(label="About reASITIC",
                           command=lambda: self._run("version"))
        menubar.add_cascade(label="Help", menu=m_help)

        self.root.config(menu=menubar)
        self.root.bind("<Control-q>", lambda _e: self.root.destroy())

    def _menu_load_tech(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Load tech file",
            filetypes=[("Tek tech file", "*.tek"), ("All files", "*.*")])
        if path:
            self._run(f"load-tech {path}")

    def _menu_load_session(self) -> None:
        from tkinter import filedialog
        path = filedialog.askopenfilename(
            title="Load session",
            filetypes=[("JSON session", "*.json"), ("All files", "*.*")])
        if path:
            self._run(f"load {path}")
            self.action_fit()

    def _menu_save_session(self) -> None:
        from tkinter import filedialog
        path = filedialog.asksaveasfilename(
            title="Save session",
            defaultextension=".json",
            filetypes=[("JSON session", "*.json")])
        if path:
            self._run(f"save {path}")

    # ------------------------------------------------------------------
    # Console — capture stdout/stderr, drive Repl.execute, refresh view
    # ------------------------------------------------------------------

    def _println(self, s: str) -> None:
        self.console.configure(state=self._tk.NORMAL)
        self.console.insert(self._tk.END, s if s.endswith("\n") else s + "\n")
        self.console.see(self._tk.END)
        self.console.configure(state=self._tk.DISABLED)

    def _run(self, line: str) -> None:
        """Run a command in the embedded Repl and pipe output to the console."""
        if not line.strip():
            return
        self._println(f"reASITIC> {line}")
        out = io.StringIO()
        try:
            with redirect_stdout(out), redirect_stderr(out):
                cont = self.repl.execute(line)
        except Exception as exc:
            self._println(f"error: {exc}")
            return
        text = out.getvalue()
        if text:
            self._println(text.rstrip("\n"))
        self.refresh_view()
        if not cont:
            self.root.after(50, self.root.destroy)

    def _on_entry_return(self, _event: object) -> None:
        line = self.entry.get()
        self.entry.delete(0, self._tk.END)
        if line.strip():
            self._history.append(line)
            self._history_idx = len(self._history)
        self._run(line)

    def _on_history_prev(self, _event: object) -> str:
        if self._history and self._history_idx > 0:
            self._history_idx -= 1
            self.entry.delete(0, self._tk.END)
            self.entry.insert(0, self._history[self._history_idx])
        return "break"

    def _on_history_next(self, _event: object) -> str:
        if self._history_idx < len(self._history) - 1:
            self._history_idx += 1
            self.entry.delete(0, self._tk.END)
            self.entry.insert(0, self._history[self._history_idx])
        else:
            self._history_idx = len(self._history)
            self.entry.delete(0, self._tk.END)
        return "break"

    # ------------------------------------------------------------------
    # Mouse / keyboard
    # ------------------------------------------------------------------

    def _on_canvas_resize(self, event: object) -> None:
        self.viewport.canvas_width = self.canvas.winfo_width()
        self.viewport.canvas_height = self.canvas.winfo_height()
        self.refresh_view()

    def _on_lmb_press(self, event: object) -> None:
        self._drag_origin = (event.x, event.y)  # type: ignore[attr-defined]
        self._drag_pan_start = (self.viewport.pan_x, self.viewport.pan_y)
        # If we click on a shape, select it. We test the first hit using
        # Tk's find_closest with a small tolerance band.
        cid = self.canvas.find_closest(event.x, event.y, halo=3)  # type: ignore[attr-defined]
        if cid:
            tags = self.canvas.gettags(cid[0])
            for t in tags:
                if t.startswith("shape:"):
                    name = t.split(":", 1)[1]
                    self.selected = name
                    self.repl.selected_shape = name
                    self.refresh_view()
                    self._println(f"Selected: {name}")
                    return

    def _on_lmb_drag(self, event: object) -> None:
        if self._drag_origin is None:
            return
        x0, y0 = self._drag_origin
        dx = event.x - x0  # type: ignore[attr-defined]
        dy = event.y - y0  # type: ignore[attr-defined]
        if abs(dx) + abs(dy) < 2:
            return
        # Pan from the original position
        self.viewport.pan_x = self._drag_pan_start[0] + dx / self.viewport.zoom
        self.viewport.pan_y = self._drag_pan_start[1] - dy / self.viewport.zoom
        self.refresh_view()

    def _on_lmb_release(self, _event: object) -> None:
        self._drag_origin = None

    def _on_motion(self, event: object) -> None:
        wx, wy = self.viewport.screen_to_world(
            event.x, event.y)  # type: ignore[attr-defined]
        sel = f"  selected={self.selected}" if self.selected else ""
        self.status.configure(
            text=(f"x={wx:8.2f} μm   y={wy:8.2f} μm   "
                  f"zoom={self.viewport.zoom:.3f} px/μm{sel}"))

    def _zoom_at_event(self, event: object, factor: float) -> None:
        self.viewport.zoom_at_screen(
            event.x, event.y, factor)  # type: ignore[attr-defined]
        self.refresh_view()

    def _zoom_centre(self, factor: float) -> None:
        self.viewport.zoom_at_screen(
            self.viewport.canvas_width / 2,
            self.viewport.canvas_height / 2, factor)
        self.refresh_view()

    def _clear_selection(self) -> None:
        self.selected = None
        self.repl.selected_shape = None
        self.refresh_view()

    # ------------------------------------------------------------------
    # View actions
    # ------------------------------------------------------------------

    def action_fit(self) -> None:
        """Frame all shapes — or the chip outline if there are none."""
        if not self.repl.shapes:
            if self.repl.tech is not None:
                cx = self.repl.tech.chip.chipx or 1000.0
                cy = self.repl.tech.chip.chipy or 1000.0
                self.viewport.fit_bbox(0.0, 0.0, cx, cy)
            else:
                self.viewport.reset()
            self.refresh_view()
            return
        x0 = y0 = float("+inf")
        x1 = y1 = float("-inf")
        for sh in self.repl.shapes.values():
            bx0, by0, bx1, by1 = sh.bounding_box()
            if bx0 == bx1 == by0 == by1 == 0.0:
                continue
            x0 = min(x0, bx0)
            y0 = min(y0, by0)
            x1 = max(x1, bx1)
            y1 = max(y1, by1)
        if x0 == float("+inf"):
            self.viewport.reset()
        else:
            self.viewport.fit_bbox(x0, y0, x1, y1)
        self.refresh_view()

    def action_reset_view(self) -> None:
        """Restore identity zoom (1 px/μm) and zero pan."""
        self.viewport.reset()
        self.refresh_view()

    def action_toggle_grid(self) -> None:
        """Switch the substrate grid overlay on/off."""
        if self.grid_step_um > 0:
            self.grid_step_um = 0.0
        else:
            # Pull from REPL viewport (matches binary's GRID setting),
            # otherwise fall back to chip / 32.
            g = float(self.repl.viewport.get("grid", 0.0) or 0.0)
            if g > 0:
                self.grid_step_um = g
            elif self.repl.tech and self.repl.tech.chip.chipx:
                self.grid_step_um = self.repl.tech.chip.chipx / 32.0
            else:
                self.grid_step_um = 50.0
        self.refresh_view()

    def refresh_view(self) -> None:
        """Wipe the canvas and re-render chip / grid / shapes / selection."""
        render_all(
            self.canvas,
            self.repl.tech,
            self.repl.shapes,
            self.viewport,
            grid_step_um=self.grid_step_um,
            selected=self.selected or self.repl.selected_shape,
        )
        # Move the layout group below the selection rectangle so the
        # selection highlight stays visible.
        self.canvas.tag_lower(LAYOUT_TAG)

    # ------------------------------------------------------------------
    # Entry point
    # ------------------------------------------------------------------

    def mainloop(self) -> None:
        """Run the Tk event loop; returns when the window is closed."""
        # Initial fit — best-effort once Tk has computed widget geometry
        self.root.update_idletasks()
        self.viewport.canvas_width = max(self.canvas.winfo_width(), 200)
        self.viewport.canvas_height = max(self.canvas.winfo_height(), 200)
        self.action_fit()
        self.root.mainloop()


def run(*, tech_path: str | None = None,
        session_path: str | None = None) -> None:
    """Spawn the GUI. Optionally load a tech file and/or session on startup."""
    app = GuiApp()
    if tech_path:
        app._run(f"load-tech {tech_path}")
    if session_path:
        app._run(f"load {session_path}")
    app.mainloop()
