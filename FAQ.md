# reASITIC FAQ

Common questions and troubleshooting tips. For step-by-step
walkthroughs see [`TUTORIAL.md`](./TUTORIAL.md); for design recipes
see [`COOKBOOK.md`](./COOKBOOK.md).

## Q: The legacy ``run/asitic.linux.2.2`` binary segfaults when I run ``Ind`` headlessly.

That's a known issue. The 1999 binary's numerical commands (``Ind``,
``Cap``, ``Q``, ``2Port``) crash in headless mode on modern Linux —
traced to an uninitialised pointer at offset −4 in
``cmd_inductance_compute``. Geometry-only commands (``Geom``,
``MetArea``, ``ListSegs``) work and form the basis of our binary
cross-validation harness.

For numerical correctness, reASITIC validates against published
Greenhouse / Mohan / Niknejad formulas instead — see
``tests/test_physics_validation.py``.

## Q: Why do I need ``xvfb-run`` to drive the binary?

The 1999 binary tries to open an X11 display even in ``--ngr``
("no graphics") mode — because some startup paths still call
``XOpenDisplay`` unconditionally. ``xvfb-run`` provides a virtual
framebuffer X server that satisfies that call without needing a
real display. reASITIC's ``BinaryRunner.auto()`` enables it
automatically when no ``DISPLAY`` env var is set.

If you don't have ``xvfb-run`` available, the binary tests
auto-skip. Install with::

```bash
sudo apt install xvfb         # Ubuntu / Debian
sudo dnf install xorg-x11-server-Xvfb   # Fedora
```

## Q: I wrote a script that drives the binary via ``subprocess.run`` and my Python interpreter crashes.

The legacy binary's ``libstdc++-libc6.1-1.so.2`` propagates a
SIGQUIT to its process group when the X server tears down. Make
sure you use ``start_new_session=True`` (or ``preexec_fn=os.setsid``)
so the SIGQUIT stays within the child group::

```python
subprocess.run(
    [...],
    start_new_session=True,  # ← essential
    capture_output=True,
)
```

reASITIC's ``BinaryRunner`` already does this.

## Q: My spiral has a tiny inductance (< 0.1 nH) — is the result trustworthy?

Greenhouse summation for sub-nH inductors is dominated by
self-inductance terms; the closed-form Grover bar self-L matches
the binary to ~1 % at low frequency. Sources of error to watch for:

* **Inner-radius collapse** — if ``length / (width + spacing)`` is
  too small, the inner turns collapse into 0-width strips. Check
  ``len(spiral.polygons) == int(turns)`` to confirm.
* **Self-resonance proximity** — if the operating frequency is
  > 0.5 × f_SR, the L vs. f curve becomes very steep; report L_dc
  rather than the f-dependent value.

For higher-confidence numbers, use ``solve_inductance_mna`` with
``n_w=2, n_t=2`` (filament-level current crowding) and validate
against published formulas via ``mohan_modified_wheeler``.

## Q: How accurate is the substrate shunt-cap model?

Our default substrate model is a per-metal-layer parallel-plate
capacitance with edge fringe correction (``substrate/shunt.py``).
It's good for first-order analysis (~10–20 % error vs. EM
simulation) but doesn't capture lateral coupling.

For better accuracy, reASITIC ships with a Sommerfeld-integral
Green's function (``substrate/green.py``) and an FFT-accelerated
2D grid (``substrate/fft_grid.py``). Use those for substrate-
critical designs.

## Q: My ``OPTSQ`` run never converges to the target L.

Three common causes:

1. **L target outside the geometric reach** — ``length=50–500 μm``,
   ``W=2–30 μm``, ``N=1–10`` typically yield L from ~0.3 nH to
   ~30 nH. Outside that range, widen the bounds:
   ```python
   optimise_square_spiral(
       tech, target_L_nH=50.0, freq_ghz=2.4,
       length_bounds=(100, 1000),
       turns_bounds=(1, 20),
   )
   ```
2. **L tolerance too tight** — default is ±5 %; loosen to ±10 % via
   ``L_tolerance=0.10``.
3. **Optimum at a boundary** — check ``res.length_um == max_l`` etc.;
   if so the constraint is active and you may need to widen.

## Q: I want the SPICE Pi-model at multiple frequencies. Is there a sweep?

Use ``write_spice_broadband_file``::

```python
from reasitic.exports import write_spice_broadband_file
write_spice_broadband_file(
    "L1_broadband.sub", spiral, tech,
    freqs_ghz=[1.0, 2.4, 5.0, 10.0],
)
```

Each frequency produces a named ``.subckt`` block that you can
``.include`` in your SPICE deck and select with ``.alter``.

## Q: How do I cross-validate against measured data?

Use the Touchstone reader to load measured S-parameter files::

```python
from reasitic.network import read_touchstone_file
meas = read_touchstone_file("measured.s2p")
# Compare meas.points[i].matrix against your simulated S
```

For pad de-embedding, use ``deembed_pad_open`` /
``deembed_pad_open_short`` from ``reasitic.network``.

## Q: Performance is slow on large spirals (>50 turns). What can I tune?

1. **Use the closed-form Greenhouse** (``compute_self_inductance``)
   instead of the filament solver — it's O(N²) but the constant is
   small (~30 μs per pair).
2. **Limit ``n_w * n_t``** in ``solve_inductance_matrix`` —  N×N×4
   filaments is the default; on a 100-segment spiral that's 40,000
   matrix entries. ``n_w=1, n_t=1`` is usually enough below 5 GHz.
3. **Bench it** — ``benchmarks/bench_inductance.py`` shows per-
   function timings. Run it before and after a change to verify
   you haven't regressed.

## Q: Can I save my session in the binary's BSAVE format?

No. reASITIC uses JSON for portability — the binary's BSAVE format
is tied to the 32-bit ELF's struct layout and not stable across
compilers. The aliases ``BSAVE``, ``BLOAD``, ``BWRITE``, ``BREAD``
all route to JSON SAVE / LOAD. Files round-trip cleanly between
reASITIC sessions but don't load into the original binary.

## Q: How do I add a new geometry builder?

1. Add a function in ``src/reasitic/geometry.py`` returning a
   ``Shape`` object.
2. Re-export from ``src/reasitic/__init__.py``.
3. Add a CLI handler ``cmd_<name>`` in ``src/reasitic/cli.py`` and
   wire into the dispatcher.
4. Add a help entry in ``_COMMAND_HELP``.
5. Regenerate the CLI reference: ``python scripts/generate_cli_reference.py
   > CLI_REFERENCE.md``.
6. Write tests in ``tests/test_more_geometry.py`` (or a new file).
7. Add a row to ``MAPPING.md`` under "geometry builders".

## Q: I get ``ImportError`` for ``matplotlib`` when I import ``reasitic.plot``.

matplotlib is an *optional* dependency. Install with the ``plot``
extra::

```bash
pip install reASITIC[plot]
```

The rest of the library works without it; ``reasitic.plot``'s
functions raise a clear ``ImportError`` only if matplotlib isn't
available.

## Q: How can I contribute?

The project is a clean-room Python rewrite of the 1999 ASITIC
binary. **All 643 reverse-engineered C functions are now
covered** — either re-implemented in Python or explicitly subsumed
by a NumPy / SciPy / stdlib equivalent. See
[`MAPPING.md`](./MAPPING.md) for the per-function ledger and
[`docs/milestone.md`](./docs/milestone.md) for the narrative
summary. Future contributions tend to fall into:

* Polishing — lift the unit-test line coverage (currently 90 %)
  toward 95 %+.
* Numerical validation — cross-check the Python kernels against
  the legacy binary's outputs.
* Performance — benchmark and tune the inner loops.
* Documentation — more recipes / tutorials / examples.

The pre-commit hook (``scripts/pre_commit.sh``) runs ruff + mypy +
pytest; CI (``.github/workflows/ci.yml``) runs them across Python
3.10–3.13.
