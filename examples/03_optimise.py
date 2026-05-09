"""Optimise a square-spiral inductor for maximum Q at a target L.

Uses scipy.optimize SLSQP under the hood. Compares OptSq, OptArea,
and OptSymSq for the same target.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.optimise import (
    optimise_area_square_spiral,
    optimise_square_spiral,
    optimise_symmetric_square,
)


def main() -> None:
    tech = reasitic.parse_tech_file(ROOT.parent / "run" / "tek" / "BiCMOS.tek")
    target_L = 2.5
    f = 2.4

    print(f"Target: L = {target_L} nH at {f} GHz on m3\n")

    print("OptSq (max Q):")
    r1 = optimise_square_spiral(tech, target_L_nH=target_L, freq_ghz=f, metal="m3")
    print(f"  L={r1.length_um:.1f} W={r1.width_um:.1f} S={r1.spacing_um:.1f}"
          f" N={r1.turns:.2f} → L={r1.L_nH:.2f} Q={r1.Q:.1f}")

    print("\nOptArea (min footprint):")
    r2 = optimise_area_square_spiral(tech, target_L_nH=target_L, freq_ghz=f, metal="m3")
    print(f"  L={r2.length_um:.1f} W={r2.width_um:.1f} S={r2.spacing_um:.1f}"
          f" N={r2.turns:.2f} → L={r2.L_nH:.2f} Q={r2.Q:.1f}")

    print("\nOptSymSq (max Q, symmetric):")
    r3 = optimise_symmetric_square(tech, target_L_nH=target_L, freq_ghz=f, metal="m3")
    print(f"  L={r3.length_um:.1f} W={r3.width_um:.1f} S={r3.spacing_um:.1f}"
          f" N={r3.turns:.2f} → L={r3.L_nH:.2f} Q={r3.Q:.1f}")


if __name__ == "__main__":
    main()
