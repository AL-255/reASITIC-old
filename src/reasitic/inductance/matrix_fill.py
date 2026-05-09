"""Filament-list assembly and impedance-matrix fill helpers.

Mirrors the binary's matrix-fill cluster:

* ``filament_list_setup``  (decomp ``0x08064e20``)
* ``build_filament_list``  (``0x08064f6c``)
* ``fill_impedance_matrix_triangular`` (``0x080650d4``)
* ``fill_inductance_diagonal``  (``0x080655a4``)
* ``fill_inductance_offdiag``   (``0x080657b8``)
* ``filament_pair_4corner_integration`` (``0x08063654``)

The binary's pipeline:

1. ``build_filament_list`` walks the spiral's segment list and
   rounds each segment's ``(width, thickness)`` against the
   chip-grid resolution to pick per-segment ``(n_w, n_t)``
   subdivision counts.
2. ``filament_list_setup`` allocates the auxiliary index arrays
   the solver uses to walk the grid.
3. ``fill_inductance_diagonal`` fills ``Z_ii = R + jωL_self`` per
   filament tile.
4. ``fill_inductance_offdiag`` fills ``Z_ij = jωM_ij`` for every
   off-diagonal pair (the symmetric lower triangle, then mirrored).

The reasitic pipeline already does the same job via
:func:`reasitic.inductance.filament.build_inductance_matrix` plus
:func:`build_resistance_vector`. This module wraps those calls
under the binary's canonical names so callers can dispatch on the
same surface, and adds a triangular-fill flavour for symmetric
matrices.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Point, Segment, Shape
from reasitic.inductance.filament import (
    Filament,
    auto_filament_subdivisions,
    build_inductance_matrix,
    build_resistance_vector,
    filament_grid,
)
from reasitic.tech import Tech

# Auxiliary indices the solver needs to walk filament tiles ----------------


@dataclass
class FilamentList:
    """Flat filament list plus the auxiliary indices the solver uses.

    Mirrors the binary's combined output of ``build_filament_list`` +
    ``filament_list_setup``: both the filaments themselves *and* the
    metal-only / via partition that the inductance fill needs.

    Attributes:
        filaments:  Flat list of filaments across all segments.
        n_w:        Per-parent-segment width-subdivision count.
        n_t:        Per-parent-segment thickness-subdivision count.
        metal_indices:  Flat indices of filaments that lie on a metal
            layer (used by the diagonal fill).
        via_indices:    Flat indices of filaments that lie on a via
            (or above the top metal); these go into a separate fill
            in the binary, mirrored here for parity.
        total_size: ``len(filaments)``; equals ``Σ_i n_w_i × n_t_i``.
    """

    filaments: list[Filament]
    n_w: list[int]
    n_t: list[int]
    metal_indices: list[int]
    via_indices: list[int]
    total_size: int


def build_filament_list(
    shape: Shape,
    tech: Tech,
    *,
    freq_ghz: float = 0.0,
    n_w_max: int = 8,
    n_t_max: int = 8,
) -> FilamentList:
    """Allocate per-segment filaments for ``shape``.

    Mirrors ``build_filament_list`` (decomp ``0x08064f6c``). For each
    segment the auto-subdivider picks ``(n_w, n_t)`` from the metal
    sheet resistance + frequency, then ``filament_grid`` is invoked
    to produce the actual filaments.

    The metal-layer / via partition is captured up-front so the
    downstream diagonal-only / off-diagonal-only fills (mirroring
    the binary's ``fill_inductance_*`` pair) can address each block.
    """
    segments = shape.segments()
    if not segments:
        return FilamentList(
            filaments=[], n_w=[], n_t=[],
            metal_indices=[], via_indices=[],
            total_size=0,
        )
    n_metals = len(tech.metals)
    filaments: list[Filament] = []
    n_w_list: list[int] = []
    n_t_list: list[int] = []
    metal_idx: list[int] = []
    via_idx: list[int] = []
    for seg in segments:
        rsh = (
            tech.metals[seg.metal].rsh
            if 0 <= seg.metal < n_metals else 0.0
        )
        n_w_seg, n_t_seg = auto_filament_subdivisions(
            seg, rsh_ohm_per_sq=rsh, freq_ghz=freq_ghz,
            n_max=max(n_w_max, n_t_max),
        )
        n_w_seg = min(n_w_seg, n_w_max)
        n_t_seg = min(n_t_seg, n_t_max)
        flat = filament_grid(seg, n_w=n_w_seg, n_t=n_t_seg)
        n_w_list.append(n_w_seg)
        n_t_list.append(n_t_seg)
        for f in flat:
            flat_idx = len(filaments)
            filaments.append(f)
            if 0 <= f.metal < n_metals:
                metal_idx.append(flat_idx)
            else:
                via_idx.append(flat_idx)
    return FilamentList(
        filaments=filaments,
        n_w=n_w_list,
        n_t=n_t_list,
        metal_indices=metal_idx,
        via_indices=via_idx,
        total_size=len(filaments),
    )


def filament_list_setup(shape: Shape, tech: Tech, *,
                        freq_ghz: float = 0.0) -> FilamentList:
    """Sister to :func:`build_filament_list`.

    Mirrors ``filament_list_setup`` (decomp ``0x08064e20``). The
    binary splits filament construction (``build_filament_list``)
    from the auxiliary index-array setup (``filament_list_setup``);
    in our cleaner Python API both fall out of one pass, so this
    function is a thin alias kept for surface parity.
    """
    return build_filament_list(shape, tech, freq_ghz=freq_ghz)


# Impedance-matrix fill ---------------------------------------------------


def fill_inductance_diagonal(
    filaments: list[Filament],
    *,
    tech: Tech | None = None,
    freq_ghz: float = 0.0,
    omega_rad: float | None = None,
) -> np.ndarray:
    """Diagonal-only fill of the impedance matrix.

    Mirrors ``fill_inductance_diagonal`` (decomp ``0x080655a4``).
    Returns an ``N × N`` complex diagonal matrix with
    ``Z_ii = R_i + jωL_self_i``. Off-diagonal entries are zero.

    Args:
        filaments:  The flat filament list.
        tech:       Tech file. If ``None``, the resistive part is zero
                    (``R = 0``).
        freq_ghz:   AC frequency for the resistance term (skin-depth
                    correction).
        omega_rad:  Angular frequency for the ``jωL`` term. Defaults
                    to ``2π · freq_ghz · 10⁹`` if ``None``.
    """
    n = len(filaments)
    Z = np.zeros((n, n), dtype=complex)
    if n == 0:
        return Z
    if omega_rad is None:
        omega_rad = 2.0 * np.pi * freq_ghz * 1e9
    L_full = build_inductance_matrix(filaments)
    R = (
        build_resistance_vector(filaments, tech, freq_ghz)
        if tech is not None
        else np.zeros(n)
    )
    for i in range(n):
        Z[i, i] = complex(R[i], omega_rad * L_full[i, i] * 1e-9)
    return Z


def fill_inductance_offdiag(
    filaments: list[Filament],
    *,
    omega_rad: float = 0.0,
) -> np.ndarray:
    """Off-diagonal-only fill of the impedance matrix.

    Mirrors ``fill_inductance_offdiag`` (decomp ``0x080657b8``).
    Returns an ``N × N`` matrix with ``Z_ij = jωM_ij`` for all
    ``i ≠ j`` and zeros on the diagonal.
    """
    n = len(filaments)
    Z = np.zeros((n, n), dtype=complex)
    if n == 0:
        return Z
    L_full = build_inductance_matrix(filaments)
    for i in range(n):
        for j in range(n):
            if i == j:
                continue
            Z[i, j] = complex(0.0, omega_rad * L_full[i, j] * 1e-9)
    return Z


def fill_impedance_matrix_triangular(
    filaments: list[Filament],
    *,
    tech: Tech | None = None,
    freq_ghz: float = 0.0,
    omega_rad: float | None = None,
) -> np.ndarray:
    """Combined diagonal + symmetric impedance-matrix fill.

    Mirrors ``fill_impedance_matrix_triangular`` (decomp
    ``0x080650d4``): produces the dense impedance matrix
    ``Z = diag(R) + jωM`` exploiting the symmetry of ``M`` to
    halve the per-pair work in the binary. The Python version
    delegates to :func:`build_inductance_matrix`, which is already
    symmetric by construction.
    """
    n = len(filaments)
    Z = np.zeros((n, n), dtype=complex)
    if n == 0:
        return Z
    if omega_rad is None:
        omega_rad = 2.0 * np.pi * freq_ghz * 1e9
    L_full = build_inductance_matrix(filaments)
    R = (
        build_resistance_vector(filaments, tech, freq_ghz)
        if tech is not None
        else np.zeros(n)
    )
    Z = 1j * omega_rad * 1e-9 * L_full
    for i in range(n):
        Z[i, i] += R[i]
    return np.asarray(Z)


# Filament-pair 4-corner integration --------------------------------------


def filament_pair_4corner_integration(
    seg_a: Segment, seg_b: Segment,
) -> tuple[float, float, float, float]:
    """Four corner-pair distances between two segments, in **μm**.

    Mirrors ``filament_pair_4corner_integration`` (decomp
    ``0x08063654``): the binary's GMD-style integrator that uses
    the four endpoint-pair distances ``(a₁→b₁, a₁→b₂, a₂→b₁,
    a₂→b₂)`` and combines them via the Grover four-corner formula.

    We expose the four distances directly so callers can recombine
    them with whatever closed-form they need.

    Returns:
        ``(d_a1b1, d_a1b2, d_a2b1, d_a2b2)`` — the four corner-pair
        Euclidean distances in μm.
    """
    def _d(p: Point, q: Point) -> float:
        dx = q.x - p.x
        dy = q.y - p.y
        dz = q.z - p.z
        return float(np.sqrt(dx * dx + dy * dy + dz * dz))

    return (
        _d(seg_a.a, seg_b.a),
        _d(seg_a.a, seg_b.b),
        _d(seg_a.b, seg_b.a),
        _d(seg_a.b, seg_b.b),
    )
