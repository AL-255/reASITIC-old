"""Performance benchmarks for the inductance kernels.

Run with::

    python benchmarks/bench_inductance.py

Reports per-function timing for representative spiral geometries
to help catch performance regressions.
"""

import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

import reasitic
from reasitic.inductance import (
    compute_self_inductance,
    solve_inductance_matrix,
    solve_inductance_mna,
)
from reasitic.network import linear_freqs, two_port_sweep
from reasitic.network.analysis import pi_model_at_freq


def bench(name: str, fn, n: int = 10) -> None:
    """Time ``fn`` over ``n`` iterations and print the mean."""
    # Warm-up
    fn()
    t0 = time.perf_counter()
    for _ in range(n):
        fn()
    dt = (time.perf_counter() - t0) / n
    units = "ms" if dt > 1e-3 else "μs"
    val = dt * 1000 if units == "ms" else dt * 1e6
    print(f"  {name:<40s}  {val:8.2f} {units}")


def main() -> None:
    tech = reasitic.parse_tech_file(ROOT.parent / "run" / "tek" / "BiCMOS.tek")

    # 2-turn spiral
    sp_small = reasitic.square_spiral(
        "S", length=170, width=10, spacing=3, turns=2, tech=tech, metal="m3"
    )
    # 8-turn spiral (32 segments)
    sp_big = reasitic.square_spiral(
        "B", length=400, width=10, spacing=2, turns=8, tech=tech, metal="m3"
    )

    print("=== Inductance kernels ===")
    print(f"Small spiral: {len(sp_small.segments())} segments")
    bench("compute_self_inductance (small)",
          lambda: compute_self_inductance(sp_small))
    bench("solve_inductance_matrix (small, 1×1)",
          lambda: solve_inductance_matrix(sp_small, tech, 2.4, n_w=1, n_t=1))
    bench("solve_inductance_mna (small, 1×1)",
          lambda: solve_inductance_mna(sp_small, tech, 2.4, n_w=1, n_t=1))

    print(f"\nLarge spiral: {len(sp_big.segments())} segments")
    bench("compute_self_inductance (large)",
          lambda: compute_self_inductance(sp_big))
    bench("solve_inductance_matrix (large, 1×1)",
          lambda: solve_inductance_matrix(sp_big, tech, 2.4, n_w=1, n_t=1))
    bench("solve_inductance_mna (large, 1×1)",
          lambda: solve_inductance_mna(sp_big, tech, 2.4, n_w=1, n_t=1))
    bench("solve_inductance_matrix (large, 2×1)",
          lambda: solve_inductance_matrix(sp_big, tech, 2.4, n_w=2, n_t=1))

    print("\n=== Network analysis ===")
    bench("pi_model_at_freq (small)",
          lambda: pi_model_at_freq(sp_small, tech, 2.4))

    fs = linear_freqs(0.1, 10.0, 0.1)
    print(f"\n2Port sweep: {len(fs)} frequency points (small spiral)")
    bench("two_port_sweep",
          lambda: two_port_sweep(sp_small, tech, fs), n=5)

    print("\n=== Optimisation ===")
    from reasitic.optimise import optimise_square_spiral
    bench(
        "optimise_square_spiral",
        lambda: optimise_square_spiral(
            tech, target_L_nH=2.0, freq_ghz=2.4, metal="m3"
        ),
        n=3,
    )

    print("\n=== Substrate ===")
    from reasitic.substrate import setup_green_fft_grid
    bench(
        "setup_green_fft_grid (32x32)",
        lambda: setup_green_fft_grid(tech, z1_um=5, z2_um=5, nx=32, ny=32),
        n=3,
    )


if __name__ == "__main__":
    main()
