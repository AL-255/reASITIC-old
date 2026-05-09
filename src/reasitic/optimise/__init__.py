"""Inductor-geometry optimisation and parameter sweeps.

Wraps :mod:`scipy.optimize` to maximise Q (or any user-supplied
objective) over the parameters of a given inductor topology
(currently square spirals; polygon spirals coming next), plus a
Cartesian sweep helper for design-space exploration.
"""

from reasitic.optimise.batch import batch_opt_square
from reasitic.optimise.opt_poly import (
    optimise_area_square_spiral,
    optimise_polygon_spiral,
    optimise_symmetric_square,
)
from reasitic.optimise.opt_sq import OptResult, optimise_square_spiral
from reasitic.optimise.sweep import (
    sweep_square_spiral,
    sweep_to_csv,
    sweep_to_tsv,
)

__all__ = [
    "OptResult",
    "batch_opt_square",
    "optimise_area_square_spiral",
    "optimise_polygon_spiral",
    "optimise_square_spiral",
    "optimise_symmetric_square",
    "sweep_square_spiral",
    "sweep_to_csv",
    "sweep_to_tsv",
]
