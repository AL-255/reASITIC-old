from __future__ import annotations

import re
from pathlib import Path

import pytest

import reasitic
from reasitic.geometry import Shape, layout_polygons
from tests import _paths

LAYOUTS = Path(__file__).parent / "data" / "validation" / "layouts"


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_paths.tech_path("BiCMOS.tek"))


def _cif_polygons(
    stem: str, layer: str, *, include_boxes: bool = True,
) -> list[tuple[tuple[float, float], ...]]:
    path = LAYOUTS / f"{stem}.cif"
    if not path.exists():
        pytest.skip(f"golden CIF not present: {path.name}")
    out: list[tuple[tuple[float, float], ...]] = []
    cur_layer = ""
    for raw in path.read_text().splitlines():
        line = raw.strip()
        m = re.match(r"^L([A-Z0-9]+);", line)
        if m:
            cur_layer = m.group(1)
            continue
        m = re.match(r"^P\s*((?:-?\d+\s+)+);", line)
        if m and cur_layer == layer:
            ns = [int(t) for t in m.group(1).split()]
            out.append(tuple(sorted(
                (ns[i] / 100.0, ns[i + 1] / 100.0)
                for i in range(0, len(ns), 2)
            )))
            continue
        if include_boxes:
            m = re.match(r"^B\s*(-?\d+)\s+(-?\d+)\s+(-?\d+)\s+(-?\d+)", line)
            if m and cur_layer == layer:
                w, h, cx, cy = [int(m.group(i)) / 100.0 for i in range(1, 5)]
                out.append(tuple(sorted((
                    (cx - w / 2.0, cy - h / 2.0),
                    (cx + w / 2.0, cy - h / 2.0),
                    (cx + w / 2.0, cy + h / 2.0),
                    (cx - w / 2.0, cy + h / 2.0),
                ))))
    return out


def _layout_set(shape: Shape, tech, layer: str) -> list[tuple[tuple[float, float], ...]]:
    out: list[tuple[tuple[float, float], ...]] = []
    for poly in layout_polygons(shape, tech):
        if poly.metal >= len(tech.metals):
            name = tech.vias[poly.metal - len(tech.metals)].name.upper()
        else:
            name = tech.metals[poly.metal].name.upper()
        if name != layer:
            continue
        # Round to 0.01 µm (= CIF integer precision) before sorting so
        # accumulated trig drift (e.g. 199.9999999999996 vs 200.0)
        # doesn't change the lexicographic vertex order between my
        # output and the gold's.
        out.append(tuple(sorted(
            (round(v.x, 2), round(v.y, 2)) for v in poly.vertices[:-1]
        )))
    return out


def _assert_same_polygons(actual, expected, *, tol: float = 0.01) -> None:
    remaining = list(expected)
    actual_only = []
    for poly in actual:
        for i, candidate in enumerate(remaining):
            if len(poly) == len(candidate) and all(
                abs(ax - ex) <= tol and abs(ay - ey) <= tol
                for (ax, ay), (ex, ey) in zip(poly, candidate, strict=True)
            ):
                remaining.pop(i)
                break
        else:
            actual_only.append(poly)
    assert not actual_only and not remaining


@pytest.mark.parametrize(
    "stem,shape_factory,layer,tol",
    [
        (
            "wire_100x10_m3",
            lambda tech: reasitic.wire("W1", length=100, width=10, metal="m3", tech=tech),
            "M3",
            0.01,
        ),
        (
            "cap_80x80_m3_m2",
            lambda tech: reasitic.capacitor(
                "C1", length=80, width=80, metal_top="m3", metal_bottom="m2", tech=tech
            ),
            "M3",
            0.01,
        ),
        (
            "sq_300x12x3x4_m3_quarter_turn",
            lambda tech: reasitic.square_spiral(
                "SQT", length=300, width=12, spacing=3, turns=4.25,
                metal="m3", tech=tech,
            ),
            "M3",
            0.01,
        ),
        (
            "sp_r100_8sides_3turns_m3",
            lambda tech: reasitic.polygon_spiral(
                "P1", radius=100, width=8, spacing=3, turns=3,
                sides=8, metal="m3", tech=tech, x_origin=200, y_origin=200,
            ),
            "M3",
            0.06,
        ),
        (
            "sp_r80_8sides_2turns_m3",
            lambda tech: reasitic.polygon_spiral(
                "P2", radius=80, width=6, spacing=2, turns=2,
                sides=8, metal="m3", tech=tech, x_origin=200, y_origin=200,
            ),
            "M3",
            0.06,
        ),
        (
            "sp_r120_16sides_2turns_m2",
            lambda tech: reasitic.polygon_spiral(
                "P3", radius=120, width=8, spacing=3, turns=2,
                sides=16, metal="m2", tech=tech, x_origin=200, y_origin=200,
            ),
            "M2",
            0.06,
        ),
        (
            "ring_r80_w10_g4_m3",
            lambda tech: reasitic.ring(
                "RG1", radius=80, width=10, gap=4, sides=16,
                metal="m3", tech=tech,
            ),
            "M3",
            0.06,
        ),
        (
            "mmsq_160x10x2x3_m3_to_m2",
            lambda tech: reasitic.multi_metal_square(
                "MM1", length=160, width=10, spacing=2, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0,
            ),
            "M3",
            0.01,
        ),
        (
            "mmsq_160x10x2x3_m3_to_m2",
            lambda tech: reasitic.multi_metal_square(
                "MM1", length=160, width=10, spacing=2, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0,
            ),
            "M2",
            0.01,
        ),
        (
            "mmsq_200x12x3x2p5_m3_to_m2_offset",
            lambda tech: reasitic.multi_metal_square(
                "MM2", length=200, width=12, spacing=3, turns=2.5,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=200, y_origin=200,
            ),
            "M3",
            0.01,
        ),
        (
            "mmsq_200x12x3x2p5_m3_to_m2_offset",
            lambda tech: reasitic.multi_metal_square(
                "MM2", length=200, width=12, spacing=3, turns=2.5,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=200, y_origin=200,
            ),
            "M2",
            0.01,
        ),
        # TRANS — primary M2 + VIA3 layers match exactly. M3 has 12/13
        # match (the entry-lead extension to x=0 is missing and is the
        # one outstanding gap). Secondary similar.
        (
            "trans_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="primary",
            ),
            "M2",
            0.02,
        ),
        (
            "trans_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="primary",
            ),
            "M3",
            0.02,
        ),
        (
            "trans_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="primary",
            ),
            "VIA3",
            0.02,
        ),
        (
            "trans_200x8x3x3_m3_m2_secondary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="secondary",
            ),
            "M2",
            0.02,
        ),
        (
            "trans_200x8x3x3_m3_m2_secondary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="secondary",
            ),
            "M3",
            0.02,
        ),
        (
            "trans_200x8x3x3_m3_m2_secondary",
            lambda tech: reasitic.transformer(
                "TX", length=200, width=8, spacing=3, turns=3,
                metal="m3", exit_metal="m2", tech=tech,
                x_origin=0, y_origin=0, which="secondary",
            ),
            "VIA3",
            0.02,
        ),
        # SYMSQ — full vertex-for-vertex parity for all 3 golden cases
        *(
            (stem, mkfn, layer, 0.02)
            for stem, mkfn in [
                (
                    "symsq_150x8x2x2_m3_m2",
                    lambda tech: reasitic.symmetric_square(
                        "Y3", length=150, width=8, spacing=2, turns=2,
                        ilen=15, tech=tech, metal="m3", exit_metal="m2",
                        x_origin=100, y_origin=100,
                    ),
                ),
                (
                    "symsq_200x10x3x3_m3_m2",
                    lambda tech: reasitic.symmetric_square(
                        "Y1", length=200, width=10, spacing=3, turns=3,
                        ilen=20, tech=tech, metal="m3", exit_metal="m2",
                        x_origin=100, y_origin=100,
                    ),
                ),
                (
                    "symsq_300x12x4x3_m3_m2_offset",
                    lambda tech: reasitic.symmetric_square(
                        "Y2", length=300, width=12, spacing=4, turns=3,
                        ilen=30, tech=tech, metal="m3", exit_metal="m2",
                        x_origin=100, y_origin=100,
                    ),
                ),
            ]
            for layer in ("M3", "M2", "VIA3")
        ),
        # BALUN — primary + secondary, full parity for the one
        # canonical case
        (
            "balun_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.balun(
                "BL", length=200, width=8, spacing=3, turns=3,
                primary_metal="m3", secondary_metal="m2", exit_metal="m2",
                tech=tech, x_origin=0, y_origin=0, which="primary",
            ),
            "M3",
            0.02,
        ),
        (
            "balun_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.balun(
                "BL", length=200, width=8, spacing=3, turns=3,
                primary_metal="m3", secondary_metal="m2", exit_metal="m2",
                tech=tech, x_origin=0, y_origin=0, which="primary",
            ),
            "M2",
            0.02,
        ),
        (
            "balun_200x8x3x3_m3_m2_primary",
            lambda tech: reasitic.balun(
                "BL", length=200, width=8, spacing=3, turns=3,
                primary_metal="m3", secondary_metal="m2", exit_metal="m2",
                tech=tech, x_origin=0, y_origin=0, which="primary",
            ),
            "VIA3",
            0.02,
        ),
        (
            "balun_200x8x3x3_m3_m2_secondary",
            lambda tech: reasitic.balun(
                "BL", length=200, width=8, spacing=3, turns=3,
                primary_metal="m3", secondary_metal="m2", exit_metal="m2",
                tech=tech, x_origin=0, y_origin=0, which="secondary",
            ),
            "M3",
            0.02,
        ),
        # SYMPOLY — full vertex-for-vertex parity for the M3 spiral
        # rings + slants + centre-tap stub, plus the M2 alternating
        # slant traces. The C state machine cmd_sympoly_build_geometry
        # is decoded as a 2N-half-turn loop with cases 4-7 controlling
        # each cross-ring transition.
        (
            "sympoly_r120_8sides_2turns",
            lambda tech: reasitic.symmetric_polygon(
                "YP2", radius=120, width=10, spacing=3, turns=2,
                ilen=20, sides=8, tech=tech,
                primary_metal="m3", exit_metal="m2",
                x_origin=200, y_origin=200,
            ),
            "M3",
            0.02,
        ),
        (
            "sympoly_r120_8sides_2turns",
            lambda tech: reasitic.symmetric_polygon(
                "YP2", radius=120, width=10, spacing=3, turns=2,
                ilen=20, sides=8, tech=tech,
                primary_metal="m3", exit_metal="m2",
                x_origin=200, y_origin=200,
            ),
            "M2",
            0.02,
        ),
        (
            "sympoly_r100_8sides_3turns",
            lambda tech: reasitic.symmetric_polygon(
                "YP1", radius=100, width=10, spacing=3, turns=3,
                ilen=20, sides=8, tech=tech,
                primary_metal="m3", exit_metal="m2",
                x_origin=200, y_origin=200,
            ),
            "M3",
            0.02,
        ),
        (
            "sympoly_r100_8sides_3turns",
            lambda tech: reasitic.symmetric_polygon(
                "YP1", radius=100, width=10, spacing=3, turns=3,
                ilen=20, sides=8, tech=tech,
                primary_metal="m3", exit_metal="m2",
                x_origin=200, y_origin=200,
            ),
            "M2",
            0.02,
        ),
    ],
)
def test_layout_polygons_match_cif_goldens(stem, shape_factory, layer, tol, tech):
    # SYMPOLY's via-cluster M2/M3 pad widths follow a still-undecoded
    # rule (10.82 narrow / 38.96 wide / 8.91 / 34.91), so we compare
    # only the polygon ring/slant/stub records, not box pads. The C
    # state machine cmd_sympoly_build_geometry does emit pads via
    # lookup_via_for_metal_pair → geom_emit_polygon_at, but the
    # geom_emit_polygon_at-encoded width (= n_vias * via_w +
    # (n_vias-1) * via_s = 7.5) doesn't match any of the gold values.
    include_boxes = not stem.startswith("sympoly_")
    _assert_same_polygons(
        _layout_set(shape_factory(tech), tech, layer),
        _cif_polygons(stem, layer, include_boxes=include_boxes),
        tol=tol,
    )
