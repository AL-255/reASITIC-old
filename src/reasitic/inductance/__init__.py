"""Partial-inductance kernels."""

from reasitic.inductance.filament import (
    Filament,
    auto_filament_subdivisions,
    build_inductance_matrix,
    build_resistance_vector,
    filament_grid,
    solve_inductance_matrix,
    solve_inductance_mna,
)
from reasitic.inductance.grover import (
    coupled_wire_self_inductance,
    hoer_love_perpendicular_mutual,
    mohan_modified_wheeler,
    parallel_segment_mutual,
    perpendicular_segment_mutual,
    rectangular_bar_self_inductance,
    segment_self_inductance,
)
from reasitic.inductance.partial import (
    compute_mutual_inductance,
    compute_self_inductance,
    coupling_coefficient,
)

__all__ = [
    "Filament",
    "auto_filament_subdivisions",
    "build_inductance_matrix",
    "build_resistance_vector",
    "compute_mutual_inductance",
    "compute_self_inductance",
    "coupled_wire_self_inductance",
    "coupling_coefficient",
    "filament_grid",
    "hoer_love_perpendicular_mutual",
    "mohan_modified_wheeler",
    "parallel_segment_mutual",
    "perpendicular_segment_mutual",
    "rectangular_bar_self_inductance",
    "segment_self_inductance",
    "solve_inductance_matrix",
    "solve_inductance_mna",
]
