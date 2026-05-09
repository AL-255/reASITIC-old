"""Single-spiral analysis at one frequency.

Builds a 2-turn 170 μm × 10 μm m3 spiral on the BiCMOS tech stack
and prints L, R(DC), R(2.4 GHz), Q, and the Pi-equivalent.

Run with::

    python examples/01_single_spiral.py
"""

import sys
from pathlib import Path

# Add the package root so this example runs without `pip install`
ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.network.analysis import pi_model_at_freq


def main() -> None:
    tech_path = ROOT.parent / "run" / "tek" / "BiCMOS.tek"
    tech = reasitic.parse_tech_file(tech_path)

    sp = reasitic.square_spiral(
        "L1",
        length=170.0,
        width=10.0,
        spacing=3.0,
        turns=2.0,
        tech=tech,
        metal="m3",
    )

    f = 2.4
    L = reasitic.compute_self_inductance(sp)
    R_dc = reasitic.compute_dc_resistance(sp, tech)
    R_ac = reasitic.compute_ac_resistance(sp, tech, f)
    Q = reasitic.metal_only_q(sp, tech, f)
    pi = pi_model_at_freq(sp, tech, f)

    print(f"L      = {L:.4f} nH")
    print(f"R_dc   = {R_dc:.4f} Ω")
    print(f"R_ac   = {R_ac:.4f} Ω at {f} GHz")
    print(f"Q      = {Q:.2f}")
    print(f"Pi: L_s = {pi.L_nH:.3f} nH, R_s = {pi.R_series:.3f} Ω,"
          f" C_p1 = {pi.C_p1_fF:.2f} fF, C_p2 = {pi.C_p2_fF:.2f} fF")


if __name__ == "__main__":
    main()
