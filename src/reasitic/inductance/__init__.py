"""Partial-inductance kernels."""

from reasitic.inductance.eddy import assemble_eddy_matrix, eddy_packed_index
from reasitic.inductance.filament import (
    Filament,
    auto_filament_subdivisions,
    auto_filament_subdivisions_critical,
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
from reasitic.inductance.matrix_fill import (
    FilamentList,
    build_filament_list,
    filament_list_setup,
    filament_pair_4corner_integration,
    fill_impedance_matrix_triangular,
    fill_inductance_diagonal,
    fill_inductance_offdiag,
)
from reasitic.inductance.partial import (
    compute_mutual_inductance,
    compute_self_inductance,
    coupling_coefficient,
)
from reasitic.inductance.skew import (
    mutual_inductance_3d_segments,
    mutual_inductance_axial_term,
    mutual_inductance_filament_kernel,
    mutual_inductance_orthogonal_segments,
    mutual_inductance_segment_kernel,
    mutual_inductance_skew_segments,
    wire_axial_separation,
    wire_separation_periodic,
)

__all__ = [
    "Filament",
    "FilamentList",
    "assemble_eddy_matrix",
    "auto_filament_subdivisions",
    "auto_filament_subdivisions_critical",
    "build_filament_list",
    "build_inductance_matrix",
    "build_resistance_vector",
    "compute_mutual_inductance",
    "compute_self_inductance",
    "coupled_wire_self_inductance",
    "coupling_coefficient",
    "eddy_packed_index",
    "filament_grid",
    "filament_list_setup",
    "filament_pair_4corner_integration",
    "fill_impedance_matrix_triangular",
    "fill_inductance_diagonal",
    "fill_inductance_offdiag",
    "hoer_love_perpendicular_mutual",
    "mohan_modified_wheeler",
    "mutual_inductance_3d_segments",
    "mutual_inductance_axial_term",
    "mutual_inductance_filament_kernel",
    "mutual_inductance_orthogonal_segments",
    "mutual_inductance_segment_kernel",
    "mutual_inductance_skew_segments",
    "parallel_segment_mutual",
    "perpendicular_segment_mutual",
    "rectangular_bar_self_inductance",
    "segment_self_inductance",
    "solve_inductance_matrix",
    "solve_inductance_mna",
    "wire_axial_separation",
    "wire_separation_periodic",
]
