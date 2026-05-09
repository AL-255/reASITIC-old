"""FFT-accelerated convolution of the substrate Green's function.

Mirrors the binary's ``fft_setup`` (``asitic_kernel.c:12026``,
``0x08091548``) and ``fft_apply_to_green``
(``asitic_kernel.c:11898``, ``0x080912c0``):

The static substrate Green's function ``G(ρ, z₁, z₂)`` only
depends on the *relative* lateral position of the two charge
sources. So coupled-capacitance evaluations between many
metal patches reduce to a 2-D convolution: the patch charge
density is convolved with G to give the potential, then sampled
at each patch centre. With FFT the convolution costs
``O(N_x N_y log(N_x N_y))`` regardless of the number of patches,
versus the per-pair ``O(N_pairs)`` of the direct loop.

This module sets up the precomputed ``G_grid`` on an ``N_x × N_y``
grid (matching the ``fftx`` / ``ffty`` fields in the tech file),
and provides a ``green_apply`` function that performs the
convolution using ``scipy.fft.fft2`` / ``ifft2``.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import scipy.fft

from reasitic.tech import Tech


@dataclass
class GreenFFTGrid:
    """Precomputed Green's-function FFT grid for one (z₁, z₂) pair.

    ``g_grid`` is the spatial-domain Green's function sampled on a
    centred ``(N_x, N_y)`` grid spanning ``(chip_x, chip_y)`` μm.
    ``g_fft`` is its 2-D FFT, ready for fast convolution.
    """

    nx: int
    ny: int
    chip_x_um: float
    chip_y_um: float
    z1_um: float
    z2_um: float
    g_grid: np.ndarray
    g_fft: np.ndarray


def setup_green_fft_grid(
    tech: Tech,
    *,
    z1_um: float,
    z2_um: float,
    nx: int | None = None,
    ny: int | None = None,
) -> GreenFFTGrid:
    """Precompute the substrate Green's function on a 2-D grid.

    The grid uses the ``chipx`` / ``chipy`` extents from the tech
    file by default; pass ``nx`` / ``ny`` to override (must be powers
    of 2 for fastest FFT). The resulting :class:`GreenFFTGrid` can
    be passed to :func:`green_apply` for fast batched evaluation.
    """
    if nx is None:
        nx = tech.chip.fftx if tech.chip.fftx > 0 else 64
    if ny is None:
        ny = tech.chip.ffty if tech.chip.ffty > 0 else 64
    chip_x = tech.chip.chipx if tech.chip.chipx > 0 else 512.0
    chip_y = tech.chip.chipy if tech.chip.chipy > 0 else 512.0
    dx = chip_x / nx
    dy = chip_y / ny

    # Build a centred-coordinate grid: ρ at index (i, j) is the
    # distance to the centre cell.
    ix = np.arange(nx) - nx // 2
    iy = np.arange(ny) - ny // 2
    xs = ix * dx
    ys = iy * dy
    xx, yy = np.meshgrid(xs, ys, indexing="ij")
    rho = np.sqrt(xx**2 + yy**2)

    # Vectorised Green's-function evaluation: same closed form as
    # green_function_static but applied to the whole rho grid at once.
    # Avoids the ~10 ms Python overhead of per-cell function calls.
    from reasitic.units import EPS_0, UM_TO_M

    rho_m = np.maximum(rho, 1.0) * UM_TO_M  # 1 μm regularising floor
    z1_m = z1_um * UM_TO_M
    z2_m = z2_um * UM_TO_M
    r_plus = np.sqrt(rho_m**2 + (z1_m - z2_m) ** 2)
    r_minus = np.sqrt(rho_m**2 + (z1_m + z2_m) ** 2)
    # Reflection coeff is rho-dependent through k_eff = 1/rho_m;
    # vectorise the recursive formula too.
    R_arr = np.zeros_like(rho_m)
    for k_eff in np.unique(1.0 / np.maximum(rho_m, 1e-30)):
        # Group rho_m cells by their k_eff and apply same R_stack
        from reasitic.substrate.green import _stack_reflection_coefficient
        mask = np.isclose(1.0 / np.maximum(rho_m, 1e-30), k_eff)
        R_arr[mask] = _stack_reflection_coefficient(tech, k_eff)
    g_grid = (1.0 / r_plus + R_arr / r_minus) / (4.0 * np.pi * EPS_0)

    g_fft = scipy.fft.fft2(g_grid)
    return GreenFFTGrid(
        nx=nx,
        ny=ny,
        chip_x_um=chip_x,
        chip_y_um=chip_y,
        z1_um=z1_um,
        z2_um=z2_um,
        g_grid=g_grid,
        g_fft=g_fft,
    )


def green_apply(grid: GreenFFTGrid, charge: np.ndarray) -> np.ndarray:
    """Convolve a charge-density grid with the precomputed Green's function.

    ``charge`` must be the same shape as ``grid.g_grid`` (``nx`` × ``ny``).
    Returns the resulting potential grid (in Volts if ``charge`` is in
    Coulombs and ``g_grid`` is in 1/(F·m)·m² = m/F... unit conversion
    is the caller's responsibility).
    """
    if charge.shape != grid.g_grid.shape:
        raise ValueError(
            f"charge shape {charge.shape} does not match grid shape "
            f"{grid.g_grid.shape}"
        )
    c_fft = scipy.fft.fft2(charge)
    pot = scipy.fft.ifft2(c_fft * grid.g_fft).real
    return np.asarray(pot)
