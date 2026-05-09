# Golden artifacts from the legacy ASITIC binary

Each ``*.json`` file in this directory is a captured run of one
canonical command sequence against the original 1999 ASITIC
binary, parsed into a structured form.

These artifacts are **regenerated in the parent ``asitic-re``
repo** by running the binary under user-mode QEMU
(``qemu-i386-static``); see
``../../../BINARY_VALIDATION.md`` for setup details. The
regeneration script lives at
``../../scripts/regen_validation_artifacts.py`` (parent repo).

reASITIC tests load the artifacts directly, so the test suite
needs neither the binary nor QEMU at runtime — only the static
golden data. This avoids redistributing the UC-Berkeley-licensed
binary while still anchoring the Python port to the binary's
actual outputs.

## Schema

Each JSON file contains:

```json
{
  "name": "wire_100x10_m3",
  "build_command": "W NAME=W1:LEN=100:WID=10:METAL=m3:XORG=0:YORG=0",
  "shape_name": "W1",
  "tech": "BiCMOS",
  "geom": {
    "name": "W1",
    "kind": "Wire",
    "length_um": 100.0,
    "width_um": 10.0,
    "metal": "M3",
    "total_length_um": 100.0,
    "total_area_um2": 1000.0,
    "location": [0.0, 0.0],
    "n_segments": 1,
    "spiral_l1_um": null,
    "spiral_l2_um": null,
    "spiral_spacing_um": null,
    "spiral_turns": null
  },
  "captured_with": "qemu-i386-static + asitic.linux.2.2 + xvfb-run",
  "schema_version": 1
}
```

The ``geom`` block is the parsed output of ``Geom <name>``, with
``None`` for fields that don't apply to the kind (e.g. spiral
params for a wire).
