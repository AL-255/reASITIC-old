"""Quality factor (Q) computation for an inductor.

Q is the ratio of imaginary to real part of the input impedance:

.. math::

    Q = \\frac{\\omega L}{R(\\omega)}

For a planar inductor on a lossy substrate the full Q-factor includes
substrate-loss contributions; this initial implementation gives the
metal-loss-only Q, which is the upper bound and the value the binary
prints as ``Q_metal`` for spirals far below their self-resonance.
"""

from __future__ import annotations

from reasitic.geometry import Shape
from reasitic.inductance import compute_self_inductance
from reasitic.resistance import compute_ac_resistance
from reasitic.tech import Tech
from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI


def metal_only_q(shape: Shape, tech: Tech, freq_ghz: float) -> float:
    """Metal-loss-only quality factor at ``freq_ghz``.

    Returns 0 if either L or R is non-positive (so the call is safe
    on degenerate geometries).
    """
    if freq_ghz <= 0:
        return 0.0
    L_nH = compute_self_inductance(shape)
    R_ohm = compute_ac_resistance(shape, tech, freq_ghz)
    if L_nH <= 0 or R_ohm <= 0:
        return 0.0
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ
    L_H = L_nH * NH_TO_H
    return omega * L_H / R_ohm
