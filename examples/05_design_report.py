"""Compile a multi-frequency design report for a single spiral.

Shows L_dc, R_dc, area, self-resonance, and per-frequency Pi-model
data in one shot.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.report import design_report


def main() -> None:
    tech = reasitic.parse_tech_file(ROOT.parent / "run" / "tek" / "BiCMOS.tek")
    sp = reasitic.square_spiral(
        "L1",
        length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0, 10.0])
    print(rpt.format_text())


if __name__ == "__main__":
    main()
