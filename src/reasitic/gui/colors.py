"""Per-metal-layer color palette for the layout view.

The original ASITIC binary indexes metals by ``g_metal_layer_color_index``
(see ``decomp/output/asitic_repl.c`` line ~3427) and resolves each entry
through ``XParseColor`` against the X11 ``rgb.txt`` color database. Tech
files name each colour with an X11 colour string (``red``, ``blue``,
``greenish``, …); we re-use that mapping but normalise unusual names
(``greenish``, ``yellowish``…) to standard CSS hex codes that Tk
understands.
"""

from __future__ import annotations

from reasitic.tech import Tech

# Names the original tech files use that Tk doesn't recognise out of the
# box. Approximations chosen to match the look-and-feel of the original
# ASITIC palette as documented in run/doc/asitic_doc.html.
_NAME_NORMALISE: dict[str, str] = {
    "greenish": "#a8d8a8",
    "yellowish": "#d8d8a8",
    "blueish": "#a8a8d8",
    "redish": "#d8a8a8",
    "reddish": "#d8a8a8",
    "purplish": "#c8a8d8",
}

# Used when a Metal/Via has no colour at all
_DEFAULT_COLORS = (
    "#1f77b4", "#ff7f0e", "#2ca02c", "#d62728",
    "#9467bd", "#8c564b", "#e377c2", "#7f7f7f",
    "#bcbd22", "#17becf",
)


def normalize(name: str) -> str:
    """Return a Tk-acceptable colour string for an X11 colour name."""
    if not name:
        return "#888888"
    n = name.strip().lower()
    if n in _NAME_NORMALISE:
        return _NAME_NORMALISE[n]
    return n  # Tk understands "red", "blue", "#rgb", etc.


def metal_color(tech: Tech, metal_name: str) -> str:
    """Return the canvas colour for ``metal_name`` in ``tech``.

    Falls back to a deterministic palette entry keyed by index if the
    metal has no colour assigned.
    """
    for idx, m in enumerate(tech.metals):
        if m.name == metal_name:
            if m.color and m.color.lower() != "white":
                return normalize(m.color)
            return _DEFAULT_COLORS[idx % len(_DEFAULT_COLORS)]
    # Unknown metal — last resort
    return "#888888"


def via_color(tech: Tech, via_name: str) -> str:
    """Return the canvas colour for ``via_name`` in ``tech``."""
    for idx, v in enumerate(tech.vias):
        if v.name == via_name:
            if v.color and v.color.lower() != "white":
                return normalize(v.color)
            return _DEFAULT_COLORS[(idx + 5) % len(_DEFAULT_COLORS)]
    return "#bbbbbb"
