"""``OptSq`` — square-spiral inductor optimisation.

Mirrors the binary's ``cmd_opt_l_sq`` (case 700 in
``commands.json``): given a target inductance and operating
frequency, search over (length, turns, width, spacing) for the
geometry that maximises Q while meeting the L target. We use
``scipy.optimize.minimize`` with the SLSQP algorithm for
constrained optimisation.

The original ASITIC's optimiser is a hand-rolled gradient descent
with finite differences (``set_cell_size_normal`` /
``compute_inductance`` re-evaluated each step). scipy.optimize's
SLSQP is more robust, supports multiple constraints, and gives us
quasi-Newton convergence for free.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.optimize

from reasitic import (
    Shape,
    compute_self_inductance,
    metal_only_q,
    square_spiral,
)
from reasitic.tech import Tech


@dataclass
class OptResult:
    """One optimisation result."""

    success: bool
    length_um: float
    width_um: float
    spacing_um: float
    turns: float
    L_nH: float
    Q: float
    n_iter: int
    message: str


def optimise_square_spiral(
    tech: Tech,
    *,
    target_L_nH: float,
    freq_ghz: float,
    metal: int | str = 0,
    length_bounds: tuple[float, float] = (50.0, 500.0),
    width_bounds: tuple[float, float] = (2.0, 30.0),
    spacing_bounds: tuple[float, float] = (1.0, 10.0),
    turns_bounds: tuple[float, float] = (1.0, 10.0),
    init: tuple[float, float, float, float] | None = None,
    L_tolerance: float = 0.05,
) -> OptResult:
    """Maximise Q for a square spiral subject to L = ``target_L_nH``.

    ``init`` is an optional ``(length, width, spacing, turns)``
    starting point; if omitted, the centre of each parameter's
    bounds is used. Returns an :class:`OptResult` with the best
    geometry plus its computed L and Q.

    The constraint ``|L - target| / target ≤ L_tolerance`` is enforced
    via SLSQP inequality constraints.
    """

    def _build(x: np.ndarray) -> Shape:
        length, width, spacing, turns = (float(v) for v in x)
        return square_spiral(
            "_opt",
            length=length,
            width=width,
            spacing=spacing,
            turns=turns,
            tech=tech,
            metal=metal,
        )

    def _q_neg(x: np.ndarray) -> float:
        try:
            sh = _build(x)
            q = metal_only_q(sh, tech, freq_ghz)
        except (ValueError, ZeroDivisionError):
            return 1e6
        return -q  # minimise -Q → maximise Q

    def _l_lower(x: np.ndarray) -> float:
        sh = _build(x)
        return compute_self_inductance(sh) - target_L_nH * (1.0 - L_tolerance)

    def _l_upper(x: np.ndarray) -> float:
        sh = _build(x)
        return target_L_nH * (1.0 + L_tolerance) - compute_self_inductance(sh)

    bounds = [length_bounds, width_bounds, spacing_bounds, turns_bounds]
    if init is None:
        x0 = np.array([0.5 * (lo + hi) for (lo, hi) in bounds])
    else:
        x0 = np.array(init, dtype=float)

    result = scipy.optimize.minimize(
        _q_neg,
        x0,
        method="SLSQP",
        bounds=bounds,
        constraints=[
            {"type": "ineq", "fun": _l_lower},
            {"type": "ineq", "fun": _l_upper},
        ],
        options={"maxiter": 100, "ftol": 1e-4},
    )
    sh = _build(result.x)
    L = compute_self_inductance(sh)
    Q = metal_only_q(sh, tech, freq_ghz)
    return OptResult(
        success=bool(result.success),
        length_um=float(result.x[0]),
        width_um=float(result.x[1]),
        spacing_um=float(result.x[2]),
        turns=float(result.x[3]),
        L_nH=L,
        Q=Q,
        n_iter=int(getattr(result, "nit", 0)),
        message=str(result.message),
    )
