"""Frequency-swept S-parameter analysis with Touchstone export.

Sweeps a 3-turn 200 μm spiral across 1–10 GHz and writes the
S-matrix to a Touchstone ``.s2p`` file viewable by any RF tool.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.network import (
    linear_freqs,
    two_port_sweep,
    write_touchstone_file,
)


def main() -> None:
    tech = reasitic.parse_tech_file(ROOT.parent / "run" / "tek" / "BiCMOS.tek")
    sp = reasitic.square_spiral(
        "L1",
        length=200.0, width=10.0, spacing=2.0, turns=3.0,
        tech=tech, metal="m3",
    )
    fs = linear_freqs(1.0, 10.0, 0.5)
    sweep = two_port_sweep(sp, tech, fs)

    out = ROOT / "examples" / "L1_sweep.s2p"
    write_touchstone_file(out, sweep.to_touchstone_points(param="S"))
    print(f"Wrote {len(fs)} frequency points to {out}")
    # Quick summary of S11 magnitude at each f
    print(f"{'f (GHz)':>10} {'|S11|':>10} {'|S21|':>10}")
    for f, S in zip(fs, sweep.S, strict=True):
        print(f"{f:>10.2f} {abs(S[0,0]):>10.4f} {abs(S[1,0]):>10.4f}")


if __name__ == "__main__":
    main()
