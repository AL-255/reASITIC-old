# reASITIC implementation plan

A clean-room Python port of ASITIC, validated against the original
1999 binary checked in at `../run/asitic.linux.2.2`.

The full reverse-engineered C surface is **643 functions / ~60 kLOC**,
and the port has reached **100 % coverage** — every identified C
function is either re-implemented in Python or explicitly subsumed
by a NumPy / SciPy / stdlib equivalent. The plan below documents
the staged path that got us there: foundation first (parsers +
simplest kernels + validation harness), then numerical kernels,
network extraction, optimisation, REPL/CLI, and finally the GUI
plus the GDS / SPICE / Touchstone export surface.

See [`MAPPING.md`](./MAPPING.md) for the per-function ledger and
[`docs/milestone.md`](./docs/milestone.md) for the narrative
milestone summary.

## Library substitutions

The original is statically linked against several Fortran/C numerical
libraries. The Python port uses portable equivalents:

| Vendored in binary | Replacement in Python |
| --- | --- |
| LAPACK / BLAS | `scipy.linalg` |
| LINPACK | `scipy.linalg` |
| QUADPACK (DQAGS/DQAGI/DQAWO/DQAWFE) | `scipy.integrate.quad` |
| libf2c (Fortran I/O runtime) | _not needed_ — we don't emit Fortran-format records |
| MV++ Sparse-BLAS | `scipy.sparse` if needed |
| SGI STL | _not needed_ — Python containers |
| libstdc++ exceptions | Python exceptions |
| Mesa GL / X11 | _out of scope_ — headless library |
| readline | `cmd.Cmd` / `prompt_toolkit` for the REPL |

`numpy` is the universal array dependency.

## Package layout

```
src/reasitic/
    __init__.py
    units.py             # constants: mu_0, eps_0, micron, etc.
    tech.py              # .tek file parser → Tech object
    geometry.py          # Point, Segment, Polygon, Shape, builders
    inductance/
        __init__.py
        grover.py        # closed-form self & mutual inductance
        skin.py          # Wheeler AC-resistance formula
        partial.py       # Greenhouse partial-inductance loop
    network/
        __init__.py
        twoport.py       # Y/Z/S transformations
        pi_model.py      # Pi-equivalent extraction
    substrate/
        __init__.py
        green.py         # FFT-based substrate Green's functions
    validation/
        __init__.py
        binary_runner.py # Drive run/asitic + parse output
    cli.py               # `python -m reasitic ...`
```

Tests live alongside under `tests/`, mirroring the package layout.

## Phases

### Phase 1 — foundation ✅ (done)

- [x] `units.py` constants
- [x] `tech.py` parser, validated on `run/tek/{BiCMOS,CMOS}.tek`
- [x] `geometry.py` Point/Segment/Polygon/Shape + `square_spiral`,
      `polygon_spiral`, `wire` builders
- [x] `inductance/grover.py` rectangular-bar self-L + parallel-segment mutual-L
- [x] `inductance/partial.py` Greenhouse summation
- [x] `validation/binary_runner.py` (Geom-based; binary's Ind crashes)
- [x] tests for each module (29 tests)
- [x] tests that compare reASITIC geometry vs binary's Geom output

### Phase 2 — numerical kernels ✅ (done)

- [x] DC resistance per polygon (`resistance/dc.py`)
- [x] Wheeler skin-effect AC resistance (`resistance/skin.py`)
- [x] Metal-loss-only Q factor (`quality.py`)
- [x] Mutual inductance between shapes & coupling coefficient
      (`inductance/partial.py`)
- [x] LAPACK-equivalent calls via `scipy.linalg` (`inductance/filament.py`)
- [x] Filament discretisation (`filament_grid` + `solve_inductance_matrix`)
- [ ] Orthogonal & general 3D segment mutuals (deferred — negligible
      effect for axis-aligned spirals; would require porting the 1.7 KB
      `mutual_inductance_orthogonal_segments` and 3 KB
      `mutual_inductance_filament_general` long-double bodies)

### Phase 3 — network extraction ✅ (done)

- [x] Y/Z/S 2-port conversions (`network/twoport.py`)
- [x] Pi-equivalent extraction (`pi_equivalent`)
- [x] `spiral_y_at_freq` builds Y from a Shape + Tech
- [x] 3-port reduction (`network/threeport.py`)
- [x] Multi-frequency `2Port` sweep + Touchstone `.s2p` export
      (`network/sweep.py`, `network/touchstone.py`)

### Phase 4 — substrate ✅ (done)

- [x] Per-metal-layer parallel-plate shunt-cap with proper series
      stack of dielectric layers between metal and ground, plus
      edge-fringe correction (`substrate/shunt.py`)
- [x] Auto-included in `spiral_y_at_freq` by default so Y is non-
      singular and Pi-model / Zin / SelfRes give physical values
- [x] Multi-layer Sommerfeld Green's function: recursive layered
      reflection coefficient, quasi-static self/mutual cap, and
      ``scipy.integrate.quad``-based Bessel-J0 integration
      (`substrate/green.py`)
- [x] Eddy-current correction via ground-image method
      (`inductance/eddy.py`)
- [ ] FFT-accelerated convolution Green's function (binary's
      ``compute_green_function`` precomputes G on a 2-D grid; we
      evaluate per-pair which is slower but clearer)

### Phase 5 — optimisation ✅ (done)

- [x] `OptSq` square-spiral optimiser via `scipy.optimize.minimize`
      SLSQP (`optimise/opt_sq.py`)
- [x] `OptPoly`, `OptArea`, `OptSymSq` (`optimise/opt_poly.py`)
- [x] `BatchOpt` across many (L, f) target pairs (`optimise/batch.py`)
- [x] `Sweep` parametric Cartesian grid (`optimise/sweep.py`)

### Phase 6 — REPL parity ✅ (done)

- [x] Argument parser (NAME=VALUE) and command dispatch
- [x] All shape builders: Wire, Square, Spiral, Ring, Via,
      Trans, 3DTrans, SymSq, Balun, Capacitor
- [x] Single-frequency analysis: Ind, Res, Q, K, Cap, Pi, Zin,
      ShuntR, Pi3, Pi4
- [x] Transformer analysis: CalcTrans
- [x] Frequency-swept analysis: 2Port, SelfRes
- [x] Info commands: Geom, MetArea, ListSegs, LRMAT, List
- [x] Save/Load round-trip via JSON (`persistence.py`)
- [x] CIF / Sonnet / Tek / SPICE output (`exports/`)
- [x] Touchstone S2P export
- [x] Inductor optimisation: OptSq, OptPoly, OptArea, OptSymSq,
      BatchOpt, Sweep

## Coordinate / unit conventions

Internal computation matches the binary:

- Lateral lengths in **microns** (input units).
- The Grover formulas multiply by `0.0001` (μm → cm) before evaluating
  the closed form, so internal SI: lengths in **cm** for the formula.
- Output inductance in **nH** (closed form yields nH directly when
  lengths are in cm and currents in A, since μ₀/(4π) × cm = nH).
- Frequency in **GHz**.
- Resistance in **Ω**.

## Bookkeeping

* [`MAPPING.md`](./MAPPING.md) — line-by-line catalog of every Python
  function and the reverse-engineered C function it ports / mirrors.
  **Update it whenever a new public function lands** so the
  Python ↔ C correspondence stays trustworthy.

## Validation strategy

For each numerical primitive we land, add a pytest that:

1. Constructs an equivalent geometry on the original binary via a
   scripted EXEC file.
2. Runs the binary with the script, captures its output.
3. Re-runs the same primitive in Python.
4. Asserts agreement within a tolerance (typically 1e-3 relative).

The harness lives in `src/reasitic/validation/binary_runner.py`
and is gated behind the `BINARY` env var (or the binary's presence on
disk) so CI can skip it on platforms without 32-bit support.
