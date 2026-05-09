"""Aggregate inductor figures-of-merit at one or more frequencies.

A ``DesignReport`` collects everything you'd typically want to know
about a spiral inductor before committing it to a design: DC and
AC resistance, inductance, coupling-only Q, parallel-equivalent
resistance, substrate cap, self-resonance frequency, and the full
Pi-model parameters at each requested frequency.

Useful as a one-shot CLI / script entry point:

::

    from reasitic import parse_tech_file, square_spiral
    from reasitic.report import design_report

    tech = parse_tech_file("BiCMOS.tek")
    sp = square_spiral("L1", length=200, width=10, spacing=2,
                        turns=3, tech=tech, metal="m3")
    rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
    print(rpt.format_text())
"""

from __future__ import annotations

from dataclasses import dataclass, field
from io import StringIO

from reasitic.geometry import Shape
from reasitic.inductance import compute_self_inductance
from reasitic.network.analysis import (
    Pi3Result,
    PiResult,
    SelfResonance,
    pi3_model,
    pi_model_at_freq,
    self_resonance,
)
from reasitic.quality import metal_only_q
from reasitic.resistance import compute_ac_resistance, compute_dc_resistance
from reasitic.tech import Tech


@dataclass
class FreqPointReport:
    """One frequency's worth of design data."""

    freq_ghz: float
    L_nH: float
    R_dc_ohm: float
    R_ac_ohm: float
    Q_metal: float
    pi: PiResult
    pi3: Pi3Result


@dataclass
class DesignReport:
    """Aggregate report for a single spiral over one or more frequencies."""

    name: str
    L_dc_nH: float  # frequency-independent self-inductance
    R_dc_ohm: float
    metal_area_um2: float
    n_polygons: int
    n_segments: int
    self_resonance_ghz: float | None
    points: list[FreqPointReport] = field(default_factory=list)

    def format_text(self) -> str:
        """Render the report as a readable text block."""
        out = StringIO()
        out.write(f"=== Design report for <{self.name}> ===\n")
        out.write(f"  L_dc      = {self.L_dc_nH:.4f} nH\n")
        out.write(f"  R_dc      = {self.R_dc_ohm:.4f} Ω\n")
        out.write(f"  Area      = {self.metal_area_um2:.2f} μm²\n")
        out.write(
            f"  Geometry  = {self.n_polygons} polygons, {self.n_segments} segments\n"
        )
        if self.self_resonance_ghz is not None:
            out.write(f"  f_SR      = {self.self_resonance_ghz:.3f} GHz\n")
        else:
            out.write("  f_SR      = (not found in scan range)\n")
        out.write("\n")
        if not self.points:
            return out.getvalue()
        out.write(
            f"{'f_GHz':>7} {'L_nH':>8} {'R_ac':>8} {'Q':>7} "
            f"{'C_p1':>8} {'C_p2':>8}\n"
        )
        for p in self.points:
            out.write(
                f"{p.freq_ghz:>7.3f} {p.L_nH:>8.4f} {p.R_ac_ohm:>8.4f}"
                f" {p.Q_metal:>7.2f} {p.pi.C_p1_fF:>8.3f} {p.pi.C_p2_fF:>8.3f}\n"
            )
        return out.getvalue()


def design_report(
    shape: Shape,
    tech: Tech,
    freqs_ghz: list[float],
    *,
    selfres_range_ghz: tuple[float, float] = (0.5, 50.0),
    ground_shape: Shape | None = None,
) -> DesignReport:
    """Compile a :class:`DesignReport` for ``shape``."""
    from reasitic.info import metal_area

    pts: list[FreqPointReport] = []
    for f in freqs_ghz:
        L = compute_self_inductance(shape)
        R_ac = compute_ac_resistance(shape, tech, f)
        Q = metal_only_q(shape, tech, f)
        pi = pi_model_at_freq(shape, tech, f)
        pi3 = pi3_model(shape, tech, f, ground_shape=ground_shape)
        R_dc = compute_dc_resistance(shape, tech)
        pts.append(
            FreqPointReport(
                freq_ghz=f,
                L_nH=L,
                R_dc_ohm=R_dc,
                R_ac_ohm=R_ac,
                Q_metal=Q,
                pi=pi,
                pi3=pi3,
            )
        )
    sr: SelfResonance = self_resonance(
        shape,
        tech,
        f_low_ghz=selfres_range_ghz[0],
        f_high_ghz=selfres_range_ghz[1],
    )
    return DesignReport(
        name=shape.name,
        L_dc_nH=compute_self_inductance(shape),
        R_dc_ohm=compute_dc_resistance(shape, tech),
        metal_area_um2=metal_area(shape),
        n_polygons=len(shape.polygons),
        n_segments=len(shape.segments()),
        self_resonance_ghz=sr.freq_ghz if sr.converged else None,
        points=pts,
    )
