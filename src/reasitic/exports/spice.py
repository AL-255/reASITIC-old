"""SPICE-style sub-circuit emitter.

Renders a Pi-equivalent inductor model as an Ngspice/HSPICE
``.subckt`` block:

::

    .subckt L1_pi p1 p2 gnd
    Rseries p1 nA  R={R_series}
    Lseries nA p2  L={L_series_nH}n
    Cp1 p1 gnd C={C_p1_fF}f
    Cp2 p2 gnd C={C_p2_fF}f
    .ends

The model is single-frequency (taken from the Pi-extraction at
the chosen analysis frequency). For broadband fitting use
multiple sub-circuits at different frequencies.

Mirrors the ``2Port`` ``S|Y|PI`` text output but in a more
useful interchange form for SPICE-flavour simulators.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from reasitic.geometry import Shape
from reasitic.network.analysis import pi_model_at_freq
from reasitic.tech import Tech


def write_spice_subckt(
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    name: str | None = None,
) -> str:
    """Emit a SPICE ``.subckt`` block for ``shape`` at ``freq_ghz``."""
    pi = pi_model_at_freq(shape, tech, freq_ghz)
    sub_name = (name or shape.name) + "_pi"
    out = StringIO()
    out.write(
        f"* reASITIC SPICE Pi-model for <{shape.name}> at {freq_ghz:g} GHz\n"
    )
    out.write(f".subckt {sub_name} p1 p2 gnd\n")
    out.write(f"Rseries p1 nA  {pi.R_series:.6g}\n")
    out.write(f"Lseries nA p2  {pi.L_nH:.6g}n\n")
    out.write(f"Cp1 p1 gnd  {pi.C_p1_fF:.6g}f\n")
    out.write(f"Cp2 p2 gnd  {pi.C_p2_fF:.6g}f\n")
    if pi.g_p1 > 0:
        out.write(f"Rsub1 p1 gnd  {1.0 / pi.g_p1:.6g}\n")
    if pi.g_p2 > 0:
        out.write(f"Rsub2 p2 gnd  {1.0 / pi.g_p2:.6g}\n")
    out.write(".ends\n")
    return out.getvalue()


def write_spice_subckt_file(
    path: str | Path,
    shape: Shape,
    tech: Tech,
    freq_ghz: float,
    *,
    name: str | None = None,
) -> None:
    """Write the SPICE sub-circuit to ``path``."""
    Path(path).write_text(write_spice_subckt(shape, tech, freq_ghz, name=name))


def write_spice_broadband(
    shape: Shape,
    tech: Tech,
    freqs_ghz: list[float],
    *,
    name: str | None = None,
) -> str:
    """Emit a frequency-dependent SPICE model.

    Each frequency in ``freqs_ghz`` produces a separate ``.subckt``
    block named ``<shape>_pi_<f_GHz>``. Useful when a single Pi-model
    isn't enough — pair with a SPICE ``.alter`` or per-band selection.
    """
    out: list[str] = []
    for f in freqs_ghz:
        sub_name = (name or shape.name) + f"_pi_{f:g}GHz"
        out.append(write_spice_subckt(shape, tech, f, name=sub_name))
    return "\n".join(out)


def write_spice_broadband_file(
    path: str | Path,
    shape: Shape,
    tech: Tech,
    freqs_ghz: list[float],
    *,
    name: str | None = None,
) -> None:
    """Write the broadband SPICE rendering to ``path``."""
    Path(path).write_text(write_spice_broadband(shape, tech, freqs_ghz, name=name))
