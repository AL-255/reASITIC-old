"""AC resistance with skin-effect correction.

Mirrors the per-segment formula in ``compute_inductance_inner_kernel``
(``asitic_kernel.c:142``), which is the diagonal contribution to the
binary's impedance matrix. Despite the function name in the binary
the body computes an **AC resistance** — the inductance part lives
elsewhere.

The kernel uses Wheeler-style empirical fits in two regimes,
selected by a dimensionless skin parameter

.. math::

    \\xi = \\sqrt{\\,8\\pi \\, f_\\text{GHz}\\, W_\\text{cm} / \\rho_\\text{sh}\\,}

* ``ξ ≥ 2.5`` (high-frequency / well-developed skin effect):

  .. math::

      R(f) = R_\\mathrm{dc} \\cdot \\Bigl[
          0.0035 \\cdot u
          + \\frac{1.1147 + 1.2868\\,\\xi}{1.2296 + 1.287\\,\\xi^{3}}
          + \\frac{0.43093\\,\\xi}{1 + 0.041\\,(\\,W/T\\,)^{1.8}}
        \\Bigr]

  where ``u = (W/T)^{1.19}``.

* ``ξ < 2.5`` (low-frequency, slight correction):

  .. math::

      R(f) = R_\\mathrm{dc} \\cdot
             \\bigl(1 + 0.0122 \\cdot \\xi^{p}\\bigr)

  with ``p = 3 + 0.01·ξ²``.

The constants come straight from the decompiled output and trace to
the empirical fit Niknejad reports in the original ASITIC paper
(Niknejad & Meyer, "Analysis of Eddy-Current Losses Over Conductive
Substrates with Applications to Monolithic Inductors and
Transformers," IEEE Trans. MTT, 2001).
"""

from __future__ import annotations

import math

from reasitic.geometry import Shape
from reasitic.tech import Tech
from reasitic.units import EIGHT_PI, MU_0, UM_TO_CM


def skin_depth(rho_ohm_cm: float, freq_hz: float, mu_r: float = 1.0) -> float:
    """Return the classical skin depth in metres.

    .. math::

        \\delta = \\sqrt{\\rho / (\\pi\\, \\mu\\, f)}

    Inputs ``rho`` in Ω·cm, ``freq`` in Hz, ``mu_r`` dimensionless.
    """
    if freq_hz <= 0:
        return float("inf")
    rho_si = rho_ohm_cm * 1.0e-2  # Ω·cm → Ω·m
    return math.sqrt(rho_si / (math.pi * mu_r * MU_0 * freq_hz))


def ac_resistance_segment(
    *,
    length_um: float,
    width_um: float,
    thickness_um: float,
    rsh_ohm_per_sq: float,
    freq_ghz: float,
) -> float:
    """AC resistance of one straight rectangular segment, in Ω.

    Pure port of the metal-layer branch of
    ``compute_inductance_inner_kernel`` (``asitic_kernel.c:142``).
    The via branch is handled separately in :mod:`reasitic.resistance.dc`
    via the tech file's per-via R.
    """
    if length_um <= 0 or width_um <= 0 or rsh_ohm_per_sq <= 0:
        return 0.0
    L_cm = length_um * UM_TO_CM
    W_cm = width_um * UM_TO_CM
    R_dc = rsh_ohm_per_sq * L_cm / W_cm

    if freq_ghz <= 0 or thickness_um <= 0:
        return R_dc

    xi = math.sqrt(EIGHT_PI * freq_ghz * W_cm / rsh_ohm_per_sq)
    aspect = width_um / thickness_um  # W/T

    if xi >= 2.5:
        u = aspect**1.19
        v = aspect**1.8
        ratio = (
            0.0035 * u
            + (1.1147 + 1.2868 * xi) / (1.2296 + 1.287 * (xi**3))
            + (xi * 0.43093) / (1.0 + 0.041 * v)
        )
    else:
        # Low-freq branch from the binary's else arm.
        p = 3.0 + 0.01 * xi * xi
        ratio = 1.0 + 0.0122 * (xi**p)

    return float(R_dc * ratio)


def compute_ac_resistance(shape: Shape, tech: Tech, freq_ghz: float) -> float:
    """Total AC resistance of ``shape`` at ``freq_ghz``, in Ω.

    Sums :func:`ac_resistance_segment` over every segment using the
    metal layer's rsh and thickness from ``tech``.
    """
    total = 0.0
    for s in shape.segments():
        if s.metal < 0 or s.metal >= len(tech.metals):
            continue
        m = tech.metals[s.metal]
        total += ac_resistance_segment(
            length_um=s.length,
            width_um=s.width,
            thickness_um=m.t,
            rsh_ohm_per_sq=m.rsh,
            freq_ghz=freq_ghz,
        )
    return total
