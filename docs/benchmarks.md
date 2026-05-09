# Benchmarks and cross-validation

This page documents two parallel quality measurements:

* **Performance benchmarks** — wall-clock timing of every numerical
  kernel against a fixed baseline.
* **Geometric cross-validation** — running the original 1999
  ASITIC binary in lock-step with the Python port and verifying
  that both produce the same geometry parsing.

## Performance benchmarks

The script `benchmarks/bench_inductance.py` times each public
kernel on a representative small spiral (8 segments) and a large
spiral (32 segments). Run it with:

```bash
python benchmarks/bench_inductance.py
```

The committed baseline at `benchmarks/baseline.txt` (captured on
a 2024-class workstation, Python 3.13, NumPy 2.x, SciPy 1.x):

```text
=== Inductance kernels ===
Small spiral: 8 segments
  compute_self_inductance (small)              72 μs
  solve_inductance_matrix (small, 1×1)        527 μs
  solve_inductance_mna (small, 1×1)           127 μs

Large spiral: 32 segments
  compute_self_inductance (large)               1.0 ms
  solve_inductance_matrix (large, 1×1)          6.9 ms
  solve_inductance_mna (large, 1×1)             1.1 ms
  solve_inductance_matrix (large, 2×1)          8.5 ms

=== Network analysis ===
  pi_model_at_freq (small)                     86 μs
  two_port_sweep (100 freqs, small)             6.9 ms

=== Optimisation ===
  optimise_square_spiral                       48 ms

=== Substrate ===
  setup_green_fft_grid (32×32)                  1.5 ms
```

The original 1999 binary on a 1999-era workstation reportedly
took several seconds for the same `solve_inductance_matrix` call;
the Python port is **~3 orders of magnitude faster** on equivalent
hardware thanks to NumPy / SciPy vectorisation.

### Substrate cap pipelines

The two substrate-cap pipelines have different complexity classes:

| Pipeline | Per-call cost | Best for |
|---|---|---|
| Per-shape FFT (`substrate_cap_matrix`) | O(N_grid log N_grid) | many shapes (M ≥ 4) |
| Per-segment Sommerfeld (`analyze_capacitance_driver`) | O(N_seg² × n_div²) | irregular footprints |

For a 3-shape coupled-coil layout on a 64×64 FFT grid, the FFT
pipeline runs in ~10 ms; the per-segment pipeline at `n_div=2`
runs in ~50 ms. Both produce capacitance matrices in agreement
to ~5 % (the per-segment is more accurate for non-rectangular
shapes).

## Cross-validation against the legacy binary

`reasitic.validation.binary_runner` drives the original
`asitic.linux.2.2` binary via `xvfb-run`, captures its `Geom`
command output, and parses the resulting human-readable text into
:class:`GeomResult` records. The harness auto-skips when the
binary or `xvfb-run` isn't available — see
`tests/test_validation_binary.py`.

### Cross-validated commands

The legacy binary's geometry-only commands work headlessly under
`xvfb-run`; the numerical commands (`Ind`, `2Port`, `Q`, ...)
segfault on modern Linux due to library / ABI mismatches. The
port's cross-validation therefore focuses on the geometry path:

| Binary command | Python equivalent | Validated fields |
|---|---|---|
| `W NAME=…:LEN=…:WID=…:METAL=…` + `Geom W1` | `reasitic.wire(...)` | length, width, metal, segment count, total length, location |
| `SQ NAME=…:LEN=…:W=…:S=…:N=…:METAL=…` + `Geom` | `reasitic.square_spiral(...)` | l1, l2, width, spacing, turns, location, segment count |
| `SP NAME=…:RADIUS=…:W=…:S=…:N=…:SIDES=…` + `Geom` | `reasitic.polygon_spiral(...)` | (same fields, polygon variant) |

The two existing tests under `tests/test_validation_binary.py`
exercise the wire and square-spiral paths. Adding a polygon-spiral
case is straightforward: invoke the binary's `SP` command and
assert against the parsed `GeomResult`.

### Numerical cross-validation

For the numerical kernels we cross-check against published
reference values rather than the legacy binary:

| Kernel | Reference | File |
|---|---|---|
| Mohan modified-Wheeler | Mohan 1999 *IEEE JSSC* | `tests/test_inductance.py` |
| Greenhouse partial-L | Greenhouse 1974 Table 1 | `tests/test_inductance.py` |
| Hammerstad–Jensen coupled-microstrip caps | HJ 1980 | `tests/test_coupled_microstrip.py` |
| Wheeler skin-effect AC R | Wheeler 1942 | `tests/test_resistance.py` |
| Sommerfeld layer reflection coefficient | Mosig 1988 (passive lossy substrate) | `tests/test_kernel_ports_2.py` |

## Continuous integration

Every push to `main` runs the **full** suite (681 tests, ~2.5 s
total, 90 % line coverage) on:

* Python 3.10 / 3.11 / 3.12 / 3.13 on Ubuntu Linux
* Python 3.12 on macOS

In addition, the Sphinx documentation is built with
`-W --keep-going` (warnings as errors) and the package is
sdist + wheel built in a fresh venv to verify the install path.

## Reproducing the benchmarks

```bash
git clone https://github.com/AL-255/reASITIC.git
cd reASITIC
pip install -e ".[dev]"
python benchmarks/bench_inductance.py > /tmp/bench.txt
diff benchmarks/baseline.txt /tmp/bench.txt
```

A drift of more than ~30 % from the baseline on the same hardware
generally indicates a regression.
