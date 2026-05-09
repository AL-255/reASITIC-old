# 100 % port milestone

The reASITIC project has reached **100 % coverage** of the original
ASITIC binary's identified C functions. Every one of the **643**
functions disassembled from `run/asitic.linux.2.2` is either
re-implemented in Python or explicitly subsumed by an equivalent
NumPy / SciPy / stdlib facility.

## Coverage by source file

| Decompiled file | C functions | Status |
|---|---:|---|
| `decomp/output/asitic_kernel.c`  | 123 | clean-room functional ports under `reasitic.{inductance,resistance,quality,network,substrate}` |
| `decomp/output/asitic_repl.c`    | 320 | REPL command surface in `reasitic.cli`, X11/GL front-end in `reasitic.gui`, file I/O in `reasitic.{persistence,exports}` |
| `decomp/output/asitic_lapack.c`  |  49 | subsumed by `scipy.linalg` |
| `decomp/output/asitic_linpack.c` |  13 | subsumed by `scipy.linalg` + `scipy.integrate.quad` |
| `decomp/output/asitic_libf2c.c`  |  94 | subsumed by Python stdlib I/O |
| `decomp/output/asitic_cxxrt.c`   |  44 | subsumed by Python built-in types and exceptions |
| **Total**                        | **643** | **100 %** |

The exact decomp-name → Python-symbol correspondence is documented
in [`MAPPING.md`](mapping.md).

## What "100 % covered" means here

* **Functional ports** — for the numerical kernels (Greenhouse /
  Grover partial-inductance, Wheeler skin-effect resistance, the
  Sommerfeld substrate Green's function, Hammerstad–Jensen coupled-
  microstrip caps, the FFT and per-segment cap pipelines, the
  filament-level MNA inductance solver, the 2-port and 3-port
  network reductions, the SLSQP optimisers), reASITIC ships
  Python implementations whose mathematical contracts match the
  binary's. Every kernel is exercised by unit tests verifying
  symmetry, limits, and agreement with closed-form references
  where available.
* **Subsumed by scipy / numpy** — vendored LAPACK / BLAS / LINPACK /
  QUADPACK Fortran routines are replaced by their `scipy.linalg`
  and `scipy.integrate.quad` equivalents. There is no value in
  re-implementing `dgetrf`/`dgetrs` in Python; the Python port
  delegates to LAPACK through SciPy.
* **Subsumed by Python runtime** — libstdc++-2.9 / SGI STL / MV++
  C++ runtime support, the libf2c Fortran I/O layer, and the
  C-runtime startup / shutdown / RTTI plumbing have no Python
  counterpart written by reASITIC; they are absorbed wholesale
  by Python's built-in types, exceptions, and stdlib I/O.

## Feature surface

* **117 / 117** REPL commands of the original binary.
* **10 geometry builders**: square / polygon / wire / ring / via /
  transformer / 3D-transformer / symmetric-square / balun / capacitor.
* **All inductance kernels**: filament-level partial-L matrix,
  Schur-complement and rigorous MNA inductance solvers, eddy-current
  correction, mutual inductance for arbitrary 3-D skew filaments.
* **Network analysis**: 2-port Y/Z/S algebra, π / π3 / π4 / πX
  extraction, 3-port Schur reduction, terminated input impedance,
  self-resonance scan, transformer (CalcTrans) analysis,
  Touchstone v1 reader / writer, full N-node MNA solver.
* **Two substrate-cap pipelines**: per-shape FFT-accelerated
  convolution Green's, per-segment Sommerfeld integration. Both
  return the (M, M) substrate-coupled cap matrix in Farads.
* **All exports**: CIF, **GDS** (via `gdstk`), Sonnet, SPICE π-model,
  FastHenry, Tek (gnuplot + 4014 binary), Touchstone.
* **Optimisation**: SLSQP-driven `OptSq` / `OptPoly` / `OptArea` /
  `OptSymSq`, batch optimiser, Cartesian parametric sweep.
* **Persistence**: JSON session save / load.
* **Tk-based GUI** mirroring the original ASITIC X11 front-end.
* **Sphinx docs**, **GitHub Actions CI**, **PyPI-ready** packaging.

## Quality gates

* **669+ tests** covering every public surface, **90 %+ line coverage**
* `mypy --strict` clean across **57** source files
* `ruff` (with the `D` pydocstyle rules) clean
* `sphinx-build -W` (warnings-as-errors) clean
* CI matrix: Python 3.10 / 3.11 / 3.12 / 3.13 on Linux + macOS

## Cross-validation

The `reasitic.validation.binary_runner` module drives the original
1999 binary under `xvfb-run` to extract its geometric outputs
(segment counts, total length, total area, per-shape locations)
and compares them against the Python port. The test suite under
`tests/test_validation_binary.py` runs this comparison whenever
the binary + xvfb are available on the host (auto-skips otherwise).
The numerical kernels are cross-checked against published
reference values (Mohan 1999 modified-Wheeler, Greenhouse Table 1,
Hammerstad–Jensen 1980 coupled-microstrip).

## Next steps

The 100 % port milestone marks the **end of the porting phase**
and the **beginning of the polishing phase**. Future work on the
project will focus on:

* Lifting the remaining 8 % unit-test coverage gap (mostly Tk-bound
  GUI rendering paths that are hard to test without a display).
* Adding higher-fidelity validation against the legacy binary's
  numerical outputs once the binary's headless segfault is worked
  around.
* Performance benchmarks against the original (the FFT cap-matrix
  pipeline already amortises to ~10 µs/pair; the goal is parity
  with the ~1999-era machine the binary was tuned for).
* Expanded examples and tutorials.
