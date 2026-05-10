# ASITIC Geometry Routine Notes

These notes track the decompiled geometry builders in
`decomp/output/asitic_repl.c` and the corresponding clean-room
implementation in `src/reasitic/geometry.py`.

## Per-Case Status Summary

| Kind | C function | Status | Golden cases verified |
|---|---|---|---|
| `Wire` | `cmd_wire_build_geometry @ 08057998` | done | wire_100x10_m3, wire_150x8_m2, wire_75x5_msub |
| `Capacitor` | `cmd_capacitor_build_geometry @ 0805bc3c` | done | cap_80x80_m3_m2, cap_120x60_m3_m2_offset |
| `Square spiral` | `cmd_square_build_geometry @ 08056670` | done | 5 sq_*_m3 cases incl. exit-routing |
| `Polygon spiral` | `cmd_spiral_build_geometry @ 08057248` | done | 3 sp_*_m{2,3} cases |
| `Ring` | `cmd_ring_build_geometry @ 0805b450` | done | ring_r80_w10_g4_m3, ring_r120_w8_g6_m2 |
| `MMSquare` | `cmd_mmsquare_build_geometry @ 0805af5c` | broken | 0/2 |
| `Symmetric square` | `cmd_symsq_build_geometry @ 08059854` | broken | 0/3 |
| `Symmetric polygon` | `cmd_sympoly_build_geometry @ 0805a45c` | broken | 0/2 |
| `Transformer` | `cmd_trans_build_geometry @ 080576d4` | broken | 0/2 |
| `Balun` (3D Transformer) | `cmd_3dtrans_build_geometry @ 08057d40` | broken | 0/2 |
| `Via` | `cmd_via_build_geometry @ 08057b78` | covered indirectly | (no standalone golden) |

## Common Record Model

ASITIC stores layout geometry as a linked list of 240-byte polygon
records.  The builders call `display_list_append` to copy one record
per filled trace segment.  Each record has six (x, y) pairs at:

| offset | role (typical for spiral side trapezoid) |
|---|---|
| `+0x00 / +0x08` | centerline at start angle |
| `+0x18 / +0x20` | centerline at end angle |
| `+0x44 / +0x4c` | outer corner at start angle |
| `+0x5c / +0x64` | outer corner at end angle |
| `+0x88 / +0x90` | inner corner at start angle |
| `+0xa0 / +0xa8` | inner corner at end angle |

`shape_translate_inplace_xy` (decomp `0x0805b8c0`) adds `(dx, dy)`
to all six pairs (verified by reading the function's body — it walks
`*pdVar1`, `pdVar1[3]`, `+0x44`, `+0x5c`, `pdVar1[0x11]`,
`pdVar1[0x14]` for x and the `+8` siblings for y).

CIF export emits four vertices per polygon record. From the
positions in golden CIFs and the per-side decode in
`cmd_spiral_build_geometry`, the four output corners are:

1. `+0x44 / +0x4c` — outer at start
2. `+0x5c / +0x64` — outer at end
3. `+0xa0 / +0xa8` — inner at end
4. `+0x88 / +0x90` — inner at start

(The two `+0x00`/`+0x18` centerline pairs are used internally for
joining adjacent sides; they don't appear in CIF output.)

`cmd_flip_apply` does not mirror geometry; it reverses the linked-list
order. `cmd_fliph_apply` and `cmd_flipv_apply` mirror the geometry
about the bbox centerline (horizontal / vertical, respectively).

## `cmd_square_build_geometry` (`0x08056670`)

Builds square spiral metal as ASITIC display polygons, not as nested
closed loops.  For each side it emits one quadrilateral ribbon segment:
top, right, bottom, left.  The pitch is `W + S`.  Integer turns emit four
sides per turn; fractional turns emit `round(4 * frac(N))` extra sides.

The last emitted side is trimmed by one trace width along its terminal
direction before access routing is added.  If the shape has an exit
metal, or ASITIC supplies the default one-layer-down exit, the routine
adds:

- an overlap pad on the exit metal,
- an overlap pad on the spiral metal,
- an `n x n` via array sized from via width/spacing/overplot,
- an exit-metal lead in the terminal direction.

The reASITIC `layout_polygons(..., tech)` path ports this display
polygon logic directly.  The centerline `Shape.segments()` path is kept
for analysis.

## `cmd_spiral_build_geometry` (`0x08057248`)

Builds arbitrary-sided polygon spirals.  For each side, the outer radius
starts at `R` and the inner radius is `R - W / cos(pi / sides)`.  The
outer radius decreases by `(W + S) / cos(pi / sides) / sides` per side.

After all side polygons are emitted, ASITIC shifts the raw polygon set by
half of its bounding-box width and height plus the user origin.  This is
why the CIF lower-left does not land exactly at `XORG,YORG` for octagonal
spirals.

## `cmd_capacitor_build_geometry` (`0x0805bc3c`)

Creates two filled rectangles on the top and bottom metals.  `XORG,YORG`
are the lower-left plate corner.  reASITIC now follows that convention;
older code treated the origin as the plate center.

## `cmd_ring_build_geometry` (`0x0805b450`)

Builds a gapped annular polygon by sweeping `sides - 1` segments around
`2*pi - gap`.  The package layout path now emits the same filled segment
polygons for `ring(..., gap=...)`; the analysis shape remains a
centerline approximation.

## `cmd_mmsquare_build_geometry` (`0x0805af5c`)

Multi-metal series square inductor. Builds one square spiral per
metal layer between `METAL` (top) and `EXIT` (bottom), each layer
flipped or rotated so consecutive layers couple via vias rather
than overlap. The C does:

```c
iVar7 = shape.metal - shape.exit_metal;        // # of layers - 1
// First spiral on shape.metal (no exit metal — pure square spiral)
*(shape + 0x6c) = -1;                           // suppress exit
cmd_square_build_geometry(shape, 3);
// Restore exit_metal so cmd_square sees it for subsequent calls
shape.exit_metal = shape.metal - iVar7;
// Repeat for each lower metal layer
for (i = 1; i <= iVar7; i++) {
    name = sprintf("%s-%d", shape.name, i);
    new_metal = shape.metal - i;
    cmd_copy_clone(prev_shape, name, ..., new_metal);
    if (turns is integer or half-integer) cmd_fliph_apply(g_current_shape);
    else                                  cmd_flipv_apply(g_current_shape);
    if (turns is half-integer) alternate flip direction each iteration;
    cmd_flip_apply(g_current_shape);            // reverse linked-list order
}
// Join all spirals serially
for (i = 1; i <= iVar7; i++) cmd_join_apply(prev[0], prev[i]);
```

The flip selection at the C `cmd_mmsquare_build_geometry @ 0805af5c`
prologue:

```c
double frac = turns - round(turns);
if (frac == 0.5 || frac == 0.0) flip = cmd_fliph_apply;
else                            flip = cmd_flipv_apply;
```

For `turns = 3` (integer) the flip is `fliph`; for `turns = 2.5`
(half-integer) the flip is also `fliph` but it alternates per
layer between fliph and flipv. The CIF goldens for
`mmsq_160x10x2x3_m3_to_m2` (turns=3, 2 metals) show M3 with the
trace running clockwise from top-left and M2 with the trace
running counter-clockwise from bottom-left — i.e. M3 fliph'd
once gives M2.

**Python status (broken):** `multi_metal_square` builds two
independent `square_spiral`s at the same `(x_origin, y_origin)`
and concatenates polygons without flipping. Result: M3 and M2
polygons overlap exactly instead of forming the staircased
interconnect the C produces. Needs a per-layer flip applied to
each subsequent square spiral.

## `cmd_trans_build_geometry` (`0x080576d4`)

Planar transformer: two interleaved square spirals at the same
metal (`METAL`) but laterally offset and counter-wound.

```c
cmd_square_build_geometry(primary, 3);
cmd_square_build_geometry(secondary, 3);
cmd_flipv_apply(g_current_shape);    // flip secondary vertically
cmd_fliph_apply(g_current_shape);    // and horizontally
// Then translate secondary so it interleaves the primary at half
// the bbox-difference along x and y (lines 3879-3897).
double dx = (primary.bbox.xmax - secondary.first_outer.x) * 0.5;
double dy = (primary.bbox.ymax - primary.first_outer.y) * 0.5;
secondary[0].outer.x += dx;  // shift first segment outer
secondary[0].center.x += dx;
secondary[0].inner.x += dx;
secondary[last].outer.x -= dx;  // shift last segment outer
secondary[last].center.x -= dx;
secondary[last].inner.x -= dx;
secondary[last].outer.y += (...) + dy;  // adjust last endpoint
// Apply additional shift if turns has 0.25/0.75/0.5 fraction (lines 3902-3924)
shape.linked_list[0xb4] = secondary;     // link primary to secondary
secondary.linked_list[0xb4] = primary;
```

The TRANS thus produces TWO shapes (primary + secondary) linked
into the same display list, each addressable by name. ASITIC's
`CIFSAVE TP file.cif` saves only the primary's polygons. Our
golden cases include both `_primary.cif` and `_secondary.cif`.

**Python status (broken):** `transformer()` produces a single
shape combining both coils — but each coil's geometry uses the
basic `square_spiral` without the exit-metal access routing or
the secondary translation/flip. The signature also doesn't
accept the kwargs the test harness expects (`primary_length`,
`primary_width`, etc.).

## `cmd_3dtrans_build_geometry` (`0x08057d40`)

3D balun / transformer: two square spirals on different metal
layers, with vertical (z-direction) coupling via metal stack.
The 5329-byte function is the largest builder. It:

1. Builds primary on `METAL` (top).
2. Builds secondary on `EXIT` (bottom).
3. Inserts via clusters at the corners where the primary's
   inner trace ends and the secondary's outer trace starts.
4. Adds connecting traces between the two coils.

The detailed structure needs more reverse-engineering. The
golden cases are `balun_200x8x3x3_m3_m2_primary` and
`balun_200x8x3x3_m3_m2_secondary` — same as TRANS in spirit but
with the two coils stacked rather than side-by-side.

**Python status (broken):** `balun()` and `transformer_3d()` use
the same simple-stack approach as `multi_metal_square`. Doesn't
match the C output. Signatures don't accept `primary_metal` /
`secondary_metal` kwargs.

## `cmd_symsq_build_geometry` (`0x08059854`)

Symmetric centre-tapped square inductor. The 2679-byte function
takes an `ILEN` parameter (centre-tap spacing) in addition to the
standard `LEN`/`W`/`S`/`N`/`METAL`/`EXIT` set. It builds two arms
that meet at the centre with a bridge segment crossing on the
exit metal.

Algorithm (high level):

1. Build the right arm: walk `N` turns of square spiral but stop
   each side at the centre line, with a centre-tap stub of length
   `ILEN/2`.
2. Build the left arm as the mirror of the right (cmd_fliph_apply).
3. Cross-connect at the centre via a bridge on `EXIT` metal.

**Python status (broken):** `symmetric_square` builds two
half-length square spirals at offset positions, missing the
centre-tap bridge and the ILEN parameter. Signature doesn't
accept `ilen` or `primary_metal`/`exit_metal`.

## `cmd_sympoly_build_geometry` (`0x0805a45c`)

Symmetric polygon spiral — the polygon equivalent of `cmd_symsq`,
1914 bytes. Builds two polygon-spiral arms that meet at the
centre with the same ILEN-based centre-tap bridge.

**Python status (broken):** `symmetric_polygon` builds two
half-radius polygon spirals at offset positions. Signature
doesn't accept `ilen`. Same gaps as `symmetric_square`.

## Remaining Work

The five "broken" builders (MMSQ, TRANS, 3DTRANS/BALUN, SYMSQ,
SYMPOLY) all need:

1. Updated Python signatures to accept the same kwargs the C
   commands consume (e.g. `ILEN` for the symmetric variants,
   `EXIT` metal for all).
2. Per-layer or per-arm trapezoid emission — currently they
   merge raw centerline polygons without breaking each spiral
   side into its own trapezoid.
3. The flip / rotate / link operations the C performs on the
   secondary coil or on each subsequent metal layer.
4. The centre-tap bridge for the symmetric variants.
5. Access-routing helpers integrated where appropriate.

The first natural test gate is the
`tests/test_layout_polygons_against_cif.py` harness. As each
builder is fixed, add the corresponding golden CIF case there
to lock in fidelity.

The simpler ports first:

- **TRANS** has a clear two-spiral structure with documented
  flips and translation.
- **MMSQ** wraps `cmd_square_build_geometry` plus per-layer
  flips and joins.

Both are reasonable starting points.
