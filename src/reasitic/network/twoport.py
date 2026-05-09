"""2-port network parameter conversions.

Mirrors the binary's Y/Z/S conversion machinery
(``y_to_z_2port_invert``, ``y_to_s_2port_50ohm`` in
``asitic_kernel.c``). Where the original keeps the parameters in
flat global cells, we use 2×2 NumPy complex arrays.

All matrices are indexed ``[port_i, port_j]`` (so ``Y[0][1]`` is
``Y_12``). Reference impedance defaults to **50 Ω** which matches
the binary's hardcoded ``Y_0 = 0.02 = 1/50``.

The Pi-equivalent representation models a planar inductor as a
series impedance ``Z_s`` between the two ports plus shunt
admittances ``Y_p1`` and ``Y_p2`` to ground:

::

    port1 ─┬─[ Z_s ]─┬─ port2
           │         │
          Y_p1     Y_p2
           │         │
          GND       GND

Conversion to Y::

    Y[0][0] = 1/Z_s + Y_p1
    Y[1][1] = 1/Z_s + Y_p2
    Y[0][1] = Y[1][0] = -1/Z_s

This is the same Pi extraction emitted by the binary's ``Pi`` /
``Pi2`` REPL commands (``cmd_pi3_emit``, ``analyze_narrow_band_2port``).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Shape
from reasitic.inductance import compute_self_inductance
from reasitic.resistance import compute_ac_resistance
from reasitic.tech import Tech
from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI

_Y0_DEFAULT = 0.02  # 1/50 Ω, matches the binary's hardcoded reference


def y_to_z(Y: np.ndarray) -> np.ndarray:
    """Invert a 2×2 admittance matrix to its impedance matrix.

    .. math::

        Z = Y^{-1} = \\frac{1}{\\det Y}
            \\begin{pmatrix} Y_{22} & -Y_{12} \\\\
                             -Y_{21} & Y_{11} \\end{pmatrix}

    Example:
        >>> import numpy as np
        >>> from reasitic.network import y_to_z
        >>> Y = np.diag([0.02 + 0j, 0.02 + 0j])
        >>> Z = y_to_z(Y)
        >>> round(Z[0, 0].real)
        50
    """
    if Y.shape != (2, 2):
        raise ValueError(f"expected 2x2 matrix, got {Y.shape}")
    det = Y[0, 0] * Y[1, 1] - Y[0, 1] * Y[1, 0]
    return np.array(
        [
            [Y[1, 1] / det, -Y[0, 1] / det],
            [-Y[1, 0] / det, Y[0, 0] / det],
        ],
        dtype=complex,
    )


def z_to_y(Z: np.ndarray) -> np.ndarray:
    """Inverse of :func:`y_to_z` — they share the same formula."""
    return y_to_z(Z)


def y_to_s(Y: np.ndarray, y0: float = _Y0_DEFAULT) -> np.ndarray:
    """Convert a 2-port Y matrix to a scattering matrix S.

    Reference admittance ``y0`` defaults to ``0.02`` (i.e. 50 Ω),
    matching the binary's hardcoded reference. The closed form is:

    .. math::

        S = (I + Y/Y_0)^{-1} (I - Y/Y_0)
    """
    if Y.shape != (2, 2):
        raise ValueError(f"expected 2x2 matrix, got {Y.shape}")
    eye = np.eye(2, dtype=complex)
    Yn = Y / y0
    return np.linalg.solve(eye + Yn, eye - Yn)


def s_to_y(S: np.ndarray, y0: float = _Y0_DEFAULT) -> np.ndarray:
    """Inverse of :func:`y_to_s`.

    .. math::

        Y = Y_0 (I - S)(I + S)^{-1}
    """
    if S.shape != (2, 2):
        raise ValueError(f"expected 2x2 matrix, got {S.shape}")
    eye = np.eye(2, dtype=complex)
    return np.asarray(y0 * np.linalg.solve(eye + S.T, (eye - S).T).T)


@dataclass
class PiModel:
    """Pi-equivalent of a 2-port network at one frequency.

    All quantities are complex except ``freq_ghz`` which is real. ``Z_s``
    is the series impedance between the ports (Ω); ``Y_p1`` and ``Y_p2``
    are shunt admittances to ground at ports 1 and 2 (S).
    """

    freq_ghz: float
    Z_s: complex
    Y_p1: complex
    Y_p2: complex


def pi_to_y(model: PiModel) -> np.ndarray:
    """Synthesise the 2×2 Y matrix from a Pi model."""
    if model.Z_s == 0:
        raise ValueError("Pi-model series impedance is zero")
    Yseries = 1.0 / model.Z_s
    return np.array(
        [
            [Yseries + model.Y_p1, -Yseries],
            [-Yseries, Yseries + model.Y_p2],
        ],
        dtype=complex,
    )


def pi_equivalent(Y: np.ndarray, freq_ghz: float) -> PiModel:
    """Extract the Pi-equivalent (Z_s, Y_p1, Y_p2) from a Y-matrix.

    .. math::
        Z_s = -1/Y_{12}, \\quad Y_{p1} = Y_{11} + Y_{12},
        \\quad Y_{p2} = Y_{22} + Y_{12}

    Two ports' shunt admittance is whatever each diagonal element
    has *in excess of* the through term. This is the same extraction
    the binary performs in ``extract_pi_equivalent``
    (``asitic_kernel.c:8945``).
    """
    if Y.shape != (2, 2):
        raise ValueError(f"expected 2x2 matrix, got {Y.shape}")
    Y12 = Y[0, 1]
    if Y12 == 0:
        raise ValueError("Y12 is zero, cannot invert")
    Z_s = -1.0 / Y12
    return PiModel(
        freq_ghz=freq_ghz,
        Z_s=Z_s,
        Y_p1=Y[0, 0] + Y12,
        Y_p2=Y[1, 1] + Y12,
    )


def deembed_pad_open(Y_meas: np.ndarray, Y_open: np.ndarray) -> np.ndarray:
    """De-embed shunt pad capacitance from measured Y using an
    open-only structure.

    Standard "open" de-embedding: the open structure's Y captures the
    pad shunts; subtract from the measured Y.

    .. math::

        Y_\\text{DUT} = Y_\\text{meas} - Y_\\text{open}

    Both arguments must be 2×2. Returns the de-embedded Y matrix.
    """
    if Y_meas.shape != (2, 2) or Y_open.shape != (2, 2):
        raise ValueError("both Y matrices must be 2x2")
    return np.asarray(Y_meas - Y_open, dtype=complex)


def deembed_pad_open_short(
    Y_meas: np.ndarray, Y_open: np.ndarray, Y_short: np.ndarray
) -> np.ndarray:
    """Open-then-short de-embedding: removes pad shunts (open) and
    series losses in the test-structure access lines (short).

    .. math::

        Y_\\text{DUT} = \\bigl[(Y_\\text{meas} - Y_\\text{open})^{-1}
                              - (Y_\\text{short} - Y_\\text{open})^{-1}
                       \\bigr]^{-1}

    All three matrices must be 2×2. Returns the de-embedded Y.
    """
    for name, M in (("meas", Y_meas), ("open", Y_open), ("short", Y_short)):
        if M.shape != (2, 2):
            raise ValueError(f"Y_{name} must be 2x2, got {M.shape}")
    Z_meas_open = np.linalg.inv(Y_meas - Y_open)
    Z_short_open = np.linalg.inv(Y_short - Y_open)
    return np.asarray(np.linalg.inv(Z_meas_open - Z_short_open), dtype=complex)


def z_2port_from_y(
    Y: np.ndarray,
    *,
    differential: bool = False,
    port: int = 1,
) -> complex:
    """Convert a 2-port Y matrix to a single complex impedance.

    Mirrors the binary's ``z_2port_from_y`` (decomp ``0x0804e8b0``):

    * Single-ended (``differential=False``):
        - ``port == 1`` → ``Z = 1 / Y[1, 1]`` (look into port 1 with
          port 2 short-circuited via Y inversion convention).
        - ``port != 1`` → ``Z = 1 / Y[0, 0]``.
    * Differential (``differential=True``) — the LC-mode impedance of
      a symmetric pair under ``Y[0,1] == Y[1,0]``:

      .. math::

          Z_d = (Y_{11} + Y_{22} + 2 Y_{21}) / (Y_{11} Y_{22} - Y_{21}^2)

    The binary's globals ``Y22_re/im`` correspond to ``Y[1, 1]`` and
    ``g_Y11_re/im`` to ``Y[0, 0]``; the matrix layout convention is the
    standard ``Y[i, j]`` indexing here.
    """
    if Y.shape != (2, 2):
        raise ValueError(f"expected 2x2 Y, got {Y.shape}")
    if differential:
        Y11 = Y[0, 0]
        Y22 = Y[1, 1]
        Y21 = Y[1, 0]
        det = Y11 * Y22 - Y21 * Y21
        num = Y11 + Y22 + 2.0 * Y21
        return complex(num / det)
    if port == 1:
        return complex(1.0 / Y[1, 1])
    return complex(1.0 / Y[0, 0])


def imag_z_2port_from_y(
    Y: np.ndarray,
    *,
    differential: bool = False,
    port: int = 1,
) -> float:
    """Imaginary part of :func:`z_2port_from_y`.

    Mirrors the binary's ``imag_z_2port_from_y`` (decomp
    ``0x0804e7c0``). Convenience wrapper that takes the imaginary
    component directly so callers extracting a reactance don't need
    to remember the indexing convention.
    """
    return float(z_2port_from_y(
        Y, differential=differential, port=port
    ).imag)


def zin_terminated_2port(
    Y: np.ndarray,
    Y_load: complex,
    *,
    port: int = 1,
) -> complex:
    """Input impedance with the *other* port terminated in admittance ``Y_load``.

    Mirrors the binary's ``zin_terminated_2port`` (decomp
    ``0x0804e9b0``). Implements the standard 2-port reduction
    identity::

        Y_in = Y_ii − Y_ij · Y_ji / (Y_jj + Y_load)
        Z_in = 1 / Y_in

    Unlike :func:`z_2port_from_y`, this routine reads ``Y[0, 1]``
    independently of ``Y[1, 0]`` — it does **not** assume reciprocity,
    matching the binary's only function in this group that pulls the
    Y12 slot separately.

    Args:
        Y:        2×2 admittance matrix.
        Y_load:   Load admittance terminating the *other* port.
        port:     Which port we're looking into (1 or 2).
    """
    if Y.shape != (2, 2):
        raise ValueError(f"expected 2x2 Y, got {Y.shape}")
    if port == 1:
        # Look into port 1; port 2 terminated by Y_load
        Y_in = Y[0, 0] - Y[0, 1] * Y[1, 0] / (Y[1, 1] + Y_load)
    else:
        # Look into port 2; port 1 terminated by Y_load
        Y_in = Y[1, 1] - Y[0, 1] * Y[1, 0] / (Y[0, 0] + Y_load)
    return complex(1.0 / Y_in)


def spiral_y_at_freq(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    y_p1: complex | None = None,
    y_p2: complex | None = None,
    include_substrate: bool = True,
) -> np.ndarray:
    """Build the 2-port Y matrix for ``shape`` at ``freq_ghz``.

    * ``y_p1`` / ``y_p2`` — explicit shunt admittances at port 1 / 2.
      Each defaults to ``None``, in which case the value is filled in
      from the substrate stub (or zero if ``include_substrate=False``).
    * ``include_substrate`` — when True (the default) and the user
      didn't pass an explicit shunt admittance, half of the substrate
      shunt capacitance from :func:`shape_shunt_capacitance` is
      attributed to each port (the standard Pi-model split).

    Series impedance is ``R(f) + jωL``. Substrate-loss conductance is
    not modelled in this stub.

    A Pi-aggregator on the per-segment Maxwell cap matrix is exposed
    separately as
    :func:`reasitic.substrate.shape_pi_capacitances`, but it routes
    through ``analyze_capacitance_driver`` whose underlying P matrix
    needs the substrate Green's-function rework in TODO.md §3 before
    its values are physically meaningful for spirals. Wiring the
    full ``analyze_narrow_band_2port`` path here is therefore gated
    on §3.
    """
    L_nH = compute_self_inductance(shape)
    R = compute_ac_resistance(shape, tech, freq_ghz)
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ
    Z_s = complex(R, omega * L_nH * NH_TO_H)
    if Z_s == 0:
        raise ValueError("series impedance is zero (zero L and zero R)")
    if (y_p1 is None or y_p2 is None) and include_substrate:
        # Avoid a circular import; reach for substrate only when needed.
        from reasitic.substrate import shape_shunt_capacitance

        C_total_F = shape_shunt_capacitance(shape, tech)
        # Standard Pi-split: each port carries half the shunt cap.
        Y_sub = 1j * omega * (C_total_F * 0.5)
    else:
        Y_sub = 0j
    if y_p1 is None:
        y_p1 = Y_sub
    if y_p2 is None:
        y_p2 = Y_sub
    return pi_to_y(PiModel(freq_ghz=freq_ghz, Z_s=Z_s, Y_p1=y_p1, Y_p2=y_p2))
