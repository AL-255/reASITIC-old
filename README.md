# reASITIC

[![CI](https://github.com/AL-255/reASITIC/actions/workflows/ci.yml/badge.svg)](https://github.com/AL-255/reASITIC/actions/workflows/ci.yml)
[![Docs](https://github.com/AL-255/reASITIC/actions/workflows/docs.yml/badge.svg)](https://al-255.github.io/reASITIC/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![Tests](https://img.shields.io/badge/tests-404%20passing-brightgreen)
![Coverage](https://img.shields.io/badge/coverage-92%25-brightgreen)
![License](https://img.shields.io/badge/license-GPL--2.0-blue)

<!-- DOCS-INTRO -->
Reverse-engineered, clean-room Python implementation of [ASITIC][asitic] —
a planar RF inductor analysis and design tool originally developed at
UC Berkeley by Ali M. Niknejad in 1999. The original binary is
checked in alongside this package at `../run/asitic.linux.2.2`; the
decompiled C surface and ID notes live in `../decomp/` and
`../IDENTIFIED.md`.

<!-- /DOCS-INTRO -->

## Quick install

```bash
pip install reASITIC                 # base library
pip install reASITIC[plot]           # + matplotlib for plotting helpers
pip install -e ".[dev]"              # development install
```

```bash
reasitic --version
reasitic -t my_tech.tek -c "SQ NAME=L:LEN=200:W=10:S=2:N=3:METAL=m3"
reasitic-gui -t my_tech.tek                # graphical workspace
```

> **Status:** All six phases of the [implementation plan](./PLAN.md)
> are functionally complete, plus extensions. The library covers
> tech-file parsing, 10 geometry builders (square / polygon /
> wire / ring / via / transformer / 3D-transformer / symmetric-
> square / balun / capacitor) with shape transforms (translate,
> rotate, flip), Greenhouse partial-inductance summation with
> filament-level current crowding via both Schur-complement and
> proper MNA topology solves, eddy-current correction, mutual
> inductance + coupling coefficient, DC + Wheeler skin-effect AC
> resistance with auto-sized filament grids, metal-loss Q,
> parallel-equivalent shunt resistance, 2-port Y/Z/S conversions,
> Pi / Pi3 / Pi4 equivalent extraction, input impedance with
> terminations, self-resonance scan, 3-port reduction, frequency
> sweeps, transformer analysis (CalcTrans), Touchstone `.s2p` /
> SPICE / FastHenry exports, JSON save/load, CIF / Sonnet / Tek
> exports, per-metal-layer substrate shunt-cap with Sommerfeld-
> integral Green's function and FFT-accelerated convolution grid,
> scipy.optimize-based OptSq/OptPoly/OptArea/OptSymSq + BatchOpt,
> parametric geometry sweeps, info commands (MetArea, ListSegs,
> LRMAT), multi-frequency design report, optional matplotlib
> plotting helpers, a binary cross-validation harness, runnable
> examples, end-to-end integration test, Touchstone reader/writer
> round-trip, FastHenry/SPICE/CIF/Sonnet/Tek exports, performance
> benchmarks, auto-generated CLI reference, and a REPL CLI with
> **117 commands** (full binary REPL parity). **401 tests pass**
> with **92% line coverage**; ruff (with pydocstyle D-rules) and
> `mypy --strict` are clean. PyPI-ready: builds cleanly via
> ``python -m build`` and installs end-to-end in a fresh venv.
>
> Coverage of the original 643 C functions: ~165 ported (~26 %),
> including all 117/117 REPL commands.

## What works today

```python
import reasitic

tech = reasitic.parse_tech_file("../run/tek/BiCMOS.tek")

# Build a 2-turn square spiral inductor on metal m3
sp = reasitic.square_spiral(
    "L1",
    length=170.0,    # outer side, μm
    width=10.0,      # metal width, μm
    spacing=3.0,     # turn-to-turn spacing, μm
    turns=2.0,
    tech=tech,
    metal="m3",
)

# Inductance, AC resistance, Q at 2 GHz
L_nH = reasitic.compute_self_inductance(sp)
R_ac = reasitic.compute_ac_resistance(sp, tech, freq_ghz=2.0)
Q = reasitic.metal_only_q(sp, tech, freq_ghz=2.0)
print(f"L = {L_nH:.3f} nH, R(2 GHz) = {R_ac:.3f} Ω, Q = {Q:.1f}")

# 2-port Y matrix and Pi extraction
from reasitic.network import spiral_y_at_freq, pi_equivalent, y_to_s
Y = spiral_y_at_freq(sp, tech, freq_ghz=2.0)
pi = pi_equivalent(Y, freq_ghz=2.0)
print(f"Z_series = {pi.Z_s}, S = {y_to_s(Y)}")

# Coupling between two adjacent spirals
sp2 = reasitic.square_spiral("L2", length=170.0, width=10.0, spacing=3.0,
                              turns=2.0, tech=tech, metal="m3", x_origin=200.0)
k = reasitic.coupling_coefficient(sp, sp2)
print(f"k(L1, L2) = {k:.3f}")
```

The same flows work from the command line:

```
$ reasitic -t ../run/tek/BiCMOS.tek
reASITIC> SQ NAME=L1:LEN=170:W=10:S=3:N=2:METAL=m3:XORG=0:YORG=0
reASITIC> IND L1
L(L1) = 1.279 nH
reASITIC> RES L1 2.0
R_dc(L1) = 2.512000 Ohm
R_ac(L1, 2.0 GHz) = 2.643... Ohm
reASITIC> Q L1 2.0
Q_metal(L1, 2.0 GHz) = ...
reASITIC> SQ NAME=L2:LEN=170:W=10:S=3:N=2:METAL=m3:XORG=200:YORG=0
reASITIC> K L1 L2
M(L1, L2) = ... nH
k(L1, L2) = ...
```

## Library substitutions vs. the original

The original is statically linked against several Fortran/C libraries
identified during reverse engineering. The Python port uses portable
equivalents:

| Vendored in binary | Replacement in Python |
| --- | --- |
| LAPACK / BLAS | `scipy.linalg` |
| LINPACK | `scipy.linalg` |
| QUADPACK | `scipy.integrate.quad` |
| libf2c | _not needed_ |
| MV++ Sparse-BLAS | `scipy.sparse` |
| SGI STL | _not needed_ |
| libstdc++ exceptions | Python exceptions |
| Mesa GL / X11 | _out of scope_ |
| readline | `cmd.Cmd` |

Only `numpy` and `scipy` are runtime dependencies.

## Install (development)

```bash
pip install -e ".[dev]"
pytest          # 29 passing
ruff check .
mypy
```

The validation tests under `tests/test_validation_binary.py` invoke
the legacy binary via `xvfb-run` (so they run on headless CI). They
auto-skip if `xvfb-run` or the binary isn't on disk.

## Layout

```
src/reasitic/
    units.py             # SI constants, μm/cm conversions
    tech.py              # .tek parser → Tech / Layer / Metal / Via
    geometry.py          # Point/Segment/Polygon/Shape + 9 builders
    inductance/
        grover.py        # Grover closed-form self / mutual formulas
        partial.py       # Greenhouse summation + inter-shape coupling
        filament.py      # Filament discretisation + scipy.linalg solve
    resistance/
        dc.py            # R = rsh · L / W per segment
        skin.py          # Wheeler-style AC resistance (skin effect)
    network/
        twoport.py       # Y/Z/S conversions + Pi-equivalent
        threeport.py     # 3-port reduction + Z→S
        sweep.py         # Frequency sweep wrapper
        touchstone.py    # IEEE Touchstone v1 (.s2p) writer
    quality.py           # ωL/R metal-loss-only Q-factor
    inductance/
        eddy.py          # Substrate eddy-current correction
        filament.py      # MNA + Schur filament solvers
    optimise/
        opt_sq.py        # scipy.optimize SLSQP for OptSq
        opt_poly.py      # OptPoly, OptArea, OptSymSq
        batch.py         # BatchOpt over (L, f) target table
        sweep.py         # Cartesian parametric geometry sweep
    substrate/
        shunt.py         # Per-metal-layer parallel-plate shunt cap
        green.py         # Sommerfeld Green's function (scipy.integrate)
        fft_grid.py      # 2-D FFT-accelerated convolution grid
    network/
        analysis.py      # Pi/Pi3/Pi4, Zin, SelfRes, ShuntR, CalcTrans
    info.py              # MetArea, ListSegs, LRMAT
    report.py            # Multi-frequency design report
    plot.py              # Optional matplotlib helpers
    exports/
        cif.py           # CIF layout export
        sonnet.py        # Sonnet .son export
        tek.py           # gnuplot-friendly Tek dump
        spice.py         # SPICE Pi-model .subckt
        fasthenry.py     # FastHenry .inp
    persistence.py       # JSON save/load
    validation/
        binary_runner.py # Drive run/asitic via xvfb-run + parse
    cli.py               # `reasitic` entry point (105 commands)
examples/                # Runnable scripts: single spiral, sweep, opt, transformer, report
benchmarks/              # Performance benchmarks
scripts/                 # Maintenance scripts (CLI reference generator)
```

## Documentation

The full HTML documentation, including a searchable API reference, is
hosted at **<https://al-255.github.io/reASITIC/>** and is rebuilt from
`docs/` on every push to `main` via the `Docs` GitHub Actions
workflow. To build it locally:

```bash
pip install -e ".[docs]"
cd docs && make html      # output in docs/_build/html
make strict               # treat sphinx warnings as errors (CI does this)
```

* [`TUTORIAL.md`](./TUTORIAL.md) — step-by-step design flow walkthrough
* [`COOKBOOK.md`](./COOKBOOK.md) — 10 worked design recipes for common RF scenarios
* [`FAQ.md`](./FAQ.md) — common questions and troubleshooting tips
* [`CLI_REFERENCE.md`](./CLI_REFERENCE.md) — auto-generated REPL command reference
* [`MAPPING.md`](./MAPPING.md) — line-by-line Python ↔ C function correspondence (~155/643 ports)
* [`PLAN.md`](./PLAN.md) — implementation plan and phase status
* [`CHANGELOG.md`](./CHANGELOG.md) — version history and notable changes
* [`examples/`](./examples) — runnable Python scripts
* [`benchmarks/`](./benchmarks) — performance regression checks


## C ↔ Python mapping

For every Python function in `src/reasitic/`, [`MAPPING.md`](./MAPPING.md)
records the reverse-engineered C function it ports / mirrors (with
addresses inside `run/asitic.linux.2.2`). Useful when chasing
behavioural discrepancies against the binary.

## License

GPL-2.0-only. See [LICENSE](LICENSE).

[asitic]: https://rfic.eecs.berkeley.edu/~niknejad/asitic.html
