"""Transformer analysis: build two coupled spirals and report
L_pri, L_sec, M, k, n, Q at the operating frequency.
"""

import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.network.analysis import calc_transformer


def main() -> None:
    tech = reasitic.parse_tech_file(ROOT.parent / "run" / "tek" / "BiCMOS.tek")
    pri = reasitic.square_spiral(
        "PRI",
        length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    sec = reasitic.square_spiral(
        "SEC",
        length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3",
        x_origin=215,  # adjacent
    )
    res = calc_transformer(pri, sec, tech, freq_ghz=2.4)
    print(f"L_pri = {res.L_pri_nH:.3f} nH, L_sec = {res.L_sec_nH:.3f} nH")
    print(f"R_pri = {res.R_pri_ohm:.3f} Ω, R_sec = {res.R_sec_ohm:.3f} Ω")
    print(f"M = {res.M_nH:.3f} nH, k = {res.k:.4f}, n = {res.n_turns_ratio:.3f}")
    print(f"Q_pri = {res.Q_pri:.2f}, Q_sec = {res.Q_sec:.2f}")


if __name__ == "__main__":
    main()
