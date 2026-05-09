# reASITIC tutorial

A step-by-step walk-through of the design flow for an integrated
spiral inductor: tech-stack load → geometry build → analysis →
optimisation → SPICE/Touchstone export. Every snippet is runnable
against the BiCMOS sample tech file under ``../run/tek/BiCMOS.tek``.

## 1. Install

```bash
git clone https://github.com/AL-255/reASITIC.git
cd reASITIC
pip install -e ".[dev]"
```

You should now have:

* ``import reasitic`` from any Python program
* the ``reasitic`` REPL on your shell `$PATH`
* ``python -m reasitic.cli`` as an alternative entry point

Verify with::

```bash
reasitic --help
python -c "import reasitic; print(reasitic.__version__)"
```

## 2. Load a technology stack

ASITIC ships with two sample tech files. They describe the substrate
layers, metal layers, vias, and chip dimensions::

```python
import reasitic
tech = reasitic.parse_tech_file("../run/tek/BiCMOS.tek")
print(tech.chip)
for m in tech.metals:
    print(f"  {m.name}: t={m.t}μm, rsh={m.rsh}Ω/sq, layer={m.layer}")
```

Output:

```
Chip(chipx=512.0, chipy=512.0, fftx=128, ffty=128, ...)
  msub: t=0.4μm, rsh=0.035Ω/sq, layer=1
  m2: t=0.8μm, rsh=0.05Ω/sq, layer=2
  m3: t=2.0μm, rsh=0.02Ω/sq, layer=2
```

m3 is the thickest, lowest-resistance layer — ideal for spiral
inductors.

## 3. Build a spiral

A square spiral is the most common topology::

```python
sp = reasitic.square_spiral(
    "L1",
    length=200.0,    # outer side, μm
    width=10.0,      # metal trace width, μm
    spacing=2.0,     # turn-to-turn spacing, μm
    turns=3.0,
    tech=tech,
    metal="m3",
)
print(f"{len(sp.polygons)} turns, {len(sp.segments())} total segments")
```

Each turn becomes one rectangular polygon; the spiral collapses
inward by ``width + spacing`` per turn.

reASITIC also ships with 9 other geometry builders for transformers,
baluns, MIM caps, vias, polygon spirals, and centre-tapped variants.
See `python -m reasitic help <builder>` for parameters.

## 4. Analyse: L, R, Q, Pi-model

```python
# Self-inductance from Greenhouse partial-inductance summation
L = reasitic.compute_self_inductance(sp)
print(f"L = {L:.3f} nH")

# DC and AC resistance
R_dc = reasitic.compute_dc_resistance(sp, tech)
R_ac = reasitic.compute_ac_resistance(sp, tech, freq_ghz=2.4)
print(f"R_dc = {R_dc:.3f} Ω, R_ac(2.4 GHz) = {R_ac:.3f} Ω")

# Metal-only Q factor
Q = reasitic.metal_only_q(sp, tech, freq_ghz=2.4)
print(f"Q(2.4 GHz) = {Q:.2f}")

# Full Pi-equivalent (L_series, R_series, C_p1, C_p2)
from reasitic.network.analysis import pi_model_at_freq
pi = pi_model_at_freq(sp, tech, freq_ghz=2.4)
print(f"Pi: L={pi.L_nH:.3f} nH, R={pi.R_series:.3f} Ω,"
      f" C_p1={pi.C_p1_fF:.2f} fF")
```

The Pi-model auto-includes the substrate shunt-cap from the
parallel-plate stack. To see Pi without substrate (pure series):
``spiral_y_at_freq(sp, tech, f, include_substrate=False)``.

## 5. Frequency sweep + Touchstone export

For circuit-level simulation you typically want a ``.s2p`` file
covering your operating band::

```python
from reasitic.network import (
    linear_freqs,
    two_port_sweep,
    write_touchstone_file,
)

fs = linear_freqs(0.1, 10.0, 0.1)  # 0.1 to 10 GHz, 0.1 GHz steps
sweep = two_port_sweep(sp, tech, fs)
write_touchstone_file("L1.s2p", sweep.to_touchstone_points(param="S"))
print(f"Wrote {len(fs)} frequency points")
```

The ``L1.s2p`` file loads directly into ngspice, ADS, AWR, Sonnet,
or any other RF tool that reads Touchstone v1.

For a SPICE Pi-model at one operating point::

```python
from reasitic.exports import write_spice_subckt_file
write_spice_subckt_file("L1.sp", sp, tech, freq_ghz=2.4)
```

## 6. Optimisation: maximise Q for a target L

Use ``OptSq`` to find the geometry that maximises Q at a given L
target and frequency::

```python
from reasitic.optimise import optimise_square_spiral
res = optimise_square_spiral(
    tech, target_L_nH=2.0, freq_ghz=2.4, metal="m3",
)
print(f"Optimal: L={res.length_um:.0f} W={res.width_um:.0f}"
      f" S={res.spacing_um:.1f} N={res.turns:.1f}"
      f" → L={res.L_nH:.3f} nH, Q={res.Q:.1f}")
```

For polygon spirals use ``optimise_polygon_spiral``; for area
minimisation use ``optimise_area_square_spiral``; for symmetric
designs use ``optimise_symmetric_square``.

Multi-target (e.g. multiple frequency bands) uses ``BatchOpt``::

```python
from reasitic.optimise import batch_opt_square
arr = batch_opt_square(
    tech,
    targets=[(1.0, 5.0), (2.0, 2.4), (5.0, 1.0)],
    metal="m3",
)
print(arr)
```

## 7. Multi-frequency design report

The one-stop report::

```python
from reasitic.report import design_report
rpt = design_report(sp, tech, freqs_ghz=[1.0, 2.4, 5.0])
print(rpt.format_text())
```

```
=== Design report for <L1> ===
  L_dc      = 2.917 nH
  R_dc      = 4.224 Ω
  Area      = 94 080.00 μm²
  f_SR      = 11.93 GHz

  f_GHz   L_nH    R_ac     Q   C_p1   C_p2
  1.000   2.917   4.297   4.27  61.0  61.0
  2.400   2.917   4.498   9.78  61.0  61.0
  5.000   2.917   3.571  25.67  61.0  61.0
```

## 8. Cross-validate against the legacy ASITIC binary

reASITIC ships with a binary-driver. The legacy ``Ind`` command
crashes on modern Linux due to a bug in the 1999 build, but
geometry-only commands (``Geom``, ``MetArea``) work and are the
basis for cross-validation::

```python
from reasitic.validation import BinaryRunner
runner = BinaryRunner.auto()  # uses ../run/asitic + xvfb-run
result = runner.geom("SQ NAME=L:LEN=200:W=10:S=2:N=3:METAL=m3", "L")
print(f"Binary reports: L1={result.spiral_l1_um}, segments={result.n_segments}")
```

For numerical correctness against published references see
``tests/test_physics_validation.py`` (Greenhouse, Mohan, Niknejad
formula cross-checks).

## 9. The REPL

For interactive exploration, run the REPL::

```bash
reasitic -t ../run/tek/BiCMOS.tek
```

```
reASITIC> SQ NAME=L1:LEN=200:W=10:S=2:N=3:METAL=m3
reASITIC> IND L1
L(L1) = 2.917375 nH
reASITIC> Q L1 2.4
Q_metal(L1, 2.4 GHz) = 9.78
  L = 2.9174 nH, R_ac = 4.4984 Ohm
reASITIC> REPORT L1 1.0 2.4 5.0
=== Design report for <L1> ===
...
reASITIC> QUIT
```

The REPL recognises ~105 commands (``HELP`` lists them; ``HELP <cmd>``
gives details).  See [`CLI_REFERENCE.md`](./CLI_REFERENCE.md) for the
auto-generated full table.

## 10. Where to next?

* [`COOKBOOK.md`](./COOKBOOK.md) — 10 design recipes covering common scenarios
* [`MAPPING.md`](./MAPPING.md) — per-function correspondence to the
  reverse-engineered C source (**643 / 643 = 100 %** covered)
* [`docs/milestone.md`](./docs/milestone.md) — narrative summary of
  the 100 %-coverage milestone
* [`PLAN.md`](./PLAN.md) — implementation plan and remaining TODOs
* `examples/` — runnable Python scripts
* `benchmarks/` — performance regression checks
