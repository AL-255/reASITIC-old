"""Filament discretisation and impedance-matrix-based L extraction.

The closed-form Greenhouse summation in :mod:`reasitic.inductance.partial`
treats every conductor as a single filament. For finite-width / finite-
thickness conductors at high frequency this misses current crowding
(skin and proximity effects). The original ASITIC binary handles this
by splitting each segment into ``N_w × N_t`` parallel filaments,
filling a complex impedance matrix ``Z = R + jωM``, and solving for the
per-filament currents under a unit-voltage excitation. The net
inductance follows from the parallel sum.

This module mirrors that pipeline at a Python level:

1. Subdivide each :class:`Segment` into ``n_w × n_t`` axial filaments
   (``filament_grid``).
2. Build the per-filament Z matrix:
     - Diagonal: ``R_i + jωL_self_i`` from the rectangular-bar formula.
     - Off-diagonal: ``jωM_ij`` from the parallel-segment Grover form
       for parallel filaments, 0 for perpendicular pairs.
3. Solve ``Z·I = V·1`` (uniform unit voltage), then ``L_eff =
   Im(V/I_total) / ω``.

Mirrors the binary's ``solve_inductance_matrix``
(``asitic_kernel.c:5687``, address ``0x08064360``) and
``set_cell_size_normal`` (``asitic_kernel.c:7602``,
``0x0807043c``).

The sub-filaments are *not* used for the closed-form Greenhouse path
in :func:`reasitic.inductance.compute_self_inductance`; that path
still treats each segment as one filament and is faster but less
accurate at high frequency.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Point, Segment, Shape
from reasitic.inductance.grover import (
    parallel_segment_mutual,
    rectangular_bar_self_inductance,
)
from reasitic.inductance.partial import _axis_of, _parallel_axis_pair
from reasitic.tech import Tech
from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI, UM_TO_CM


@dataclass
class Filament:
    """One sub-filament after discretising a :class:`Segment`."""

    a: Point
    b: Point
    width: float
    thickness: float
    metal: int
    parent_segment: int  # index into the original segment list


def auto_filament_subdivisions(
    segment: Segment,
    rsh_ohm_per_sq: float,
    freq_ghz: float,
    *,
    cells_per_skin_depth: float = 2.0,
    n_max: int = 8,
) -> tuple[int, int]:
    """Pick ``(n_w, n_t)`` so each filament is ≤ ``δ_skin / cells_per_skin_depth``.

    At the operating frequency ``freq_ghz`` and metal sheet resistance
    ``rsh``, computes the skin depth ``δ`` and returns subdivisions
    that keep every filament ≤ that fraction of δ. Capped at
    ``n_max`` to avoid runaway grid sizes.

    Returns ``(1, 1)`` at DC (freq_ghz ≤ 0).
    """
    if freq_ghz <= 0:
        return 1, 1
    from reasitic.resistance.skin import skin_depth

    # Effective bulk rho ≈ rsh × t (per metal layer)
    rho_si = max(rsh_ohm_per_sq * segment.thickness * 1e-6, 1e-12)
    rho_ohm_cm = rho_si * 100.0
    delta_m = skin_depth(rho_ohm_cm, freq_ghz * 1.0e9)
    delta_um = delta_m * 1.0e6
    target_um = delta_um / max(cells_per_skin_depth, 1.0)
    n_w = max(1, min(n_max, round(segment.width / target_um)))
    n_t = max(1, min(n_max, round(segment.thickness / target_um)))
    return n_w, n_t


def auto_filament_subdivisions_critical(
    segment: Segment,
    rsh_ohm_per_sq: float,
    freq_ghz: float,
    *,
    cells_per_skin_depth: float = 4.0,
    n_max: int = 16,
) -> tuple[int, int]:
    """Critical-mode filament subdivisions (finer than the normal mode).

    Mirrors ``set_cell_size_critical`` (decomp ``0x08071cec``, 3454 B):
    the binary's stricter cell-sizer for high-accuracy regimes.
    Same formula as :func:`auto_filament_subdivisions` but with
    twice the cells-per-skin-depth target (default 4× rather than
    2×) and a higher cap (``n_max=16`` rather than 8). The binary
    logs the result with a leading ``!#`` marker that routes the
    line to the per-spiral log file.

    Returns the ``(n_w, n_t)`` subdivision counts.
    """
    return auto_filament_subdivisions(
        segment, rsh_ohm_per_sq, freq_ghz,
        cells_per_skin_depth=cells_per_skin_depth,
        n_max=n_max,
    )


def filament_grid(segment: Segment, n_w: int = 1, n_t: int = 1) -> list[Filament]:
    """Split ``segment`` into a ``n_w × n_t`` grid of filaments.

    Each filament inherits the parent segment's length and direction;
    they're translated perpendicular to the segment axis to tile the
    cross-section. Width and thickness divide evenly.

    Returns at least one filament. Raises ``ValueError`` if either
    division count is non-positive.
    """
    if n_w <= 0 or n_t <= 0:
        raise ValueError("filament grid must have positive subdivisions")
    L = segment.length
    if L <= 0:
        return []
    # Unit vector along the segment
    ux, uy, uz = segment.direction
    # Build a perpendicular orthonormal basis (one in-plane, one out-of-plane).
    # For axis-aligned segments this is unambiguous.
    if abs(uz) < 1e-9:
        # In-plane segment: width is in (-uy, ux) direction; thickness is z.
        wx, wy, wz = -uy, ux, 0.0
        tx, ty, tz = 0.0, 0.0, 1.0
    else:
        # Vertical (via) segment: arbitrary perpendicular basis.
        wx, wy, wz = 1.0, 0.0, 0.0
        tx, ty, tz = 0.0, 1.0, 0.0
    fil_w = segment.width / n_w
    fil_t = segment.thickness / n_t
    out: list[Filament] = []
    for iw in range(n_w):
        # offset in the width direction, centred on segment axis
        off_w = (iw - (n_w - 1) * 0.5) * fil_w
        for it in range(n_t):
            off_t = (it - (n_t - 1) * 0.5) * fil_t
            cx = off_w * wx + off_t * tx
            cy = off_w * wy + off_t * ty
            cz = off_w * wz + off_t * tz
            a = Point(segment.a.x + cx, segment.a.y + cy, segment.a.z + cz)
            b = Point(segment.b.x + cx, segment.b.y + cy, segment.b.z + cz)
            out.append(
                Filament(
                    a=a,
                    b=b,
                    width=fil_w,
                    thickness=fil_t,
                    metal=segment.metal,
                    parent_segment=-1,  # caller fills this in
                )
            )
    return out


def _filament_to_segment(f: Filament) -> Segment:
    return Segment(a=f.a, b=f.b, width=f.width, thickness=f.thickness, metal=f.metal)


def _filament_self_l(f: Filament) -> float:
    L = math.sqrt(
        (f.b.x - f.a.x) ** 2 + (f.b.y - f.a.y) ** 2 + (f.b.z - f.a.z) ** 2
    )
    return rectangular_bar_self_inductance(L, f.width, f.thickness)


def _filament_pair_m(f_i: Filament, f_j: Filament) -> float:
    """Mutual inductance (nH) between two parallel filaments,
    or 0 if non-parallel. Used as the off-diagonal of M."""
    s_i = _filament_to_segment(f_i)
    s_j = _filament_to_segment(f_j)
    try:
        ax_i, _ = _axis_of(s_i)
    except ValueError:
        return 0.0
    pair = _parallel_axis_pair(s_i, s_j, ax_i)
    if pair is None:
        return 0.0
    L1, L2, sep, offset, sign = pair
    if sep < UM_TO_CM:  # ~1 nm — treat as singular
        return 0.0
    return sign * parallel_segment_mutual(L1, L2, sep, offset)


def build_inductance_matrix(filaments: list[Filament]) -> np.ndarray:
    """Build the symmetric N×N partial-inductance matrix in nH.

    Diagonal entries are per-filament self-inductances; off-diagonal
    entries are the signed Grover parallel-segment mutuals.
    """
    n = len(filaments)
    M = np.zeros((n, n))
    for i, fi in enumerate(filaments):
        M[i, i] = _filament_self_l(fi)
        for j in range(i + 1, n):
            mij = _filament_pair_m(fi, filaments[j])
            M[i, j] = mij
            M[j, i] = mij
    return M


def build_resistance_vector(
    filaments: list[Filament],
    tech: Tech,
    freq_ghz: float,
) -> np.ndarray:
    """Per-filament AC resistance, ready to fill the Z diagonal."""
    from reasitic.resistance.skin import ac_resistance_segment

    out = np.zeros(len(filaments))
    for i, f in enumerate(filaments):
        if f.metal < 0 or f.metal >= len(tech.metals):
            continue
        m = tech.metals[f.metal]
        L_um = math.sqrt(
            (f.b.x - f.a.x) ** 2 + (f.b.y - f.a.y) ** 2 + (f.b.z - f.a.z) ** 2
        )
        out[i] = ac_resistance_segment(
            length_um=L_um,
            width_um=f.width,
            thickness_um=f.thickness,
            rsh_ohm_per_sq=m.rsh,
            freq_ghz=freq_ghz,
        )
    return out


def solve_inductance_mna(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    n_w: int = 1,
    n_t: int = 1,
) -> tuple[float, float]:
    """Modified-nodal-analysis solve for net (L, R) of a series spiral.

    Topology (rigorous version):

    * The spiral is a single mesh: every parent segment carries the
      same total current ``I_spiral`` (chosen as 1 here).
    * Within parent ``p`` the ``n_par = n_w·n_t`` sub-filaments are
      in parallel: each carries some fraction ``i_k`` of ``I_spiral``,
      and they all share the parent's terminal voltage drop ``V_p``.

    For each parent we get ``n_par`` equations::

        Σ_{k in p} i_k = 1       (current-conservation)
        (Z i)_k1 - (Z i)_k = 0    for k = k2 ... kn_par
                                  (voltages must match at the parent's
                                   end nodes)

    where ``Z = diag(R) + jω M`` is the complex per-filament impedance
    matrix. Stacking these gives an ``N × N`` complex linear system
    in the filament currents. The total spiral impedance is then
    ``Z_eff = Σ_p V_p`` (with ``I_spiral = 1`` implicit).

    Mirrors ``solve_inductance_matrix`` (``0x08064360``) more
    accurately than the older ``solve_inductance_matrix`` Schur-
    complement method.
    """
    segs = shape.segments()
    if not segs:
        return 0.0, 0.0

    filaments: list[Filament] = []
    for idx, s in enumerate(segs):
        for f in filament_grid(s, n_w=n_w, n_t=n_t):
            f.parent_segment = idx
            filaments.append(f)
    if not filaments:
        return 0.0, 0.0

    n = len(filaments)
    n_seg = len(segs)
    M_nh = build_inductance_matrix(filaments)
    R_ohm = build_resistance_vector(filaments, tech, freq_ghz)
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ if freq_ghz > 0 else 0.0
    M_h = M_nh * NH_TO_H
    Z = np.diag(R_ohm).astype(complex) + 1j * omega * M_h

    # Build per-parent filament-index lists
    parent_indices: list[list[int]] = [[] for _ in range(n_seg)]
    for k, f in enumerate(filaments):
        parent_indices[f.parent_segment].append(k)

    # Assemble the constraint matrix A (n × n) and RHS b (n,)
    A = np.zeros((n, n), dtype=complex)
    b = np.zeros(n, dtype=complex)
    row = 0
    for idxs in parent_indices:
        if not idxs:
            continue
        # 1) Current-sum: Σ_k i_k = 1
        for k in idxs:
            A[row, k] = 1.0
        b[row] = 1.0
        row += 1
        # 2) Voltage-equality across the parent: V_kj = V_k0 (j ≥ 1)
        k0 = idxs[0]
        for kj in idxs[1:]:
            A[row, :] = Z[kj, :] - Z[k0, :]
            b[row] = 0.0
            row += 1

    if row != n:
        # Degenerate (e.g. zero-length segments); pad with identity
        for r in range(row, n):
            A[r, r] = 1.0

    # Solve for filament currents
    if omega == 0:
        # DC: the imaginary part of Z is zero; solve real system
        try:
            i_vec = np.linalg.solve(A.real, b.real).astype(complex)
        except np.linalg.LinAlgError:
            i_vec = np.linalg.lstsq(A.real, b.real, rcond=None)[0].astype(complex)
    else:
        try:
            i_vec = np.linalg.solve(A, b)
        except np.linalg.LinAlgError:
            i_vec = np.linalg.lstsq(A, b, rcond=None)[0]

    # Total voltage = sum of per-parent terminal voltages
    Z_total = 0j
    for idxs in parent_indices:
        if not idxs:
            continue
        # All filaments in parent p share V_p; pick the first
        k0 = idxs[0]
        Z_total += complex(np.dot(Z[k0, :], i_vec))

    R_eff = float(Z_total.real)
    L_eff_nH = float(Z_total.imag / omega / NH_TO_H) if omega > 0 else 0.0
    return L_eff_nH, R_eff


def solve_inductance_matrix(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    n_w: int = 1,
    n_t: int = 1,
) -> tuple[float, float]:
    """Filament-based solve for net (L, R) of a shape at one frequency.

    Returns ``(L_nH, R_ohm)``.

    Topology: the spiral is a single series chain of conductor
    segments. Within one parent segment the ``n_w × n_t``
    sub-filaments are in *parallel* (sharing the segment's voltage
    drop); across segments the parents are in *series* (sharing
    the spiral's terminal current). The net impedance is built by
    folding the per-filament Z matrix back through this topology.

    For ``n_w = n_t = 1`` this reduces to the closed-form Greenhouse
    summation and matches :func:`compute_self_inductance` exactly
    (within floating-point round-off).

    For higher subdivisions, the per-segment effective L includes
    proximity / current-crowding corrections via the parallel
    sharing inside each parent. Mirrors the binary's
    ``solve_inductance_matrix`` (``0x08064360``).
    """
    segs = shape.segments()
    if not segs:
        return 0.0, 0.0

    # Discretise
    filaments: list[Filament] = []
    for idx, s in enumerate(segs):
        for f in filament_grid(s, n_w=n_w, n_t=n_t):
            f.parent_segment = idx
            filaments.append(f)

    if not filaments:
        return 0.0, 0.0

    M_nh = build_inductance_matrix(filaments)
    R_ohm = build_resistance_vector(filaments, tech, freq_ghz)
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ if freq_ghz > 0 else 0.0
    M_h = M_nh * NH_TO_H
    Z = np.diag(R_ohm).astype(complex) + 1j * omega * M_h

    n_seg = len(segs)
    n_fil_per_seg = max(1, n_w * n_t)

    # Build the n_seg × n_filament incidence matrix A so that
    # I_filament = A.T @ I_segment / n_fil_per_seg (uniform sharing
    # within a parent segment). For the simple single-mesh case
    # (entire spiral one loop) every parent carries the same I_loop;
    # we represent that by setting all entries of A to 1.
    #
    # A[k, p] = 1 if filament k's parent is segment p, else 0.
    A = np.zeros((len(filaments), n_seg))
    for k, f in enumerate(filaments):
        A[k, f.parent_segment] = 1.0
    # Effective per-segment Z under the assumption that all filaments
    # of a parent share the parent's terminal voltage (parallel
    # sharing). This is a Schur-complement reduction of the full
    # filament Z matrix down to the per-segment level.
    #
    # Each parent's filaments form a sub-block of Z; the effective
    # parent impedance is the equivalent parallel impedance, which
    # for a symmetric block reduces to ``1 / sum(inv(Z_block))``.
    Z_eff_per_seg = np.zeros((n_seg, n_seg), dtype=complex)
    for p in range(n_seg):
        idx_p = np.where(A[:, p] > 0)[0]
        if len(idx_p) == 0:
            continue
        for q in range(n_seg):
            idx_q = np.where(A[:, q] > 0)[0]
            if len(idx_q) == 0:
                continue
            # Average the cross-block entries: this is what the
            # series-chain assumption (uniform current within each
            # parent) gives.
            block = Z[np.ix_(idx_p, idx_q)]
            Z_eff_per_seg[p, q] = block.mean() * len(idx_p) if p == q else block.mean()

    if n_fil_per_seg > 1:
        # Self-block diagonal correction: for a parent's own block we
        # want the parallel-equivalent impedance, not the mean × N.
        for p in range(n_seg):
            idx_p = np.where(A[:, p] > 0)[0]
            if len(idx_p) <= 1:
                continue
            Z_block = Z[np.ix_(idx_p, idx_p)]
            try:
                Y_block = np.linalg.inv(Z_block)
            except np.linalg.LinAlgError:
                continue
            # Parallel admittance of the block under uniform port
            # voltage = sum over all entries of Y_block.
            Y_par = complex(Y_block.sum())
            Z_eff_per_seg[p, p] = 1.0 / Y_par if Y_par != 0 else Z_eff_per_seg[p, p]

    # Total spiral impedance: series sum of per-segment effective
    # impedances. Each entry's row p, col q contributes once because
    # the spiral mesh visits each segment exactly once with sign +1.
    Z_total = complex(Z_eff_per_seg.sum())

    R_eff = float(Z_total.real)
    L_eff_nH = float(Z_total.imag / omega / NH_TO_H) if omega > 0 else 0.0
    return L_eff_nH, R_eff
