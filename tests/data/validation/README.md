# Golden artifacts from the legacy ASITIC binary

Each test case in this directory comes from running one canonical
command sequence against the original 1999 ASITIC binary, captured
into a JSON ground-truth record plus a small bundle of binary
artifacts:

| File | Source | Purpose |
|---|---|---|
| `<stem>.json`               | parsed binary output                       | Geometry + electrical ground truth |
| `layouts/<stem>.cif`        | `CIFSAVE <name> <file>`                    | Native ASITIC layout export (Caltech Intermediate Form) |
| `layouts/<stem>.gds`        | `klayout` cif → GDSII conversion           | Modern GDSII for downstream EDA tooling |
| `analysis/<stem>.s2p`       | `2Port <name> … S polar slow <file>`       | Touchstone S-parameters across the swept frequency range |
| `analysis/<stem>.stable.log`| stdout of MetArea / Ind / Res / per-freq Pi2 etc. | Raw transcript of the multi-frequency stable analysis session |
| `analysis/<stem>.sweep.log` | stdout of the 2Port sweep session          | Raw transcript of the sweep session |

Artifacts are **regenerated in the parent ``asitic-re`` repo** by
running the binary under user-mode QEMU (``qemu-i386-static``)
with ``xvfb-run`` providing a virtual X11 display, then piping the
emitted CIF through ``klayout`` in batch mode. See
``../../../BINARY_VALIDATION.md`` for the QEMU rationale and
``../../../TESTSET.md`` for the case index and regeneration
workflow; the regeneration script lives at
``../../scripts/regen_validation_artifacts.py``.

reASITIC tests load the JSON directly. The CIF / GDS / S2P / log
artifacts are intentionally **not tracked in git** (see
``../../.gitignore``) — they're large derivative outputs of the
UC-Berkeley-licensed binary and any user can re-derive them by
running the regen script. Tests that consume them should treat
their absence as a skip condition.

## JSON schema (v4)

```json
{
  "name": "sq_200x10x2x3_m3",
  "build_command": "SQ NAME=B:LEN=200:W=10:S=2:N=3:METAL=m3:XORG=200:YORG=200",
  "shape_name": "B",
  "tech": "BiCMOS",

  "geom": {
    "name": "B", "kind": "Square spiral",
    "spiral_l1_um": 200.0, "spiral_l2_um": 200.0,
    "spiral_spacing_um": 2.0, "spiral_turns": 3.0, "width_um": 10.0,
    "total_length_um": ..., "total_area_um2": ...,
    "location": [200.0, 200.0], "n_segments": ...,
    "...other shape kinds populate other fields...": null
  },

  "layout": {
    "cif": "layouts/sq_200x10x2x3_m3.cif",
    "gds": "layouts/sq_200x10x2x3_m3.gds"
  },

  "analysis": {
    "metal_area_um2": ...,
    "ind_dc_nh": ...,
    "res_dc_ohm": ...,
    "freq_points_ghz": [1.0, 5.0],
    "res_hf_ohm":   [..., ...],
    "q":            [..., ...],
    "lrmat_l_h":    [..., ...],
    "lrmat_r_ohm":  [..., ...],
    "pi2_points": [
      {"freq_ghz": 1.0, "q_three": [..., ..., ...],
       "L_nh": ..., "R_ohm": ...,
       "Cs1_ff": ..., "Rs1_ohm": ...,
       "Cs2_ff": ..., "Rs2_ohm": ...,
       "f_res_ghz": ...}
    ],
    "cap_points": [
      {"freq_ghz": 1.0, "cap_ff": ..., "cap_r_ohm": ...}
    ],
    "stable_session_rc": -3, "stable_session_seconds": 7.4,
    "sweep_session_rc": -3, "sweep_session_seconds": 37.3,
    "s2p_freq_count": 10,
    "commands_run": ["SQ NAME=...", "MetArea B", ...],
    "errors": []
  },

  "artifacts": {
    "stable_log": "analysis/sq_200x10x2x3_m3.stable.log",
    "sweep_log":  "analysis/sq_200x10x2x3_m3.sweep.log",
    "s2p":        "analysis/sq_200x10x2x3_m3.s2p"
  },

  "captured_with": "qemu-i386-static + asitic.linux.2.2 + xvfb-run",
  "schema_version": 4
}
```

### `geom` block

| field | populated for |
|---|---|
| `length_um`, `width_um`, `metal` | `Wire` only |
| `spiral_l1_um`, `spiral_l2_um` | `Square spiral`, `Symmetric square spiral`, `Transformer` (L1/L2 = outer dims for `Square spiral`/`Transformer`; for `Symmetric square spiral`, L1 = outer dim, L2 = ILEN transition spacing) |
| `spiral_spacing_um`, `spiral_turns` | All spiral kinds (S, N) — except `Transformer` uses `primary_turns` / `secondary_turns` |
| `radius_um`, `n_sides` | `Polygon spiral`, `Symmetric polygon spiral` |
| `primary_width_um`, `secondary_width_um`, `primary_turns`, `secondary_turns` | `Transformer` (used for both `TRANS` and `BALUN`) |
| `total_length_um`, `total_area_um2`, `location`, `n_segments` | All shapes |

`User defined` (MMSQ, CAPACITOR) and `Ring` (RING) only populate
the totals/location block — the binary doesn't emit shape-specific
parameters for those. The build command is preserved so consumers
can recover the original parameters.

### `analysis` block

The analysis runs in two QEMU sessions per case:

* **Stable session** — issues `MetArea`, `Ind` (DC), `Res` (DC),
  then for each entry in `freq_points_ghz` a 5-tuple of `ResHF`,
  `Q`, `Pi2`, `Cap`, `LRMAT`. All of these execute cleanly under
  QEMU. (Note: `Ind <freq>`, `Res <freq>` and the original `Pi`
  command segfault under QEMU; `Pi2` is the QEMU-stable
  replacement for AC analysis.)
* **Sweep session** — issues a single
  `2Port <name> <f1> <f2> <step> S polar slow <file>` to capture
  the full Touchstone S-parameter sweep. Always uses `slow` mode;
  `fast` mode segfaults under QEMU on the very first frequency
  point.

With the default `(1.0, 10.0, 1.0)` GHz sweep, every case
produces 10 S2P data points.

### `pi2_points[]` reference

Each Pi2 record is a dump of the binary's two-port π-equivalent
circuit at one frequency. The fields:

| field | meaning |
|---|---|
| `freq_ghz` | frequency at which the Pi2 model was extracted |
| `q_three` | three Q-factor variants the binary reports (single-port, port 1 grounded, port 2 grounded) |
| `L_nh`, `R_ohm` | series branch — total inductance and AC resistance |
| `Cs1_ff`, `Rs1_ohm` | port-1 substrate shunt cap & resistance |
| `Cs2_ff`, `Rs2_ohm` | port-2 substrate shunt cap & resistance |
| `f_res_ghz` | self-resonant frequency the binary computes from the model |

## Notes on the GDS files

* CIF (and ASITIC) preserves **named** layers (``LM3``, ``LVIA3``,
  ``LM2``, ``LMSUB``). klayout assigns GDSII numeric layer
  ``(N, 0)`` in the order each name first appears in the CIF, so
  the layer numbering is **per-file** and not globally consistent
  across cases. For authoritative layer identity, parse the CIF.
* All polygons are written to datatype 0.
* Database unit is 1 nm (``dbu = 0.001 um``), inherited from the
  klayout default.

## Notes on the S2P files

* Touchstone v1, magnitude/angle representation
  (`# GHZ S MA`).
* Reference impedance is the ASITIC default (50 Ω).
</content>
</invoke>