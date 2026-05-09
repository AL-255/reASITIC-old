# reASITIC cookbook

Worked design recipes for common RF inductor / transformer scenarios.
Each section includes a runnable Python snippet using the ``reasitic``
public API and shows the expected output. All examples assume the
BiCMOS technology file is at ``../run/tek/BiCMOS.tek``.

---

## 1. Pick a 1-nH inductor for a 5 GHz LO

For an LO tank, you want **L** to set the resonant frequency, **Q**
high to reduce phase noise, and footprint small enough to fit the
floorplan. Use ``OptSq`` to find the geometry that maximises Q for
your L target.

```python
import reasitic
from reasitic.optimise import optimise_square_spiral

tech = reasitic.parse_tech_file("../run/tek/BiCMOS.tek")
res = optimise_square_spiral(
    tech, target_L_nH=1.0, freq_ghz=5.0, metal="m3",
    length_bounds=(50, 300),  # tighten footprint
)
print(f"L={res.length_um:.0f} W={res.width_um:.1f} S={res.spacing_um:.1f}"
      f" N={res.turns:.2f} → L={res.L_nH:.2f} nH, Q={res.Q:.0f}")
```

```
L=205 W=30.0 S=2.7 N=2.04 → L=1.04 nH, Q=27
```

The optimiser picks a wide-trace, low-turn geometry — minimising
series resistance dominates Q for small-L designs.

---

## 2. 5 nH for 1 GHz with substrate-loss-limited Q

At 1 GHz the substrate cap shunts the spiral terminals, capping Q
even with thick metal. The ``REPORT`` command exposes both the metal-
loss Q and the self-resonance frequency:

```python
sp = reasitic.square_spiral(
    "L5",
    length=400, width=20, spacing=2, turns=4,
    tech=tech, metal="m3",
)
from reasitic.report import design_report
print(design_report(sp, tech, freqs_ghz=[1.0]).format_text())
```

```
=== Design report for <L5> ===
  L_dc      = 7.34 nH
  R_dc      = 4.55 Ω
  Area      = 419 200 μm²
  f_SR      = 6.5 GHz

  f_GHz   L_nH    R_ac    Q   C_p1   C_p2
  1.000   7.34    4.86   9.5  254.0  254.0
```

The 254 fF substrate cap puts f_SR around 6.5 GHz — fine for 1 GHz
operation. To raise f_SR, reduce the area: use ``OPTAREA`` to find
the smallest spiral meeting the L target.

---

## 3. Differential balun with 1:1 turns ratio

A planar balun is two stacked counter-wound coils. ``balun()`` builds
the geometry; ``CALCTRANS`` reports the differential parameters.

```python
b = reasitic.balun(
    "BAL",
    length=200, width=10, spacing=2, turns=3,
    tech=tech, metal="m3", metal2="m2",
)
# Treat the two coils as separate shapes for analysis
from reasitic.network.analysis import calc_transformer
import reasitic.geometry as geo

# Re-build as two separate coils for CalcTrans
pri = reasitic.square_spiral("PRI", length=200, width=10, spacing=2,
                              turns=3, tech=tech, metal="m3")
sec = reasitic.square_spiral("SEC", length=200, width=10, spacing=2,
                              turns=3, tech=tech, metal="m2")
res = calc_transformer(pri, sec, tech, freq_ghz=2.4)
print(f"L_pri={res.L_pri_nH:.2f}, L_sec={res.L_sec_nH:.2f},"
      f" k={res.k:.3f}, n={res.n_turns_ratio:.3f}")
```

```
L_pri=2.32, L_sec=2.32, k=0.654, n=1.000
```

For a balun the goal is **k as close to 1 as possible**. To raise k,
move the two coils closer (or use the same metal layer with
interleaving — see :func:`reasitic.transformer`).

---

## 4. Frequency-swept S-parameter export for SPICE

To use a reASITIC-extracted spiral in SPICE, dump a Touchstone S2P
file or a SPICE Pi-model sub-circuit at the operating point:

```python
from reasitic.network import linear_freqs, two_port_sweep, write_touchstone_file
from reasitic.exports import write_spice_subckt_file

sp = reasitic.square_spiral(
    "L1", length=200, width=10, spacing=2, turns=3,
    tech=tech, metal="m3",
)

# Touchstone .s2p across the 0.1 - 10 GHz band
fs = linear_freqs(0.1, 10.0, 0.1)
sweep = two_port_sweep(sp, tech, fs)
write_touchstone_file("L1.s2p", sweep.to_touchstone_points(param="S"))

# SPICE Pi-model at the operating point only
write_spice_subckt_file("L1.sub", sp, tech, freq_ghz=2.4)
```

The ``L1.sub`` file is a complete ``.subckt L1_pi p1 p2 gnd ... .ends``
block that drops directly into ngspice / Hspice / LTspice.

---

## 5. Cross-validate against the legacy ASITIC binary

reASITIC ships with a binary-driver that compares geometry output
against the original ASITIC binary. Useful for catching regressions
when you change a kernel.

```python
from reasitic.validation import BinaryRunner

runner = BinaryRunner.auto()  # uses ../run/asitic + xvfb-run
result = runner.geom("SQ NAME=L:LEN=200:W=10:S=2:N=3:METAL=m3", "L")
print(f"Binary reports: spiral_l1={result.spiral_l1_um}, segments={result.n_segments}")
```

The binary's numerical commands (``Ind``, ``Cap``, ``2Port``)
segfault in headless mode (legacy library bug), so we cross-check
geometry only. For numerical correctness, see ``tests/test_physics_validation.py``
which validates against published Greenhouse / Mohan formulas.

---

## 6. Optimisation sweep across multiple operating points

For a multi-band radio you may want different spirals at each band.
``BatchOpt`` runs ``OptSq`` across a list of (L, f) targets:

```python
from reasitic.optimise import batch_opt_square

targets = [
    (1.0, 5.0),   # 1 nH at 5 GHz
    (2.0, 2.4),   # 2 nH at 2.4 GHz (Wi-Fi)
    (5.0, 1.0),   # 5 nH at 1 GHz
]
arr = batch_opt_square(tech, targets=targets, metal="m3")
print(arr)
```

Each row gives the best ``(length, width, spacing, turns, L_nH, Q)``
for its (target_L, freq) pair.

---

## 7. Differential transformer with optimal coupling

A differential pair is two interleaved coils on the same metal. The
``transformer`` builder creates them; ``CalcTrans`` reports k:

```python
import reasitic
from reasitic.network.analysis import calc_transformer

tech = reasitic.parse_tech_file("../run/tek/BiCMOS.tek")
t = reasitic.transformer(
    "T",
    length=200, width=10, spacing=2, turns=3,
    tech=tech, metal_primary="m3", metal_secondary="m3",
)
# Re-extract primary/secondary as separate coils for analysis
pri = reasitic.square_spiral(
    "P", length=200, width=10, spacing=2, turns=3,
    tech=tech, metal="m3",
)
sec = reasitic.square_spiral(
    "S", length=200, width=10, spacing=2, turns=3,
    tech=tech, metal="m3",
    x_origin=210,  # adjacent
)
print(calc_transformer(pri, sec, tech, freq_ghz=2.4))
```

A typical adjacent-coil planar transformer has k ≈ 0.4–0.6.
Move the coils closer (or interleave them on alternating metals)
to push k upward.

---

## 8. MIM capacitor with proper dielectric stack

For decoupling / RF tank caps, ASITIC's MIM model is two stacked
metal plates with the inter-layer oxide forming the dielectric:

```python
cap = reasitic.capacitor(
    "C1",
    length=50, width=50,        # 50 × 50 μm² plate
    metal_top="m3",             # 2 μm thick m3
    metal_bottom="m2",          # 0.8 μm thick m2
    tech=tech,
)
# Substrate cap from each plate
from reasitic.substrate import shape_shunt_capacitance
print(f"Total shunt cap: {shape_shunt_capacitance(cap, tech) * 1e15:.2f} fF")
```

The shunt cap captures the m2-to-substrate path (m3 sits above
m2 so its substrate path is longer).

---

## 9. Multi-metal series inductor (boosting L for fixed footprint)

The ``MMSquare`` inductor stacks multiple metal layers in series.
For the BiCMOS stack you can boost L by ~3× without changing
footprint by stacking m2+m3:

```python
mm = reasitic.multi_metal_square(
    "MM",
    length=200, width=10, spacing=2, turns=3,
    tech=tech, metals=["m2", "m3"],
)
print(f"L = {reasitic.compute_self_inductance(mm):.2f} nH")

# Compare with single-metal m3 only
single = reasitic.square_spiral(
    "S", length=200, width=10, spacing=2, turns=3,
    tech=tech, metal="m3",
)
print(f"Single-metal L = {reasitic.compute_self_inductance(single):.2f} nH")
```

Each additional metal layer adds roughly L_single nH (with mutual
coupling between the layers ~1, since they're co-located).

---

## 10. Parametric L-Q sweep visualisation

Sweep the spiral length and turns count, plot L and Q:

```python
import numpy as np
from reasitic.optimise import sweep_square_spiral

arr = sweep_square_spiral(
    tech,
    length_um=np.arange(100, 401, 50).tolist(),
    width_um=[10.0],
    spacing_um=[2.0],
    turns=np.arange(1.0, 6.0, 0.5).tolist(),
    freq_ghz=2.4,
    metal="m3",
)
# Now plot Q vs (L, N) using matplotlib (optional dep)
try:
    import matplotlib.pyplot as plt
    fig, ax = plt.subplots()
    Ls = sorted(set(arr["length_um"]))
    Ns = sorted(set(arr["turns"]))
    Q = arr["Q"].reshape(len(Ls), len(Ns))
    im = ax.imshow(Q, origin="lower",
                   extent=(min(Ns), max(Ns), min(Ls), max(Ls)),
                   aspect="auto", cmap="viridis")
    plt.colorbar(im, label="Q")
    ax.set_xlabel("Turns N")
    ax.set_ylabel("Length (μm)")
    plt.savefig("LQ_sweep.png", dpi=120)
except ImportError:
    pass
```

---

## See also

- ``examples/`` — runnable scripts that mirror these recipes.
- ``MAPPING.md`` — line-by-line port table to the reverse-engineered
  C source. Useful when chasing numerical discrepancies against the
  binary.
- ``PLAN.md`` — implementation phases and what's deferred.
