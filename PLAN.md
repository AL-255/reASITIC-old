# reASITIC implementation plan

A clean-room Python port of [ASITIC][asitic], the 1999 UC Berkeley
RF inductor analysis tool. Validated against the original 32-bit
binary at `../run/asitic.linux.2.2` (parent ``asitic-re`` repo).

> **Status: 100 % port complete.** All **643** identified C
> functions across the kernel, frontend, and four vendored
> libraries are either re-implemented in Python or explicitly
> subsumed by NumPy / SciPy / Python-stdlib equivalents. Test
> suite at **737 passing + 3 skipped** (the optional binary-cross-
> validation tests, gated behind QEMU). Line coverage **91 %**.
> See [`MAPPING.md`](./MAPPING.md) for the per-function ledger
> and [`docs/milestone.md`](./docs/milestone.md) for the
> narrative milestone summary.

## Where this plan came from

The reverse-engineered C surface is ~60 kLOC across six files
(`decomp/output/asitic_*.c`):

| File | Bucket | C funcs |
|---|---|---:|
| ``asitic_kernel.c`` | numerical kernels | 123 |
| ``asitic_repl.c`` | REPL + X11/GL frontend | 320 |
| ``asitic_lapack.c`` | vendored LAPACK / BLAS | 49 |
| ``asitic_linpack.c`` | vendored LINPACK / SLATEC / QUADPACK | 13 |
| ``asitic_libf2c.c`` | vendored Fortran I/O runtime | 94 |
| ``asitic_cxxrt.c`` | vendored libstdc++ / SGI STL / MV++ | 44 |
| **Total** | | **643** |

The plan was staged: foundation (parsers + simplest kernels +
validation harness) → numerical kernels → network extraction →
optimisation → REPL/CLI → GUI → exports → polish. All phases
are complete; only ongoing **polish** remains (test-coverage
gaps, performance benchmarks, expanded examples).

## Library substitutions

The original is statically linked against several Fortran/C
numerical libraries. The Python port uses portable equivalents:

| Vendored in binary | Replacement in Python |
| --- | --- |
| LAPACK / BLAS (49 funcs) | ``scipy.linalg`` |
| LINPACK / SLATEC (13 funcs) | ``scipy.linalg`` |
| QUADPACK (DQAGS / DQAGI / DQAWO / DQAWFE) | ``scipy.integrate.quad`` |
| libf2c (94 funcs) | Python stdlib I/O |
| MV++ Sparse-BLAS | ``scipy.sparse`` (or dense ``numpy``) |
| SGI STL | Python built-in containers |
| libstdc++-2.9 exceptions / RTTI | Python exceptions |
| Mesa GL / X11 | Tk Canvas (``tkinter``) |
| readline | ``cmd.Cmd`` + ``argparse`` |

``numpy`` and ``scipy`` are the only required runtime
dependencies. ``matplotlib`` is optional via the ``[plot]``
extra; ``gdstk`` is optional via the ``[gds]`` extra.

## Package layout (current)

```
src/reasitic/
    __init__.py            # top-level re-exports + summary()
    _version.py
    units.py               # SI constants, μm/cm conversions
    tech.py                # .tek file parser → Tech / Layer / Metal / Via
    geometry.py            # Point / Segment / Polygon / Shape + 10 builders
    spiral_helpers.py      # spiral_max_n / radius / turn-position / period-fold
    info.py                # MetArea / ListSegs / LRMAT helpers
    persistence.py         # JSON session save / load
    quality.py             # ωL/R metal-loss-only Q
    plot.py                # optional matplotlib helpers
    report.py              # multi-frequency design report
    inductance/
        grover.py          # closed-form Grover self & mutual L
        partial.py         # Greenhouse partial-inductance summation
        filament.py        # filament discretisation + Schur / MNA solvers
        skew.py            # arbitrary 3-D skew filament mutual L
        eddy.py            # substrate ground-image eddy correction
        matrix_fill.py     # impedance-matrix assembly helpers
    resistance/
        dc.py              # ρ_sh · L / W per segment
        skin.py            # Wheeler-style AC R with skin effect
        three_class.py     # 3-class metal weighted accumulator
    network/
        twoport.py         # Y/Z/S algebra + Pi extraction + de-embed
        threeport.py       # 3-port Schur reduction + Z→S
        sweep.py           # frequency-sweep wrapper
        touchstone.py      # IEEE Touchstone v1 (.s2p) reader/writer
        analysis.py        # Pi / Pi3 / Pi4 / PiX, Zin, SelfRes, ShuntR, CalcTrans
        mna_helpers.py     # MNA solvers (solve_node_equations, 3port Schur)
    substrate/
        shunt.py           # per-metal-layer parallel-plate shunt cap
        green.py           # Sommerfeld Green's function (per-pair)
        fft_grid.py        # FFT-accelerated convolution Green's grid
        coupled.py         # Hammerstad-Jensen coupled-microstrip caps
        segment_cap.py     # per-segment substrate-cap pipeline
    optimise/
        opt_sq.py          # SLSQP square-spiral optimiser
        opt_poly.py        # OptPoly / OptArea / OptSymSq
        batch.py           # BatchOpt across many (L, f) targets
        sweep.py           # Cartesian parametric geometry sweep
    exports/
        cif.py             # CIF round-trip
        sonnet.py          # Sonnet .son round-trip
        tek.py             # gnuplot text + Tek 4014 binary
        spice.py           # SPICE Pi-model .subckt + broadband
        fasthenry.py       # FastHenry .inp
        gds.py             # GDSII round-trip via gdstk
    gui/
        app.py             # Tk-based reASITIC workspace
        renderer.py        # Tk Canvas renderer (mirrors xui_*)
        viewport.py        # pan/zoom transform
        colors.py          # per-metal X11→Tk palette
    validation/
        binary_runner.py   # optional QEMU-driven binary harness
    cli.py                 # `reasitic` REPL with all 117 commands
    __main__.py            # `python -m reasitic` entry
```

Tests live alongside under ``tests/`` (~40 files, 737 tests
currently passing); golden artifacts captured from the legacy
binary live in ``tests/data/validation/``. See
[`docs/`](./docs) for Sphinx documentation, [`benchmarks/`](./benchmarks)
for performance regressions, and [`examples/`](./examples) for
runnable demos.

## Phases (all complete)

### Phase 1 — foundation ✅

* ``units.py`` constants, ``tech.py`` parser, ``geometry.py``
  Point / Segment / Polygon / Shape with 10 builders (square,
  polygon, wire, ring, via, transformer, 3D-transformer,
  symmetric-square, balun, capacitor + multi-metal-square).
* Closed-form Grover formulas: rectangular-bar self-L,
  parallel-segment mutual-L.
* Greenhouse partial-inductance summation.
* QEMU-aware validation harness in ``validation/binary_runner``.

### Phase 2 — numerical kernels ✅

* DC + Wheeler-style AC resistance (with skin-depth filament
  auto-sizing).
* Metal-loss-only Q.
* Mutual inductance between shapes + coupling coefficient.
* Filament-level current-crowding solvers: both Schur-complement
  reduction and rigorous MNA.
* **Arbitrary 3-D skew filament mutual L** via Maxwell's double
  integral evaluated through ``scipy.integrate.dblquad``, with
  closed-form parallel + zero-cos(α) fast paths.
* Substrate eddy-current correction via ground-image method
  with finite-thickness factor.

### Phase 3 — network extraction ✅

* Y / Z / S 2-port algebra with arbitrary Z₀.
* π / π3 / π4 / πX equivalent extraction.
* 3-port Schur reduction.
* Terminated Zin, self-resonance scan, shunt-R, transformer
  analysis (CalcTrans).
* Multi-frequency 2-port sweep + Touchstone v1 reader/writer.
* Pad de-embedding (open-only, open-then-short).
* MNA helpers: ``assemble_mna_matrix``, ``solve_node_equations``,
  ``solve_3port_equations``.

### Phase 4 — substrate ✅

* Per-metal-layer parallel-plate shunt cap with series-stack
  dielectric path-to-ground + edge-fringe correction.
* Multi-layer Sommerfeld Green's function (per-pair, via
  ``scipy.integrate.quad``).
* **FFT-accelerated convolution Green's function** (the binary's
  ``compute_green_function`` path): k-space spectral form with
  zero-padded linear convolution, ``rasterize_shape`` polygon
  rasteriser, and end-to-end ``substrate_cap_matrix`` driver.
* Per-segment Sommerfeld pipeline complementing the FFT path
  (``analyze_capacitance_driver``, ``capacitance_per_segment``,
  ``capacitance_segment_integral``).
* Hammerstad-Jensen coupled-microstrip caps with even/odd
  impedances.

### Phase 5 — optimisation ✅

* ``OptSq`` / ``OptPoly`` / ``OptArea`` / ``OptSymSq`` via
  ``scipy.optimize.minimize`` (SLSQP).
* ``BatchOpt`` across many (L, f) target pairs.
* Cartesian parametric geometry sweep with TSV / CSV writers.

### Phase 6 — REPL parity ✅

* All **117 / 117** commands of the original binary, dispatched
  through ``cli.Repl``.
* JSON session ``Save`` / ``Load`` (replaces the binary's BSAVE).
* Macro / log / record / exec / cat I/O paths.

### Phase 7 — GUI ✅

* Tk-based ``reasitic.gui.GuiApp``: top-down layout view (pan,
  zoom, chip outline, substrate grid, click-to-select) + embedded
  REPL pane that drives ``cli.Repl``.
* Per-metal X11→Tk colour palette ported from the tech files'
  ``color`` field.
* Mirror of the binary's ``xui_*`` rendering surface (12 / 12
  ported decomp functions).

### Phase 8 — exports ✅

* CIF / Sonnet / Tek (gnuplot + 4014 binary) / SPICE π-model /
  FastHenry / GDSII (via ``gdstk``).
* Touchstone v1 reader & writer (``.s2p``).
* Round-trip support for CIF / Sonnet / GDS.

### Phase 9 — polish (ongoing)

* [x] **PyPI-ready packaging** — sdist + wheel build cleanly,
      ``reasitic --version`` works in a fresh venv.
* [x] **Sphinx docs** with autodoc + autosummary + intersphinx
      to NumPy / SciPy / Python; built with ``-W`` strict.
* [x] **GitHub Actions CI** — Python 3.10 / 3.11 / 3.12 / 3.13 on
      Ubuntu + Python 3.12 on macOS; doctest, ruff, mypy --strict,
      sdist/wheel build.
* [x] **GitHub Pages** docs deploy on every push to main.
* [x] **Golden-artifact validation flow** — binary outputs are
      pre-captured under QEMU in the parent ``asitic-re`` repo
      (``scripts/regen_validation_artifacts.py``) and shipped as
      static JSON under ``tests/data/validation/``. Tests need
      neither the binary nor QEMU at runtime.
* [x] **Performance benchmarks** with a committed baseline
      (``benchmarks/baseline.txt``).
* [ ] Lift line coverage from 91 % toward 95 %+ (remaining gaps
      are mostly Tk-bound ``gui/`` rendering and the QEMU-only
      live binary runner).
* [ ] Expand the golden-artifact set with more canonical cases
      (currently 3: a wire and two square spirals).
* [ ] Add cross-validation under QEMU for Ind / Res-DC / Q-LF /
      Pi3 / LRMAT (these all work in the binary; the artifacts
      currently capture only Geom).

## Coordinate / unit conventions

Internal computation matches the binary:

* Lateral lengths in **microns** (input units).
* The Grover formulas multiply by ``UM_TO_CM = 1e-4`` (μm → cm)
  before evaluating the closed form, since Grover's tables are
  tabulated in cm.
* Output inductance in **nH** (closed form yields nH directly
  when lengths are in cm and currents in A, since
  ``μ₀ / 4π × 1 cm = 1 nH``).
* Frequency in **GHz**.
* Resistance in **Ω**.
* Capacitance in **F** (top-level) or **F/cm** (Hammerstad-Jensen
  per-unit-length surface).

## Bookkeeping

* [`MAPPING.md`](./MAPPING.md) — per-function Python ↔ C ledger
  (643 / 643 = 100 %). Update whenever a new public function
  lands so the correspondence stays trustworthy.
* [`docs/milestone.md`](./docs/milestone.md) — narrative summary
  of the 100 % milestone with feature-surface and validation
  cross-references.
* [`CHANGELOG.md`](./CHANGELOG.md) — release history.
* [`docs/benchmarks.md`](./docs/benchmarks.md) — performance +
  cross-validation methodology.

## Validation strategy

The Python kernels are validated on three independent axes:

1. **Closed-form analytic checks** — every kernel has unit tests
   against published reference values (Mohan 1999 Table 1,
   Greenhouse 1974 Table 1, Hammerstad-Jensen 1980, Wheeler 1942,
   Mosig 1988).
2. **Cross-module integration** — ``test_full_design_flow.py``
   builds a 3-shape coupled-coil layout, runs every analysis and
   every export format end-to-end, and verifies internal
   consistency (e.g. skew-segment kernel ↔ parallel-Grover limit
   to ~1e-6 relative).
3. **Binary cross-validation via golden artifacts** — the parent
   ``asitic-re`` repo runs the legacy binary under
   ``qemu-i386-static + xvfb-run`` for a canonical set of test
   cases and dumps the parsed ``Geom`` outputs as JSON into
   ``tests/data/validation/``. reASITIC's
   ``test_against_golden_artifacts.py`` loads the JSONs and
   compares, with configurable numerical tolerances
   (``REASITIC_ARTIFACT_REL_TOL`` default 0.001,
   ``REASITIC_ARTIFACT_ABS_TOL`` default 1e-3).

The reASITIC test suite needs **neither the binary nor QEMU at
runtime** — only the static JSON artifacts. This keeps the
UC-Berkeley-licensed binary out of the Python wheel / CI image
while still anchoring the port to real reference data.

[asitic]: https://rfic.eecs.berkeley.edu/~niknejad/asitic.html
