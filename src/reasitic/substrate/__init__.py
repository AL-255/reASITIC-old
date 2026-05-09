"""Substrate model.

Two implementations live here:

* :mod:`shunt` — parallel-plate per-metal-layer cap with edge fringe.
  Fast, used by default in :func:`reasitic.network.spiral_y_at_freq`.
* :mod:`green` — multi-layer Sommerfeld Green's function (quasi-static
  limit) with optional Bessel-J0 numerical integration via
  :func:`scipy.integrate.quad`. Slower but captures the full layered-
  stack reflection coefficient.

The full FFT-based Green's function (binary's ``compute_green_function``
at ``asitic_kernel.c:9212``) is functionally replaced by
``substrate.green.integrate_green_kernel`` for per-pair queries.
"""

from reasitic.substrate.coupled import (
    HJCoupledCaps,
    coupled_microstrip_caps_hj,
    coupled_microstrip_to_cap_matrix,
    even_odd_impedances,
)
from reasitic.substrate.fft_grid import (
    GreenFFTGrid,
    green_apply,
    setup_green_fft_grid,
)
from reasitic.substrate.green import (
    coupled_capacitance_per_pair,
    green_function_static,
    integrate_green_kernel,
    layer_reflection_coefficient,
    propagation_constant,
)
from reasitic.substrate.shunt import (
    parallel_plate_cap_per_area,
    shape_shunt_capacitance,
)

__all__ = [
    "GreenFFTGrid",
    "HJCoupledCaps",
    "coupled_capacitance_per_pair",
    "coupled_microstrip_caps_hj",
    "coupled_microstrip_to_cap_matrix",
    "even_odd_impedances",
    "green_apply",
    "green_function_static",
    "integrate_green_kernel",
    "layer_reflection_coefficient",
    "parallel_plate_cap_per_area",
    "propagation_constant",
    "setup_green_fft_grid",
    "shape_shunt_capacitance",
]
