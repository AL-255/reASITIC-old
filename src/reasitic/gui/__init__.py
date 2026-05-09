"""reASITIC graphical interface (Tkinter).

The GUI is a single window that mirrors the original ASITIC X11
front-end: a top-down 2-D layout view (pan/zoom, chip outline,
substrate grid, click-to-select) over an embedded REPL pane that
forwards every typed line to :class:`reasitic.cli.Repl`.
"""

from __future__ import annotations

from reasitic.gui.colors import metal_color, normalize, via_color
from reasitic.gui.viewport import Viewport

__all__ = [
    "Viewport",
    "metal_color",
    "normalize",
    "run",
    "via_color",
]


def run(*, tech_path: str | None = None,
        session_path: str | None = None) -> None:
    """Spawn the reASITIC GUI window.

    The Tkinter import is deferred to call-time so the rest of this
    package can be imported headlessly (CI, doc builds) without a
    display being available.
    """
    from reasitic.gui.app import run as _run

    _run(tech_path=tech_path, session_path=session_path)
