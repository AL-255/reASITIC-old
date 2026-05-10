"""Verify the REPL bridge output matches the ASITIC binary's CIF goldens.

For every layout file under ``tests/data/validation/layouts/<stem>.cif``,
this test:

1. Parses the CIF into the set of (layer, 4-corner-polygon) records the
   binary emitted.
2. Drives the REPL bridge (``docs/repl/bridge.py``) with the parameters
   that produced the golden, and pulls back the rendered payload.
3. Compares each metal-trace polygon corner-for-corner (after sorting
   vertices to absorb winding-order differences).

A passing test means the REPL viewer is producing the **exact same
geometry** the C binary produced for that case — the user requirement
that drove this harness in the first place.

Cases currently covered: ``wire_100x10_m3``. New CIF goldens dropped
under ``tests/data/validation/layouts/`` extend coverage automatically
once their parameters are added to ``CASES`` below.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

import pytest

REPO = Path(__file__).resolve().parent.parent
LAYOUTS = REPO / "tests" / "data" / "validation" / "layouts"
TECH = REPO / "tests" / "data" / "BiCMOS.tek"
BRIDGE_DIR = REPO / "docs" / "repl"

if str(BRIDGE_DIR) not in sys.path:
    sys.path.insert(0, str(BRIDGE_DIR))


# (cif_stem, build_spec, layer_filter)
#
# Each entry maps a CIF golden file (under ``tests/data/validation/layouts/``)
# to the bridge ``build_shape`` parameters that should reproduce it. The
# layer filter is the CIF layer on which the metal trace lives.
CASES: list[tuple[str, dict, str]] = [
    # Single-segment wires (1 polygon; trivial chamfer-free case).
    (
        "wire_100x10_m3",
        {"kind": "wire", "name": "W1", "metal": "m3",
         "length": 100.0, "width": 10.0, "x_origin": 0.0, "y_origin": 0.0},
        "M3",
    ),
    (
        "wire_150x8_m2",
        {"kind": "wire", "name": "W2", "metal": "m2",
         "length": 150.0, "width": 8.0, "x_origin": 50.0, "y_origin": 50.0},
        "M2",
    ),
    (
        "wire_75x5_msub",
        {"kind": "wire", "name": "WSUB", "metal": "msub",
         "length": 75.0, "width": 5.0, "x_origin": 100.0, "y_origin": 200.0},
        "MSUB",
    ),
    # Square spirals (multi-side connected polylines with chamfered joints).
    (
        "sq_170x10x3x2_m3",
        {"kind": "square_spiral", "name": "A", "metal": "m3",
         "exit_metal": "m2",
         "length": 170.0, "width": 10.0, "spacing": 3.0, "turns": 2.0,
         "x_origin": 200.0, "y_origin": 200.0},
        "M3",
    ),
    (
        "sq_200x10x2x3_m3",
        {"kind": "square_spiral", "name": "B", "metal": "m3",
         "length": 200.0, "width": 10.0, "spacing": 2.0, "turns": 3.0,
         "x_origin": 200.0, "y_origin": 200.0},
        "M3",
    ),
    (
        "sq_120x10x2x1p5_m3_offset",
        {"kind": "square_spiral", "name": "S15", "metal": "m3",
         "length": 120.0, "width": 10.0, "spacing": 2.0, "turns": 1.5,
         "x_origin": 50.0, "y_origin": 75.0},
        "M3",
    ),
    (
        "sq_260x10x4x2p25_m3_exit_m2",
        {"kind": "square_spiral", "name": "SEXIT", "metal": "m3",
         "exit_metal": "m2",
         "length": 260.0, "width": 10.0, "spacing": 4.0, "turns": 2.25,
         "x_origin": 100.0, "y_origin": 120.0},
        "M3",
    ),
    (
        "sq_300x12x3x4_m3_quarter_turn",
        {"kind": "square_spiral", "name": "SQT", "metal": "m3",
         "exit_metal": "m2",
         "length": 300.0, "width": 12.0, "spacing": 3.0, "turns": 4.25,
         "x_origin": 0.0, "y_origin": 0.0},
        "M3",
    ),
    # Access-routing layer checks: every spiral with EXIT (or default
    # exit) should drop a via cluster + an M2 lead trace + an M2 pad.
    # We re-run the same spec but filter for the EXIT layer and the
    # via layer so the harness covers the full output of the binary.
    #
    # Lead-length is approximated as ``2 · pitch · N`` which matches
    # most captured cases to within a few microns; the C reference
    # uses a length that depends on a build-time stack value we have
    # not fully decoded. Visual fidelity is correct (right direction,
    # width, position); only the head-y differs by single digits, so
    # the M2-layer case is marked xfail.
    # M2 exit-lead and VIA3 cluster checks for every square spiral.
    *(
        (
            stem,
            {"kind": "square_spiral", "name": name, "metal": "m3",
             "exit_metal": "m2",
             "length": L, "width": W, "spacing": S, "turns": N,
             "x_origin": x0, "y_origin": y0},
            layer,
        )
        for stem, name, L, W, S, N, x0, y0 in [
            ("sq_170x10x3x2_m3", "A", 170.0, 10.0, 3.0, 2.0, 200.0, 200.0),
            ("sq_200x10x2x3_m3", "B", 200.0, 10.0, 2.0, 3.0, 200.0, 200.0),
            ("sq_120x10x2x1p5_m3_offset", "S15", 120.0, 10.0, 2.0, 1.5, 50.0, 75.0),
            ("sq_260x10x4x2p25_m3_exit_m2", "SEXIT", 260.0, 10.0, 4.0, 2.25, 100.0, 120.0),
            ("sq_300x12x3x4_m3_quarter_turn", "SQT", 300.0, 12.0, 3.0, 4.25, 0.0, 0.0),
        ]
        for layer in ("M2", "VIA3")
    ),
    # Capacitor: two metal-layer plates of equal size, filled rectangle.
    *(
        (stem, spec, layer)
        for stem, spec in [
            ("cap_80x80_m3_m2",
             {"kind": "capacitor", "name": "C1",
              "metal": "m3", "metal_bottom": "m2",
              "length": 80.0, "width": 80.0,
              "x_origin": 0.0, "y_origin": 0.0}),
            ("cap_120x60_m3_m2_offset",
             {"kind": "capacitor", "name": "C2",
              "metal": "m3", "metal_bottom": "m2",
              "length": 120.0, "width": 60.0,
              "x_origin": 50.0, "y_origin": 50.0}),
        ]
        for layer in ("M3", "M2")
    ),
    # Ring (RING command): single closed annular polygon with a gap.
    (
        "ring_r80_w10_g4_m3",
        {"kind": "ring", "name": "RG1", "metal": "m3",
         "radius": 80.0, "width": 10.0, "gap": 4.0, "sides": 16,
         "x_origin": 0.0, "y_origin": 0.0},
        "M3",
    ),
    (
        "ring_r120_w8_g6_m2",
        {"kind": "ring", "name": "RG2", "metal": "m2",
         "radius": 120.0, "width": 8.0, "gap": 6.0, "sides": 16,
         "x_origin": 100.0, "y_origin": 100.0},
        "M2",
    ),
    # NOTE: polygon_spiral / mmsq / symsq / sympoly / trans / balun
    # are now back in the REPL with full CIF parity. The bridge uses
    # ``layout_polygons`` for these kinds, so the polygons match the
    # C-binary's CIF goldens vertex-for-vertex.
    # SYMSQ — full M3+M2+VIA3 parity for all 3 goldens.
    *(
        (
            stem,
            {"kind": "symmetric_square", "name": name, "metal": "m3",
             "exit_metal": "m2",
             "length": L, "width": W, "spacing": S, "turns": N,
             "ilen": IL,
             "x_origin": x0, "y_origin": y0},
            layer,
        )
        for stem, name, L, W, S, N, IL, x0, y0 in [
            ("symsq_150x8x2x2_m3_m2", "Y3", 150, 8, 2, 2, 15, 100, 100),
            ("symsq_200x10x3x3_m3_m2", "Y1", 200, 10, 3, 3, 20, 100, 100),
            ("symsq_300x12x4x3_m3_m2_offset", "Y2", 300, 12, 4, 3, 30, 100, 100),
        ]
        for layer in ("M3", "M2", "VIA3")
    ),
    # SYMPOLY — full M3+M2+VIA3 parity for both goldens.
    *(
        (
            stem,
            {"kind": "symmetric_polygon", "name": name, "metal": "m3",
             "exit_metal": "m2",
             "radius": R, "width": W, "spacing": S, "turns": N,
             "ilen": IL, "sides": sides,
             "x_origin": 200, "y_origin": 200},
            layer,
        )
        for stem, name, R, W, S, N, IL, sides in [
            ("sympoly_r120_8sides_2turns", "YP2", 120, 10, 3, 2, 20, 8),
            ("sympoly_r100_8sides_3turns", "YP1", 100, 10, 3, 3, 20, 8),
        ]
        for layer in ("M3", "M2", "VIA3")
    ),
    # MMSQ — full M3+M2 parity for both goldens.
    *(
        (
            stem,
            {"kind": "multi_metal_square", "name": name, "metal": "m3",
             "exit_metal": "m2",
             "length": L, "width": W, "spacing": S, "turns": N,
             "x_origin": x0, "y_origin": y0},
            layer,
        )
        for stem, name, L, W, S, N, x0, y0 in [
            ("mmsq_160x10x2x3_m3_to_m2", "MM1", 160, 10, 2, 3, 0, 0),
            ("mmsq_200x12x3x2p5_m3_to_m2_offset", "MM2", 200, 12, 3, 2.5, 200, 200),
        ]
        for layer in ("M3", "M2")
    ),
    # TRANS — primary + secondary on M3+M2+VIA3.
    *(
        (
            stem,
            {"kind": kind, "name": name, "metal": "m3",
             "exit_metal": "m2",
             "length": 200, "width": 8, "spacing": 3, "turns": 3,
             "x_origin": 0, "y_origin": 0},
            layer,
        )
        for stem, kind, name in [
            ("trans_200x8x3x3_m3_m2_primary", "transformer_primary", "TX"),
            ("trans_200x8x3x3_m3_m2_secondary", "transformer_secondary", "TX"),
        ]
        for layer in ("M3", "M2", "VIA3")
    ),
    # BALUN — primary on M3+M2+VIA3, secondary on M3 only.
    (
        "balun_200x8x3x3_m3_m2_primary",
        {"kind": "balun_primary", "name": "BL", "metal": "m3",
         "secondary_metal": "m2", "exit_metal": "m2",
         "length": 200, "width": 8, "spacing": 3, "turns": 3,
         "x_origin": 0, "y_origin": 0},
        "M3",
    ),
    (
        "balun_200x8x3x3_m3_m2_primary",
        {"kind": "balun_primary", "name": "BL", "metal": "m3",
         "secondary_metal": "m2", "exit_metal": "m2",
         "length": 200, "width": 8, "spacing": 3, "turns": 3,
         "x_origin": 0, "y_origin": 0},
        "M2",
    ),
    (
        "balun_200x8x3x3_m3_m2_primary",
        {"kind": "balun_primary", "name": "BL", "metal": "m3",
         "secondary_metal": "m2", "exit_metal": "m2",
         "length": 200, "width": 8, "spacing": 3, "turns": 3,
         "x_origin": 0, "y_origin": 0},
        "VIA3",
    ),
    (
        "balun_200x8x3x3_m3_m2_secondary",
        {"kind": "balun_secondary", "name": "BL", "metal": "m3",
         "secondary_metal": "m2", "exit_metal": "m2",
         "length": 200, "width": 8, "spacing": 3, "turns": 3,
         "x_origin": 0, "y_origin": 0},
        "M3",
    ),
    # Polygon spiral — M3 only.
    *(
        (
            stem,
            {"kind": "polygon_spiral", "name": name, "metal": "m3",
             "radius": R, "width": W, "spacing": S, "turns": N,
             "sides": sides, "x_origin": 200, "y_origin": 200},
            layer,
        )
        for stem, name, R, W, S, N, sides in [
            ("sp_r100_8sides_3turns_m3", "P1", 100, 8, 3, 3, 8),
            ("sp_r80_8sides_2turns_m3", "P2", 80, 6, 2, 2, 8),
        ]
        for layer in ("M3",)
    ),
]


def _parse_cif(path: Path) -> list[tuple[str, list[tuple[float, float]]]]:
    """Return [(layer, [(x_um, y_um), ...])] for every ``P`` (polygon)
    and ``B`` (box) record in the CIF."""
    polys: list[tuple[str, list[tuple[float, float]]]] = []
    layer = ""
    for line in path.read_text().splitlines():
        line = line.strip()
        m = re.match(r"^L([A-Z0-9]+);", line)
        if m:
            layer = m.group(1)
            continue
        m = re.match(r"^P\s*((?:-?\d+\s+)+);", line)
        if m:
            ns = [int(t) for t in m.group(1).split()]
            pts = [
                (ns[i] / 100.0, ns[i + 1] / 100.0)
                for i in range(0, len(ns), 2)
            ]
            polys.append((layer, pts))
            continue
        # CIF ``B w h cx cy [rotation flags];`` — width × height box
        # centred at (cx, cy). ASITIC emits boxes for via overlap pads.
        m = re.match(r"^B\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", line)
        if m:
            w = int(m.group(1)) / 100.0
            h = int(m.group(2)) / 100.0
            cx = int(m.group(3)) / 100.0
            cy = int(m.group(4)) / 100.0
            half_w = w * 0.5
            half_h = h * 0.5
            polys.append((layer, [
                (cx - half_w, cy - half_h),
                (cx + half_w, cy - half_h),
                (cx + half_w, cy + half_h),
                (cx - half_w, cy + half_h),
            ]))
    return polys


def _normalize(corners) -> tuple[tuple[float, float], ...]:
    """Sort the 4 corners (rounded to 2 decimals = 0.01 μm = CIF's
    integer-cmu precision) so winding/start-vertex don't affect
    equality. ASITIC's FPU rounding can drift by a single cmu so the
    matching layer below (``_polys_match``) tolerates that band."""
    return tuple(sorted((round(x, 2), round(y, 2)) for x, y in corners))


def _polys_match(a, b, tol: float = 0.05) -> bool:
    """Two normalized 4-corner polygons match if every vertex of one
    has a partner in the other within ``tol`` μm. Generous enough to
    absorb the ±1 cmu FPU-precision drift between ASITIC's binary and
    Python's double-precision math."""
    if len(a) != len(b):
        return False
    used = [False] * len(b)
    for ax, ay in a:
        found = False
        for j, (bx, by) in enumerate(b):
            if used[j]:
                continue
            if abs(ax - bx) <= tol and abs(ay - by) <= tol:
                used[j] = True
                found = True
                break
        if not found:
            return False
    return True


def _diff_polys(py_set, cif_set, tol: float = 0.05):
    """Return (py_only, cif_only) lists after pairing within tolerance."""
    cif_unmatched = list(cif_set)
    py_only = []
    for p in py_set:
        for i, c in enumerate(cif_unmatched):
            if _polys_match(p, c, tol):
                cif_unmatched.pop(i)
                break
        else:
            py_only.append(p)
    return py_only, cif_unmatched


@pytest.mark.parametrize("stem,spec,layer_filter", CASES)
def test_repl_bridge_matches_cif(stem, spec, layer_filter):
    cif_path = LAYOUTS / f"{stem}.cif"
    if not cif_path.exists():
        pytest.skip(f"golden CIF not present: {cif_path.name}")

    import bridge  # imported lazily so collection works without the wheel

    bridge.STATE = {"tech": None, "shape": None, "tech_text": ""}
    bridge.load_tech(TECH.read_text())
    payload = bridge.build_shape(spec)

    cif_polys = _parse_cif(cif_path)
    cif_set = {
        _normalize(pts)
        for layer, pts in cif_polys
        if layer == layer_filter and len(pts) == 4
    }

    # Bridge tags every polygon with a ``metal_name`` so we can pick out
    # just the trace layer for comparison (vias, exit-lead pads, etc.
    # land on different layers and are checked by their own cases).
    py_set: set[tuple[tuple[float, float], ...]] = set()
    for poly in payload["polygons"]:
        py_layer = "L" + str(poly.get("metal_name", "")).upper()
        if py_layer.lstrip("L") != layer_filter.lstrip("L"):
            continue
        for corners in poly.get("segment_polys", []):
            py_set.add(_normalize(corners))

    py_only, cif_only = _diff_polys(py_set, cif_set)
    assert not py_only and not cif_only, (
        f"{stem}: REPL output diverges from CIF golden\n"
        f"  py-only ({len(py_only)}): {sorted(py_only)[:3]}\n"
        f"  cif-only ({len(cif_only)}): {sorted(cif_only)[:3]}"
    )
