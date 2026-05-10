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
| `MMSquare` | `cmd_mmsquare_build_geometry @ 0805af5c` | done | 2/2 |
| `Symmetric square` | `cmd_symsq_build_geometry @ 08059854` | done | 3/3 (266 polys all match) |
| `Symmetric polygon` | `cmd_sympoly_build_geometry @ 0805a45c` | not started | 0/2 |
| `Transformer` | `cmd_trans_build_geometry @ 080576d4` | done (primary full; secondary M3+M2 full, VIA3 ~3µm off) | 2/2 |
| `Balun` (3D Transformer) | `cmd_balun_build_geometry @ 0805bc74` | done | 2/2 (46 polys all match) |
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

**Python status (DONE — 2/2 cases vertex-for-vertex match):**
- `multi_metal_square` accepts both `metals=[...]` and the
  C-style `metal=...:exit_metal=...` arg pair.
- `_mmsquare_layout_polygons` builds the top-metal spiral with
  `trim_final=False` (no exit-via clearance trim, since MMSQ
  forces `exit_metal=-1` on the inner spiral), then for each
  lower metal layer applies `_polygon_fliph_apply` (Y-mirror
  about bbox center) + linked-list reversal + `_polygons_relayer`.
- `_square_layout_polygons` grew a `trim_final` parameter; with
  `trim_final=False` the chamfer that would accommodate the
  next perpendicular side is removed for all four side
  directions (the inner-most segment terminates straight, no
  chamfer).

The integer-turn case uses `cmd_fliph_apply`. Half-integer
turns alternate between fliph and flipv per layer, but the
single half-integer test case (`mmsq_200x12x3x2p5_m3_to_m2_offset`)
has only two metals, so we only flip once and the alternation
isn't exercised. Add cases with more metals if needed.

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

**Python status (mostly done — M2 + VIA3 match perfectly,
M3 12/13).** `transformer()` accepts the C-style
`metal=` + `exit_metal=` plus a `which="primary"|"secondary"`
selector to materialise one coil at a time. Internal layout
decoded from the gold:

- primary internal LL = `(XORG + W + S, YORG + 2W + S)` (= (11, 19))
- secondary internal LL = `(XORG, YORG + W)` (= (0, 8))
- coil spacing = `W + 2S` so inter-turn pitch is `2*(W+S)`,
  leaving room for the other coil's interleaved turns.

Secondary is built by laying out the basic spiral (with M2
exit routing) at its own internal origin, then applying
`_polygon_fliph_apply` + `_polygon_flipv_apply` with
spiral-bbox-derived axes (NOT post-access-routing-bbox axes,
since the M2 lead extension would shift the mirror axis).

**Outstanding:** the entry-lead extension. The C extends the
outermost top-side leftward back to `x = 0` (chip edge); the
Python entry lead stops at the spiral's lower-left x. One
polygon difference per coil (12/13 M3 match). The lead
extension lives somewhere in the C `cmd_square_build_geometry`
inside the EXIT-routing branch but I didn't decode the exact
"how much" formula — likely `extend_terminal_segment` or
similar.

Also fixed the via-array sizing bug in
`_square_access_polygons` while doing this:
`n = floor((W − 2·op + via_s) / (via_w + via_s))` matches the
C convention (was using `round`, which over-counted vias for
W=10 and W=8 in different ways).

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
standard `LEN`/`W`/`S`/`N`/`METAL`/`EXIT` set.

### Decoded structure (per-piece)

The full SYMSQ output for the smallest golden case
(`symsq_150x8x2x2_m3_m2`: L=150, W=8, S=2, N=2, ILEN=15,
XORG=100, YORG=100) breaks down into:

* **Centre-U** (3 M3 polygons forming an inverted "Π") — done.
  See `_symsq_centre_arm_polygons` in `geometry.py`. Verified
  vertex-for-vertex against all three golden cases.
* **Two via clusters with M3+M2 overlap pads.** Pad sizes
  ``(W × ILEN/2)`` at:
    - Pad 1 (right-arm-base): at `(XORG + L − W/2 − ?, U_arm_bot + ?)`
    - Pad 2 (lower-spiral-attachment): different position
  Exact placement formulas need decoding from the C
  `lookup_via_for_metal_pair` calls inside the SYMSQ state
  machine.
* **M2 chamfered transition trace** — a single quadrilateral
  connecting pad 1 down-and-left to pad 2 region, with the
  characteristic 45° chamfer.
* **Main spiral (12 polygons across 6 sub-pieces):**

  | Sub-piece | Polys | Decoded location (case 1) |
  |---|---|---|
  | Inner mini-loop bottom-U | 3 | y=117.5–175, x=110–240 |
  | ILEN-stub on left | 2 | x=110–118, y=175–190 (split into 2 of W height each) |
  | Upper inner ring | 3 | y=190–247.5, x=110–240 |
  | Slanted right-side transition | 1 | x=232–250, y=175–190 |
  | Outermost ring | 3 | y=107.5–175, x=100–250 |

### Decoded formulas

For the centre-U (verified on all 3 cases):

  ```
  U_outer_top_y   = YORG + L + ILEN/2
  U_arm_bottom_y  = YORG + L/2 + ILEN
  U_outer_x       = [XORG, XORG + L]
  U_inner_x       = [XORG + W, XORG + L − W]
  U_height        = (L − ILEN) / 2
  ```

For the bbox of the whole SYMSQ:

  ```
  total_bbox_x = [XORG, XORG + L]
  total_bbox_y = [YORG + ILEN/2, YORG + L + ILEN/2]
  ```

So the whole SYMSQ fits in an L × L bounding box, shifted up by
`ILEN/2` from `YORG`.

For the inner mini-loop (1 of the 3 sub-pieces of the main
spiral, case 1):

  ```
  inner_loop_top_y    = YORG + L/2          (= 175)
  inner_loop_bottom_y = YORG + ILEN/2 + pitch  (= 117.5)
  inner_loop_x        = [XORG + pitch, XORG + L − pitch]
  ```

(pitch = W + S; verified against case 1 only — needs cross-check
against cases 2 and 3.)

### Algorithm (high level, decoded from C)

The C builds the geometry via a state machine in
``cmd_symsq_build_geometry`` (lines 4970-5089) with cases 0-7
dispatching to two helpers:

* `shape_aux_init @ 0x0805bb64` (211 bytes) — emits a single
  side trapezoid by collapsing-and-extending an initial
  degenerate polygon. Args: `(side_idx, polygon_record, length, width)`.
* `symsq_emit_polygon_layers @ 0x080595d0` (lines 4677-4853) —
  emits 4 polygons in one call (the 4-side cross-tap segment
  cluster).

The state machine progresses as:

* Cases 0-3 (corner sides): single `shape_aux_init` call per side.
* Case 5 (bottom-half cross-tap): two `lookup_via_for_metal_pair`
  calls + one `symsq_emit_polygon_layers` call (4 polys).
* Case 6 (top-half cross-tap): same as 5 but mirrored.

The state machine cycles uVar11 through 0→3→5→0→1→3 etc.,
emitting one to four polygons per iteration. After N turns the
loop exits and tail-emits 2 more polygons (the centre-tap stub
on M2/EXIT).

### `cmd_balun_build_geometry` (`0x0805bc74`, 72 bytes!)

Wraps SYMSQ:

```c
cmd_symsq_build_geometry(shape);           // primary
cmd_symsq_build_geometry(args_buf);        // secondary
cmd_flipv_apply(g_current_shape);          // flip secondary x
cmd_showldiv_format(g_current_shape);
shape.linked_list[0xb4] = secondary;       // sibling pointers
secondary.linked_list[0xb4] = shape;
```

**BALUN ILEN derivation.** BALUN's CLI doesn't take an explicit
ILEN parameter — it's derived from the build args. Decoded from
gold `balun_200x8x3x3` (L=200, W=8, S=3, N=3): the apparent ILEN
inside the BALUN-internal SYMSQs is **22 = 2·pitch = 2·(W+S)**.
This makes the centre gap large enough for the second SYMSQ to
fit between (or over/under).

**BALUN primary vs full SYMSQ.** The primary BALUN coil has 15
M3 polys (vs 26 for a full SYMSQ at N=3). It looks like each
BALUN coil is a *partial* SYMSQ — only the OUTERMOST and the
INNERMOST rings are emitted, plus the centre-U. The middle-
nested rings (k=1..N-2) appear only on the partner coil.

Confirming the partial-SYMSQ structure and decoding which rings
go with which coil is the next BALUN porting step.

**Python status: N=2 done, N≥3 partial.** All 38 polygons
of `symsq_150x8x2x2_m3_m2` (the smallest case, N=2) match the
gold vertex-for-vertex. Implementation:

- `_symsq_u_ring_polygons(open_side='top'|'bottom')` —
  generic chamfered "U" ring used for centre-U, outer ring,
  inner mini-loop, and upper inner ring.
- `_symsq_layout_polygons` — assembles everything for N=2.

Verified per layer for case 1:

| Layer | Gold | Py | Match |
|---|---|---|---|
| M3 | 17 | 17 | ✓ |
| M2 | 3 | 3 | ✓ |
| VIA3 | 18 | 18 | ✓ |

### Generalising to N ≥ 3

For N=3 (cases `symsq_200x10x3x3` and `symsq_300x12x4x3`), the
M3 piece count grows because additional nested rings appear at
both top and bottom. Decoded the per-ring formulas (verified
against case 2 vertical sides):

* Top ring k (k = 0..N−1):
  ```
  outer_top_y   = YORG + L + ILEN/2 − k·pitch
  arm_bottom_y  = YORG + L/2 + ILEN
  outer_x_min   = XORG + k·pitch
  outer_x_max   = XORG + L − k·pitch
  ```
  k=0 is the centre-U (full-L wide); k=1..N-1 are nested
  inner rings opening at bottom.

* Bottom ring k (k = 0..N−1):
  ```
  outer_top_y   = YORG + L/2          (the arm-top side)
  arm_bottom_y  = YORG + ILEN/2 + k·pitch
  outer_x_min   = XORG + k·pitch
  outer_x_max   = XORG + L − k·pitch
  ```
  k=0 is the outermost ring; k=1..N-1 are nested mini-loops
  opening at top.

* Stubs: each turn, the C state machine alternates which side
  gets a 2-poly stub (ILEN/2 each). For N=2 it's on the left
  at offset `X+pitch`. For N=3 it's on the right at offset
  `X+L-pitch-W` (verified from case 2: y=200-210, y=210-220).
  Pattern needs more cases to nail.

* Slant transitions and via-cluster positions need similar
  generalization. The C state machine (cases 0-7 in
  cmd_symsq_build_geometry) emits exactly the right pieces in
  exactly the right order; a direct port would handle all N
  uniformly. Current pragmatic path: extend
  `_symsq_layout_polygons` to loop over k = 0..N-1 for the
  top/bottom rings + emit per-ring stubs/slants based on a
  small alternation table.

## `cmd_sympoly_build_geometry` (`0x0805a45c`)

Symmetric polygon spiral — the polygon equivalent of `cmd_symsq`,
1914 bytes. Builds two polygon-spiral arms that meet at the
centre with the same ILEN-based centre-tap bridge.

**Python status (NOT STARTED).** SYMPOLY's structure is the
N-gon analog of SYMSQ — instead of square U-rings, each ring
is a partial N-gon (sides/2 + 1 segments per half). The
overall topology still has:

* a centre-tap "bridge" structure at the top (analog of SYMSQ's
  centre-U but using polygon-spiral chamfer geometry)
* nested polygon rings (each a partial N-gon opening at top
  for bottom-half rings, opening at bottom for top-half rings)
* stubs/slants connecting adjacent rings across the centre
* via clusters + M2 chamfered trace (same as SYMSQ)

A faithful port should follow the SYMSQ pattern but use the
polygon-spiral side computation (cos/sin angles per side) for
each ring. The ILEN parameter is explicit in SYMPOLY's CLI
(unlike BALUN which derives it).

Suggested approach for next session:

1. Extract a generic `_polygon_partial_ring(centre, R_outer, R_inner, sides, start_angle, end_angle)` helper.
2. Compose centre-tap + ring-N + ring-N-1 + ... like SYMSQ.
3. Validate against `sympoly_r100_8sides_3turns` (smaller case)
   and `sympoly_r120_8sides_2turns`.

## Resume here (2026-05-09 round 2)

**Status snapshot.** 7/10 builders done or substantially-done.

| Builder | M2 | M3 | VIA3 |
|---|---|---|---|
| Wire ✓ | n/a | exact | n/a |
| Capacitor ✓ | exact | exact | n/a |
| Square ✓ | exact | exact | exact |
| Polygon spiral ✓ | n/a | exact | n/a |
| Ring ✓ | n/a | exact | n/a |
| MMSQ ✓ | exact | exact | n/a |
| TRANS (mostly) | exact | 12/13 | exact |
| SYMSQ | not started | | |
| SYMPOLY | not started | | |
| BALUN/3DTRANS | not started | | |

**TRANS entry-lead gap RESOLVED.** Decoded in commit *(this
session)*: `dVar2` in `cmd_trans_build_geometry @ :3879-3893`
evaluates to **`pitch = W + S`** (not `W+S/2`), because
`cmd_trans_create_new` at `:11171` pre-modifies
`primary.S = 2*S + W` so `(W + S')/2 = pitch`. The C then:

* shifts `primary.first_polygon`'s start corners by `-pitch`
  (extending the outermost top-side leftward to `x=0`)
* shifts `secondary.first_polygon`'s start corners by `+pitch`
  (post-flip, this extends the secondary's outermost top-side
  rightward to `x = XORG + L + pitch`)

Implemented as `_trans_extend_primary_lead` and
`_trans_extend_secondary_lead` in `geometry.py`. TRANS primary
now full M3+M2+VIA3 match; secondary M3+M2 full match.

**TRANS secondary VIA3 still off by ~3 µm.** Cluster center
is at `(152, 86)` in py vs `(155, 89)` in gold — diff of
exactly `S = 3` in both x and y. Likely the secondary's last
polygon (post-flip) presents its terminal corner at a
different position than the via-cluster placer assumes. Needs
investigation into how the C trans handles the
secondary-specific via cluster center.

**Useful primitives now available**:

- `_polygon_fliph_apply(polys, y_axis=...)` — Y-mirror with
  optional explicit axis (not bbox-derived).
- `_polygon_flipv_apply(polys, x_axis=...)` — X-mirror with
  optional explicit axis.
- `_polygons_relayer(polys, tech, metal_idx)` — re-emit on a
  different metal layer.
- `_polygon_bbox(polys)` — `(xmin, xmax, ymin, ymax)`.
- `_square_layout_polygons(..., trim_final=False)` — square
  spiral without the exit-via clearance trim.
- `_square_access_polygons` via-array sizing now uses `floor`
  to match the C convention.

**Suggested next unit.** SYMSQ is structurally most similar
to a "two square arms + centre-tap bridge". The C function is
2679 bytes, with `cmd_symsq_emit_helper @ 0x080595d0` doing
the per-turn polygon emission. The golden CIFs show:

- A 3-poly M3 "centre arm" (the bridge)
- Two via clusters (one per arm endpoint that lands on M2)
- A 12-poly M3 main spiral structure
- An M2 connecting trace

`symsq_150x8x2x2_m3_m2.cif` is the smallest case (53 lines —
half the size of `symsq_200x10x3x3` and `symsq_300x12x4x3`)
and a good starting point.

For the entry-lead extension fix on TRANS, search the C for
`shape_extend_first_segment_unit` and any related extension
helpers; the standalone-square call at `cmd_square_build_geometry`
calls it conditionally on `color_idx == 0 || color_idx == 2`,
but TRANS uses color_idx=3. Maybe TRANS does its own extension
via a different code path I haven't found yet.

## Remaining Work

The four "broken" builders (TRANS, 3DTRANS/BALUN, SYMSQ,
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
