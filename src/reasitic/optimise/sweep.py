"""Parametric geometry sweep.

Mirrors the binary's ``Sweep`` / ``SweepMM`` commands (cases 711 /
715). Iterates a square-spiral builder over a Cartesian grid of
``(length, width, spacing, turns)`` values, computing the
inductance and metal-loss Q at each grid point. The result is a
NumPy structured array suitable for `numpy.savetxt` / pandas /
matplotlib.

Useful for quick design-space exploration: pick the corner of
parameter space that maximises Q while meeting an L target.
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from reasitic import compute_self_inductance, metal_only_q, square_spiral
from reasitic.tech import Tech

_SWEEP_DTYPE = np.dtype(
    [
        ("length_um", "f8"),
        ("width_um", "f8"),
        ("spacing_um", "f8"),
        ("turns", "f8"),
        ("L_nH", "f8"),
        ("Q", "f8"),
    ]
)


def sweep_square_spiral(
    tech: Tech,
    *,
    length_um: Iterable[float],
    width_um: Iterable[float],
    spacing_um: Iterable[float],
    turns: Iterable[float],
    freq_ghz: float,
    metal: int | str = 0,
) -> np.ndarray:
    """Cartesian sweep of square-spiral geometry → structured array.

    Returns an ``np.ndarray`` with dtype ``(length_um, width_um,
    spacing_um, turns, L_nH, Q)``. Bad geometries (where the inner
    radius collapses) appear with ``L_nH = NaN`` and ``Q = NaN``.
    """
    rows = []
    for L_val in length_um:
        for w in width_um:
            for s in spacing_um:
                for n in turns:
                    try:
                        sp = square_spiral(
                            "_sweep",
                            length=float(L_val),
                            width=float(w),
                            spacing=float(s),
                            turns=float(n),
                            tech=tech,
                            metal=metal,
                        )
                        L = compute_self_inductance(sp)
                        Q = metal_only_q(sp, tech, freq_ghz)
                    except (ValueError, ZeroDivisionError):
                        L, Q = float("nan"), float("nan")
                    rows.append((float(L_val), float(w), float(s), float(n), L, Q))
    return np.array(rows, dtype=_SWEEP_DTYPE)


def sweep_to_tsv(arr: np.ndarray) -> str:
    """Format a sweep result as TSV (tab-separated values)."""
    return _format_table(arr, sep="\t")


def sweep_to_csv(arr: np.ndarray) -> str:
    """Format a sweep result as CSV (comma-separated values).

    Loads directly into pandas via ``pd.read_csv(StringIO(s))``.
    """
    return _format_table(arr, sep=",")


def _format_table(arr: np.ndarray, *, sep: str) -> str:
    names = arr.dtype.names
    if names is None:
        raise ValueError("sweep array must be a structured ndarray")
    lines = [
        sep.join(names),
        *(sep.join(f"{row[name]:.6g}" for name in names) for row in arr),
    ]
    return "\n".join(lines) + "\n"
