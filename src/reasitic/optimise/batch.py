"""``BatchOpt`` — batch optimisation across multiple design points.

Run the per-point optimiser at every entry of a `(target_L_nH,
freq_ghz)` table, returning a NumPy structured array of best
geometries. Mirrors ``cmd_batchopt`` (case 707).
"""

from __future__ import annotations

from collections.abc import Iterable

import numpy as np

from reasitic.optimise.opt_sq import optimise_square_spiral
from reasitic.tech import Tech

_BATCH_DTYPE = np.dtype(
    [
        ("target_L_nH", "f8"),
        ("freq_ghz", "f8"),
        ("length_um", "f8"),
        ("width_um", "f8"),
        ("spacing_um", "f8"),
        ("turns", "f8"),
        ("L_nH", "f8"),
        ("Q", "f8"),
        ("success", "i1"),
    ]
)


def batch_opt_square(
    tech: Tech,
    *,
    targets: Iterable[tuple[float, float]],
    metal: int | str = 0,
) -> np.ndarray:
    """Run :func:`optimise_square_spiral` for each ``(L_nH, f_GHz)`` pair.

    Returns one row per target with the best geometry parameters,
    achieved L and Q, plus a success flag.
    """
    rows = []
    for target_L, f in targets:
        res = optimise_square_spiral(
            tech,
            target_L_nH=float(target_L),
            freq_ghz=float(f),
            metal=metal,
        )
        rows.append(
            (
                float(target_L),
                float(f),
                res.length_um,
                res.width_um,
                res.spacing_um,
                res.turns,
                res.L_nH,
                res.Q,
                int(res.success),
            )
        )
    return np.array(rows, dtype=_BATCH_DTYPE)
