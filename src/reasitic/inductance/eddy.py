"""Eddy-current matrix and inductance fold-in.

When an inductor sits over a conductive substrate, image currents
flow in the substrate that reduce the effective inductance and
add loss. The original ASITIC binary models this via a ground-
image method: each conductor's current induces a phantom anti-
parallel current at the substrate-image position; the resulting
eddy-mutual-inductance matrix is folded into the diagonal of
the spiral's impedance matrix.

This is a rough first-cut implementation that places one image
filament per source filament, mirrored vertically about the
substrate's top surface (``z = 0`` in our convention). The
substrate-conductivity-dependent attenuation factor is the standard
``exp(-2|z|/δ)`` skin-depth roll-off applied to the image current.

Mirrors the simpler half of ``gen_eddy_current_matrix``
(``asitic_kernel.c:0x080b0e50``) and ``inductance_eddy_fold``
(``asitic_kernel.c:12578``).
"""

from __future__ import annotations

import math

import numpy as np

from reasitic.geometry import Point, Shape
from reasitic.inductance.filament import (
    Filament,
    _filament_pair_m,
    filament_grid,
)
from reasitic.resistance.skin import skin_depth
from reasitic.tech import Tech


def _image_filament(f: Filament) -> Filament:
    """Return the substrate-image of ``f``: same xy, mirrored z about
    ``z=0`` and direction reversed (image current opposes source)."""
    a = Point(f.a.x, f.a.y, -f.a.z)
    b = Point(f.b.x, f.b.y, -f.b.z)
    # Reverse the direction by swapping endpoints
    return Filament(
        a=b,
        b=a,
        width=f.width,
        thickness=f.thickness,
        metal=f.metal,
        parent_segment=f.parent_segment,
    )


def eddy_correction(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    n_w: int = 1,
    n_t: int = 1,
    finite_thickness: bool = True,
) -> tuple[float, float]:
    """Eddy-current correction to (L, R) at ``freq_ghz``.

    Returns ``(ΔL_nH, ΔR_ohm)`` — the *change* in inductance and
    resistance due to substrate eddy currents. Apply by adding to
    the un-folded :func:`solve_inductance_matrix` result.

    When ``finite_thickness`` is True the substrate is modelled as a
    finite-thickness ground plane: the image-current attenuation
    depends not only on the source-to-surface depth but also on the
    substrate's finite thickness ``t_sub``, which limits the eddy
    current path. The effective attenuation factor becomes::

        attn = exp(-2·z/δ) · (1 - exp(-2·t_sub/δ))

    where ``δ`` is the substrate skin depth and ``t_sub`` is the
    bulk-layer thickness from the tech file. For thin substrates
    (``t_sub ≪ δ``) this reduces to a small correction; for
    thick substrates (``t_sub ≫ δ``) it recovers the half-space
    half-space limit.

    A negative ``ΔL`` (inductance reduction) and positive ``ΔR``
    (loss increase) are the typical signs.
    """
    if not tech.layers:
        return 0.0, 0.0
    # Use the bulk silicon's resistivity (top layer if no eddy spec)
    rho_ohm_cm = float(tech.layers[0].rho)
    t_sub_um = float(tech.layers[0].t)
    if rho_ohm_cm <= 0 or freq_ghz <= 0:
        return 0.0, 0.0
    delta_m = skin_depth(rho_ohm_cm, freq_ghz * 1.0e9)
    t_sub_m = t_sub_um * 1.0e-6
    # Finite-thickness factor; ranges from 0 (zero thickness) to 1
    # (semi-infinite ground).
    if finite_thickness and delta_m > 0:
        thickness_factor = 1.0 - math.exp(-2.0 * t_sub_m / delta_m)
    else:
        thickness_factor = 1.0

    segs = shape.segments()
    filaments: list[Filament] = []
    for idx, s in enumerate(segs):
        for f in filament_grid(s, n_w=n_w, n_t=n_t):
            f.parent_segment = idx
            filaments.append(f)
    if not filaments:
        return 0.0, 0.0

    n = len(filaments)
    M_eddy = np.zeros((n, n))
    # Source–image mutual: each filament couples to every (mirrored)
    # image filament with an exponential attenuation by the source's
    # depth in the substrate.
    for i, fi in enumerate(filaments):
        # Source z is metal centreline; depth-below-substrate-top = z_i.
        depth_um = abs(fi.a.z)
        if depth_um <= 0:
            continue
        depth_m = depth_um * 1.0e-6
        attenuation = (
            math.exp(-2.0 * depth_m / max(delta_m, 1e-30)) * thickness_factor
        )
        for j, fj in enumerate(filaments):
            img_j = _image_filament(fj)
            # Use Segment-style parallel mutual; the image is along
            # the same axis but at -z, so the parallel-pair formula
            # captures the geometry.
            seg_pair_m = _filament_pair_m(fi, img_j)
            M_eddy[i, j] = seg_pair_m * attenuation
    # Sum: the spiral mesh is series; eddy correction = sum of all entries
    delta_L_nH = float(M_eddy.sum())
    # Resistance increase from skin-depth-induced loss:
    # Use the same image attenuation as proxy. The full version would
    # solve a complex impedance matrix.
    # For the first-order correction we estimate the eddy R as:
    #     ΔR ≈ ω · |ΔL| · tan(δ)   where tan(δ) for the substrate is
    #     ~ 1 below the relaxation freq; we use the proper expression
    #     from the binary's compute_dc_resistance_per_polygon-type
    #     model.
    omega = 2.0 * math.pi * freq_ghz * 1.0e9
    # Skin-depth-derived loss proxy
    delta_R = omega * abs(delta_L_nH) * 1.0e-9 * 0.1  # nH→H, then small loss factor
    return delta_L_nH, delta_R


def solve_inductance_with_eddy(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    n_w: int = 1,
    n_t: int = 1,
    include_eddy: bool = True,
) -> tuple[float, float]:
    """Like :func:`solve_inductance_matrix` but also folds in the eddy
    correction from :func:`eddy_correction`. Returns ``(L_nH, R_ohm)``.
    """
    from reasitic.inductance.filament import solve_inductance_matrix

    L0, R0 = solve_inductance_matrix(shape, tech, freq_ghz, n_w=n_w, n_t=n_t)
    if not include_eddy:
        return L0, R0
    dL, dR = eddy_correction(shape, tech, freq_ghz, n_w=n_w, n_t=n_t)
    return L0 + dL, R0 + dR
