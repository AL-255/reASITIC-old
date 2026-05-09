"""``OptPoly`` and related optimisation drivers.

Extensions of :func:`reasitic.optimise.opt_sq.optimise_square_spiral`
to other inductor topologies. All use the same scipy SLSQP solver
and report the same :class:`OptResult` for uniformity.

Mirrors the binary's ``OptPoly`` (case 708), ``OptArea`` (case
706), ``OptSymSq`` (case 713), ``OptSymPoly`` (case 714).
"""

from __future__ import annotations

from collections.abc import Callable

import numpy as np
import scipy.optimize

from reasitic import (
    Shape,
    compute_self_inductance,
    metal_only_q,
    polygon_spiral,
    symmetric_square,
)
from reasitic.optimise.opt_sq import OptResult
from reasitic.tech import Tech


def optimise_polygon_spiral(
    tech: Tech,
    *,
    target_L_nH: float,
    freq_ghz: float,
    sides: int = 8,
    metal: int | str = 0,
    radius_bounds: tuple[float, float] = (50.0, 500.0),
    width_bounds: tuple[float, float] = (2.0, 30.0),
    spacing_bounds: tuple[float, float] = (1.0, 10.0),
    turns_bounds: tuple[float, float] = (1.0, 10.0),
    L_tolerance: float = 0.05,
) -> OptResult:
    """Maximise Q for an N-sided polygon spiral subject to an L target.

    Mirrors ``cmd_opt_l_poly`` (case 708).
    """

    def _build(x: np.ndarray) -> Shape:
        radius, width, spacing, turns = (float(v) for v in x)
        return polygon_spiral(
            "_optpoly",
            radius=radius,
            width=width,
            spacing=spacing,
            turns=turns,
            tech=tech,
            sides=sides,
            metal=metal,
        )

    return _slsqp_drive(
        _build,
        tech,
        target_L_nH=target_L_nH,
        freq_ghz=freq_ghz,
        bounds=[radius_bounds, width_bounds, spacing_bounds, turns_bounds],
        L_tolerance=L_tolerance,
        param_names=("radius", "width", "spacing", "turns"),
    )


def optimise_area_square_spiral(
    tech: Tech,
    *,
    target_L_nH: float,
    freq_ghz: float,
    metal: int | str = 0,
    length_bounds: tuple[float, float] = (50.0, 500.0),
    width_bounds: tuple[float, float] = (2.0, 30.0),
    spacing_bounds: tuple[float, float] = (1.0, 10.0),
    turns_bounds: tuple[float, float] = (1.0, 10.0),
    L_tolerance: float = 0.05,
) -> OptResult:
    """Minimise the chip-area footprint of a square spiral while
    meeting an L target.

    Mirrors ``cmd_opt_area`` (case 706). Optimises ``length²`` (the
    bounding-box area of the spiral) directly; the bias-balance with
    Q is not enforced.
    """
    from reasitic import square_spiral

    def _build(x: np.ndarray) -> Shape:
        length, width, spacing, turns = (float(v) for v in x)
        return square_spiral(
            "_optarea",
            length=length,
            width=width,
            spacing=spacing,
            turns=turns,
            tech=tech,
            metal=metal,
        )

    bounds = [length_bounds, width_bounds, spacing_bounds, turns_bounds]
    x0 = np.array([0.5 * (lo + hi) for (lo, hi) in bounds])

    def _area(x: np.ndarray) -> float:
        return float(x[0]) ** 2  # length² ≈ outer-box footprint

    def _l_lower(x: np.ndarray) -> float:
        sh = _build(x)
        return compute_self_inductance(sh) - target_L_nH * (1.0 - L_tolerance)

    def _l_upper(x: np.ndarray) -> float:
        sh = _build(x)
        return target_L_nH * (1.0 + L_tolerance) - compute_self_inductance(sh)

    result = scipy.optimize.minimize(
        _area,
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


def optimise_symmetric_square(
    tech: Tech,
    *,
    target_L_nH: float,
    freq_ghz: float,
    metal: int | str = 0,
    length_bounds: tuple[float, float] = (50.0, 500.0),
    width_bounds: tuple[float, float] = (2.0, 30.0),
    spacing_bounds: tuple[float, float] = (1.0, 10.0),
    turns_bounds: tuple[float, float] = (1.0, 10.0),
    L_tolerance: float = 0.05,
) -> OptResult:
    """``OptSymSq`` — symmetric centre-tapped square spiral."""

    def _build(x: np.ndarray) -> Shape:
        length, width, spacing, turns = (float(v) for v in x)
        return symmetric_square(
            "_optsymsq",
            length=length,
            width=width,
            spacing=spacing,
            turns=turns,
            tech=tech,
            metal=metal,
        )

    return _slsqp_drive(
        _build,
        tech,
        target_L_nH=target_L_nH,
        freq_ghz=freq_ghz,
        bounds=[length_bounds, width_bounds, spacing_bounds, turns_bounds],
        L_tolerance=L_tolerance,
        param_names=("length", "width", "spacing", "turns"),
    )


def _slsqp_drive(
    build_fn: Callable[[np.ndarray], Shape],
    tech: Tech,
    *,
    target_L_nH: float,
    freq_ghz: float,
    bounds: list[tuple[float, float]],
    L_tolerance: float,
    param_names: tuple[str, ...],
) -> OptResult:
    """Shared SLSQP driver for ``Q`` maximisation under an L
    constraint."""

    def _q_neg(x: np.ndarray) -> float:
        try:
            sh = build_fn(x)
            q = metal_only_q(sh, tech, freq_ghz)
        except (ValueError, ZeroDivisionError):
            return 1e6
        return -q

    def _l_lower(x: np.ndarray) -> float:
        sh = build_fn(x)
        return compute_self_inductance(sh) - target_L_nH * (1.0 - L_tolerance)

    def _l_upper(x: np.ndarray) -> float:
        sh = build_fn(x)
        return target_L_nH * (1.0 + L_tolerance) - compute_self_inductance(sh)

    x0 = np.array([0.5 * (lo + hi) for (lo, hi) in bounds])
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
    sh = build_fn(result.x)
    L = compute_self_inductance(sh)
    Q = metal_only_q(sh, tech, freq_ghz)
    # OptResult is fixed-shape (length, width, spacing, turns); for
    # OptPoly the first param is "radius" semantically — store it
    # in length_um and let the caller interpret via param_names if
    # they care.
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
