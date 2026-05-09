# reASITIC

```{include} ../README.md
:start-after: "<!-- DOCS-INTRO -->"
:end-before: "<!-- /DOCS-INTRO -->"
```

A clean-room Python re-implementation of the 1999 UC Berkeley **ASITIC**
RF-spiral inductor analysis tool, faithful to the original but powered
by NumPy / SciPy and a strict, fully type-annotated codebase.

```{toctree}
:caption: User guide
:maxdepth: 2

install
tutorial
cookbook
faq
cli
gui
```

```{toctree}
:caption: Reference
:maxdepth: 2

api/index
mapping
benchmarks
milestone
changelog
```

```{toctree}
:caption: Project
:maxdepth: 1
:hidden:

GitHub <https://github.com/AL-255/reASITIC>
```

## Quick install

```bash
pip install reASITIC          # base library
pip install reASITIC[plot]    # + matplotlib for plotting helpers
```

## At-a-glance

```python
import reasitic

tech = reasitic.parse_tech_file("BiCMOS.tek")
sp = reasitic.square_spiral(
    "L1", length=170, width=10, spacing=3, turns=2,
    tech=tech, metal="m3",
)
print(f"L = {reasitic.compute_self_inductance(sp):.3f} nH")
print(f"R = {reasitic.compute_ac_resistance(sp, tech, 2.4):.3f} Ω")
print(f"Q = {reasitic.metal_only_q(sp, tech, 2.4):.1f}")
```

## Feature surface

- **117 / 117** original REPL commands
- **669** unit / integration / regression tests, **90 %** line coverage
- **643 / 643** identified C functions covered (**100 %**) — see [milestone](milestone.md)
- **`mypy --strict`** clean across the entire public surface
- Greenhouse + Grover partial-inductance summation with filament-level
  current-crowding, Wheeler skin effect, substrate eddy correction
- Sommerfeld Green's-function substrate model, FFT-accelerated coupling grid
- 2-port Y/Z/S algebra, π / π3 / π4 / πX extraction, 3-port reduction,
  Touchstone v1 reader/writer
- Geometry builders (10): square / polygon / wire / ring / via /
  transformer / 3D-transformer / symmetric-square / balun / capacitor
- Round-trip CIF / Sonnet / SPICE / FastHenry / Tek / Tek 4014 exports
- SLSQP-driven `OptSq` / `OptPoly` / `OptArea` / `OptSymSq` / `BatchOpt`
- JSON-based session persistence, full-binary cross-validation harness

## Indices

- {ref}`genindex`
- {ref}`modindex`
- {ref}`search`
