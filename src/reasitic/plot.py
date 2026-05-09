"""Plotting helpers (optional dependency on matplotlib).

If ``matplotlib`` isn't installed these functions raise a clear
``ImportError`` rather than the usual ModuleNotFoundError chain;
otherwise they return matplotlib ``Axes`` objects so callers can
further customise the plots.

The module itself imports lazily so just importing
``reasitic`` doesn't require matplotlib.
"""

from __future__ import annotations

from typing import Any

import numpy as np

from reasitic.geometry import Shape


def _require_matplotlib() -> Any:
    try:
        import matplotlib.pyplot as plt
    except ImportError as e:
        raise ImportError(
            "matplotlib is required for reasitic.plot — "
            "install with 'pip install matplotlib'"
        ) from e
    return plt


def plot_shape(shape: Shape, *, ax: Any = None, color: str | None = None) -> Any:
    """Plot a shape's polygons on the xy-plane.

    Returns the matplotlib Axes for further customisation.
    """
    plt = _require_matplotlib()
    if ax is None:
        _, ax = plt.subplots()
    for poly in shape.polygons:
        xs = [v.x for v in poly.vertices]
        ys = [v.y for v in poly.vertices]
        label = f"metal {poly.metal}" if color is None else None
        ax.plot(xs, ys, "-", color=color, label=label)
    ax.set_xlabel("x (μm)")
    ax.set_ylabel("y (μm)")
    ax.set_aspect("equal")
    ax.set_title(f"Shape <{shape.name}>")
    return ax


def plot_sweep(
    freqs_ghz: list[float],
    L_nH: list[float] | np.ndarray,
    R_ohm: list[float] | np.ndarray | None = None,
    Q: list[float] | np.ndarray | None = None,
    *,
    ax: Any = None,
) -> Any:
    """Plot a frequency sweep of L, R, Q vs freq.

    Pass any combination of L, R, Q; missing series are skipped.
    Returns the matplotlib Axes (twin x-axes used for L vs R/Q).
    """
    plt = _require_matplotlib()
    if ax is None:
        _, ax = plt.subplots()
    ax.plot(freqs_ghz, L_nH, "b-", label="L (nH)")
    ax.set_xlabel("Frequency (GHz)")
    ax.set_ylabel("L (nH)", color="b")
    if R_ohm is not None or Q is not None:
        ax2 = ax.twinx()
        if R_ohm is not None:
            ax2.plot(freqs_ghz, R_ohm, "r-", label="R (Ω)")
            ax2.set_ylabel("R (Ω)", color="r")
        if Q is not None:
            ax2.plot(freqs_ghz, Q, "g--", label="Q")
    return ax


def plot_lr_matrix(shape: Shape, *, ax: Any = None) -> Any:
    """Heat-map of the per-segment partial inductance matrix."""
    plt = _require_matplotlib()
    from reasitic.info import lr_matrix

    M = lr_matrix(shape)
    if ax is None:
        _, ax = plt.subplots()
    im = ax.imshow(M, cmap="RdBu_r", interpolation="nearest")
    ax.set_xlabel("segment j")
    ax.set_ylabel("segment i")
    ax.set_title(f"Partial L (nH) — <{shape.name}>")
    plt.colorbar(im, ax=ax)
    return ax
