"""High-level 2-port analysis: Pi-model emission, self-resonance,
input impedance, eigen-frequency search.

These functions wrap the lower-level building blocks in
:mod:`reasitic.network.twoport` and the per-frequency
:func:`reasitic.network.spiral_y_at_freq` into the textual /
single-number outputs that the binary's REPL commands return.
"""

from __future__ import annotations

import math
from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Shape
from reasitic.network.twoport import (
    PiModel,
    pi_equivalent,
    spiral_y_at_freq,
    y_to_z,
)
from reasitic.tech import Tech
from reasitic.units import GHZ_TO_HZ, NH_TO_H, TWO_PI


@dataclass
class PiResult:
    """Pi-equivalent broken out as physical L/R/C values at one frequency.

    Mirrors the textual rows that the binary's ``Pi`` / ``Pi2``
    commands print: an inductance, a series resistance, two shunt
    capacitances. The conversion from Y/Z to (L, R, C) follows the
    standard inductor model: at the operating frequency,

    .. math::

        Z_s = R + j\\omega L,
        \\quad Y_p = j\\omega C  + g_p

    where ``g_p`` is the substrate-loss conductance (zero for our
    lossless-substrate stub).
    """

    freq_ghz: float
    L_nH: float
    R_series: float
    C_p1_fF: float
    C_p2_fF: float
    g_p1: float  # shunt conductance, port 1 (S)
    g_p2: float  # shunt conductance, port 2 (S)


def pi_model_at_freq(shape: Shape, tech: Tech, freq_ghz: float) -> PiResult:
    """Build the Pi-equivalent of ``shape`` at ``freq_ghz`` and break
    out the Z_s / Y_p values into physical L, R, C, g.

    Mirrors the binary's ``cmd_pi_emit`` and ``extract_pi_lumped_3port``
    (``asitic_kernel.c:8945`` / ``0x080897e4``).
    """
    if freq_ghz <= 0:
        raise ValueError("freq_ghz must be positive")
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ
    Y = spiral_y_at_freq(shape, tech, freq_ghz)
    pi: PiModel = pi_equivalent(Y, freq_ghz)
    R = float(pi.Z_s.real)
    L_H = float(pi.Z_s.imag) / omega
    L_nH = L_H / NH_TO_H
    g1 = float(pi.Y_p1.real)
    g2 = float(pi.Y_p2.real)
    C1 = float(pi.Y_p1.imag) / omega
    C2 = float(pi.Y_p2.imag) / omega
    return PiResult(
        freq_ghz=freq_ghz,
        L_nH=L_nH,
        R_series=R,
        C_p1_fF=C1 * 1.0e15,
        C_p2_fF=C2 * 1.0e15,
        g_p1=g1,
        g_p2=g2,
    )


def zin_terminated(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    z_load_ohm: complex = 50.0 + 0j,
) -> complex:
    """Input impedance at port 1 with port 2 terminated by ``z_load``.

    .. math::

        Z_{\\text{in}} = Z_{11} - \\frac{Z_{12} \\cdot Z_{21}}
                                       {Z_{22} + Z_L}

    Mirrors ``zin_terminated_2port`` (``asitic_kernel.c:0x0804e9b0``).
    """
    Y = spiral_y_at_freq(shape, tech, freq_ghz)
    with np.errstate(divide="ignore", invalid="ignore"):
        Z = y_to_z(Y)
    if not np.all(np.isfinite(Z)):
        raise ValueError("Z is singular at this frequency (lossless network)")
    Z11, Z12 = Z[0, 0], Z[0, 1]
    Z21, Z22 = Z[1, 0], Z[1, 1]
    return complex(Z11 - (Z12 * Z21) / (Z22 + z_load_ohm))


@dataclass
class Pi3Result:
    """3-port Pi-model with one ground spiral.

    ASITIC's Pi3 model (case 517) breaks a spiral + a separate
    ground spiral into a 3-port network. Ports 1, 2 are the
    inductor terminals; port 3 is a ground reference. The model
    captures the substrate-coupled paths from each terminal to the
    ground spiral.
    """

    freq_ghz: float
    L_series_nH: float
    R_series_ohm: float
    C_p1_to_gnd_fF: float
    C_p2_to_gnd_fF: float
    R_sub_p1_ohm: float
    R_sub_p2_ohm: float


@dataclass
class Pi4Result:
    """4-port Pi-model with two pads (case 518).

    Inductor + bond-pad on each port, sharing a substrate ground.
    Captures: series inductance + resistance, two pad capacitances
    to ground, two substrate resistances.
    """

    freq_ghz: float
    L_series_nH: float
    R_series_ohm: float
    C_pad1_fF: float
    C_pad2_fF: float
    C_sub1_fF: float
    C_sub2_fF: float
    R_sub1_ohm: float
    R_sub2_ohm: float


def pi3_model(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    ground_shape: Shape | None = None,
) -> Pi3Result:
    """Compute a 3-port Pi-model for ``shape`` with ``ground_shape``.

    Ports the simpler case of ``cmd_pi3_emit``
    (``asitic_repl.c:0x08050b2c``) where ground_shape is None: the
    substrate stub provides each port's coupling to ground via a
    capacitor and a substrate-loss resistance (the latter is zero
    in our lossless-substrate stub).

    When ``ground_shape`` is provided the symmetric case is
    handled by computing M(shape, ground_shape) as part of the
    series leg.
    """
    pi = pi_model_at_freq(shape, tech, freq_ghz)
    M_nH = 0.0
    if ground_shape is not None:
        from reasitic.inductance import compute_mutual_inductance

        M_nH = compute_mutual_inductance(shape, ground_shape)
    L_series = pi.L_nH - M_nH  # inductive de-embedding for ground spiral
    return Pi3Result(
        freq_ghz=freq_ghz,
        L_series_nH=L_series,
        R_series_ohm=pi.R_series,
        C_p1_to_gnd_fF=pi.C_p1_fF,
        C_p2_to_gnd_fF=pi.C_p2_fF,
        # Substrate-loss conductance → equivalent resistance: 1/g
        R_sub_p1_ohm=1.0 / pi.g_p1 if pi.g_p1 > 0 else float("inf"),
        R_sub_p2_ohm=1.0 / pi.g_p2 if pi.g_p2 > 0 else float("inf"),
    )


def pi4_model(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    pad1: Shape | None = None,
    pad2: Shape | None = None,
) -> Pi4Result:
    """4-port Pi-model with bond-pad capacitors on each port.

    Mirrors ``cmd_pi4_emit`` (``asitic_repl.c:0x08050d10``). The
    pad shunts add to each port's substrate path. Pads are typically
    a single MIM-capacitor block; their substrate cap from
    :func:`shape_shunt_capacitance` is added to the spiral's own
    port shunt cap.
    """
    from reasitic.substrate import shape_shunt_capacitance

    pi = pi_model_at_freq(shape, tech, freq_ghz)
    # Pad cap (per port). Each pad is just a metal patch; its
    # parallel-plate cap to ground is shape_shunt_capacitance.
    C_pad1 = (
        shape_shunt_capacitance(pad1, tech) * 1e15 if pad1 is not None else 0.0
    )
    C_pad2 = (
        shape_shunt_capacitance(pad2, tech) * 1e15 if pad2 is not None else 0.0
    )
    return Pi4Result(
        freq_ghz=freq_ghz,
        L_series_nH=pi.L_nH,
        R_series_ohm=pi.R_series,
        C_pad1_fF=C_pad1,
        C_pad2_fF=C_pad2,
        C_sub1_fF=pi.C_p1_fF,
        C_sub2_fF=pi.C_p2_fF,
        R_sub1_ohm=1.0 / pi.g_p1 if pi.g_p1 > 0 else float("inf"),
        R_sub2_ohm=1.0 / pi.g_p2 if pi.g_p2 > 0 else float("inf"),
    )


@dataclass
class PixResult:
    """Extended Pi-X model with substrate-loss conductance broken out.

    The standard ``PiResult`` lumps the substrate path into a single
    ``Y_p`` admittance. PiX expresses it as a series ``R_sub`` to a
    ``C_sub`` to ground, which better matches the physical substrate
    network::

        port ─┬─[ R_sub ]─[ C_sub ]─ gnd
              │
            (no direct cap to ground)

    The decomposition is ``Y_p = jωC_sub / (1 + jωR_sub C_sub)``;
    we extract C_sub from ``|Y_p|`` at low frequencies and use the
    remainder as the R_sub estimate.
    """

    freq_ghz: float
    L_nH: float
    R_series_ohm: float
    R_sub1_ohm: float
    R_sub2_ohm: float
    C_sub1_fF: float
    C_sub2_fF: float


def pix_model(shape: Shape, tech: Tech, freq_ghz: float) -> PixResult:
    """Extended Pi-X equivalent (case 538, ``PiX``).

    Mirrors ``cmd_pix_emit`` (``asitic_repl.c:0x080527a4``). Splits
    the substrate-cap shunt into a series R-C network for SPICE-style
    substrate models.
    """
    if freq_ghz <= 0:
        raise ValueError("freq_ghz must be positive")
    Y = spiral_y_at_freq(shape, tech, freq_ghz)
    pi: PiModel = pi_equivalent(Y, freq_ghz=freq_ghz)
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ

    def _split(Yp: complex) -> tuple[float, float]:
        """Decompose a shunt admittance Y_p into a series R-C network.

        Series R-C: ``1/Y_p = R + 1/(jωC)``. Real part of 1/Y_p is R;
        imaginary part is ``-1/(ωC)``.
        """
        if Yp == 0:
            return float("inf"), 0.0
        Z = 1.0 / Yp
        R = float(Z.real)
        C_inv = -float(Z.imag)  # = 1/(ωC)
        C = 1.0 / (omega * C_inv) if C_inv > 0 and omega > 0 else 0.0
        return R, C

    R1, C1 = _split(complex(pi.Y_p1))
    R2, C2 = _split(complex(pi.Y_p2))
    R_series = float(pi.Z_s.real)
    L_nH = float(pi.Z_s.imag) / omega / NH_TO_H if omega > 0 else 0.0
    return PixResult(
        freq_ghz=freq_ghz,
        L_nH=L_nH,
        R_series_ohm=R_series,
        R_sub1_ohm=R1,
        R_sub2_ohm=R2,
        C_sub1_fF=C1 * 1.0e15,
        C_sub2_fF=C2 * 1.0e15,
    )


@dataclass
class ShuntRResult:
    """Output of the ``ShuntR`` command."""

    freq_ghz: float
    R_p_ohm: float  # parallel-equivalent resistance
    Q: float  # ωL/R_series
    L_nH: float
    R_series_ohm: float


def shunt_resistance(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    differential: bool = False,
) -> ShuntRResult:
    """Parallel-equivalent resistance of a series RL circuit.

    Mirrors ``cmd_shuntr_compute`` (``asitic_repl.c:0x0804e354``).
    For a series ``R_s + jωL`` the equivalent parallel resistance
    is :math:`R_p = R_s (1 + Q^2)`. In differential mode the
    equivalent is the series across both arms, which doubles
    ``R_s`` and ``L`` for symmetric structures.

    Inputs:
        ``shape``: target spiral.
        ``tech``: technology stack.
        ``freq_ghz``: operating frequency.
        ``differential``: ``True`` for the ``S``-mode (single-ended)
        or ``D``-mode in the binary's command parsing.
    """
    from reasitic.inductance import compute_self_inductance
    from reasitic.resistance import compute_ac_resistance

    L_nH = compute_self_inductance(shape)
    R_s = compute_ac_resistance(shape, tech, freq_ghz)
    if differential:
        L_nH *= 2.0
        R_s *= 2.0
    if R_s <= 0:
        return ShuntRResult(
            freq_ghz=freq_ghz, R_p_ohm=float("inf"), Q=float("inf"), L_nH=L_nH, R_series_ohm=R_s
        )
    omega = TWO_PI * freq_ghz * GHZ_TO_HZ
    Q = omega * L_nH * NH_TO_H / R_s
    R_p = R_s * (1.0 + Q * Q)
    return ShuntRResult(
        freq_ghz=freq_ghz,
        R_p_ohm=R_p,
        Q=Q,
        L_nH=L_nH,
        R_series_ohm=R_s,
    )


@dataclass
class TransformerAnalysis:
    """Output of the ``CalcTrans`` command."""

    freq_ghz: float
    L_pri_nH: float
    L_sec_nH: float
    R_pri_ohm: float
    R_sec_ohm: float
    M_nH: float
    k: float
    n_turns_ratio: float
    Q_pri: float
    Q_sec: float


def calc_transformer(
    primary: Shape,
    secondary: Shape,
    tech: Tech,
    freq_ghz: float,
) -> TransformerAnalysis:
    """Analyse a transformer at one frequency.

    Mirrors ``cmd_calctrans_emit`` (``asitic_repl.c:0x08051280``).
    Computes per-coil L and R, the cross-mutual M, the coupling
    coefficient k = M / sqrt(L₁·L₂), the ideal turns ratio
    n = sqrt(L₁ / L₂), and the per-coil Q.
    """
    from reasitic.inductance import (
        compute_mutual_inductance,
        compute_self_inductance,
    )
    from reasitic.quality import metal_only_q
    from reasitic.resistance import compute_ac_resistance

    L1 = compute_self_inductance(primary)
    L2 = compute_self_inductance(secondary)
    R1 = compute_ac_resistance(primary, tech, freq_ghz)
    R2 = compute_ac_resistance(secondary, tech, freq_ghz)
    M = compute_mutual_inductance(primary, secondary)
    if L1 > 0 and L2 > 0:
        k = M / math.sqrt(L1 * L2)
        n = math.sqrt(L1 / L2)
    else:
        k = 0.0
        n = 1.0
    return TransformerAnalysis(
        freq_ghz=freq_ghz,
        L_pri_nH=L1,
        L_sec_nH=L2,
        R_pri_ohm=R1,
        R_sec_ohm=R2,
        M_nH=M,
        k=k,
        n_turns_ratio=n,
        Q_pri=metal_only_q(primary, tech, freq_ghz),
        Q_sec=metal_only_q(secondary, tech, freq_ghz),
    )


@dataclass
class SelfResonance:
    """Self-resonance scan result."""

    freq_ghz: float
    Q_at_resonance: float
    z11_imag_at_resonance: float
    converged: bool


def self_resonance(
    shape: Shape,
    tech: Tech,
    *,
    f_low_ghz: float = 0.1,
    f_high_ghz: float = 50.0,
    n_steps: int = 200,
) -> SelfResonance:
    """Find the lowest frequency at which Im(Z₁₁) changes sign.

    Below the self-resonance Z₁₁ is inductive (positive imag); at
    resonance it goes through zero and turns capacitive. We use a
    coarse linear scan + bisection refinement.

    Mirrors ``cmd_selfres_compute`` (``asitic_repl.c:0x0804e590``).
    Note: this requires non-zero shunt capacitance; on the lossless-
    substrate stub the spiral has Y_p = 0 and Z₁₁ = ∞, so
    self-resonance is undefined. Use a substrate model that yields
    realistic shunt caps before calling.
    """

    def z11_im(f: float) -> float:
        Y = spiral_y_at_freq(shape, tech, f)
        with np.errstate(divide="ignore", invalid="ignore"):
            Z = y_to_z(Y)
        if not np.all(np.isfinite(Z)):
            return float("inf")
        return float(Z[0, 0].imag)

    fs = np.linspace(f_low_ghz, f_high_ghz, n_steps)
    last_im = z11_im(float(fs[0]))
    for f_next in fs[1:]:
        cur = z11_im(float(f_next))
        if math.isfinite(last_im) and math.isfinite(cur) and last_im * cur < 0:
            # zero crossing between previous f and f_next
            lo, hi = float(f_next - (fs[1] - fs[0])), float(f_next)
            for _ in range(40):
                mid = 0.5 * (lo + hi)
                v = z11_im(mid)
                if not math.isfinite(v):
                    break
                if v * last_im < 0:
                    hi = mid
                else:
                    lo = mid
                    last_im = v
            f_res = 0.5 * (lo + hi)
            # Q at resonance is undefined for purely-real Z; report
            # the magnitude ratio of |Im(Y11)| / Re(Y11) at f just
            # below resonance as a proxy.
            from reasitic.quality import metal_only_q
            q = metal_only_q(shape, tech, max(f_res * 0.95, f_low_ghz))
            return SelfResonance(
                freq_ghz=f_res,
                Q_at_resonance=q,
                z11_imag_at_resonance=z11_im(f_res),
                converged=True,
            )
        last_im = cur
    # No crossing found — likely lossless-substrate (no shunt cap).
    return SelfResonance(
        freq_ghz=float("nan"),
        Q_at_resonance=0.0,
        z11_imag_at_resonance=z11_im(float(fs[-1])),
        converged=False,
    )
