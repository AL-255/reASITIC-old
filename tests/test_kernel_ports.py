"""Consolidated tests for the kernel-port additions.

Covers polygon edge ops, chip-edge extension, three-class DC R,
shapes_bounding_box, propagation constant + layer reflection
coefficient, eddy_packed_index, Sommerfeld inner-integrand
cluster, mutual_inductance_filament_kernel, wire_axial_separation,
wire_separation_periodic.
"""

from __future__ import annotations

import math

import numpy as np
import pytest

import reasitic
from reasitic.geometry import (
    Point,
    Polygon,
    Shape,
    extend_last_segment_to_chip_edge,
    polygon_edge_vectors,
    shapes_bounding_box,
)
from reasitic.inductance import (
    auto_filament_subdivisions_critical,
    eddy_packed_index,
    mutual_inductance_filament_kernel,
    wire_axial_separation,
    wire_separation_periodic,
)
from reasitic.network import (
    back_substitute_solution,
    build_segment_node_list,
)
from reasitic.resistance import three_class_resistance
from reasitic.substrate import (
    green_function_kernel_a_oscillating,
    green_function_kernel_b_reflection,
    green_oscillating_integrand,
    green_propagation_integrand,
    layer_reflection_coefficient,
    propagation_constant,
)
from reasitic.substrate.green import TWO_PI_MU0
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=100, width=10, spacing=2, turns=2,
        tech=tech, metal="m3"
    )


# ---- polygon_edge_vectors ----------------------------------------------


class TestPolygonEdgeVectors:
    @pytest.mark.parametrize("direction", ["forward", "backward"])
    def test_consecutive_diffs(self, direction):
        poly = Polygon(
            vertices=[Point(0, 0, 0), Point(10, 0, 0),
                      Point(10, 5, 0), Point(0, 5, 0)],
            metal=0,
        )
        assert polygon_edge_vectors(poly, direction=direction) == [
            (10.0, 0.0), (0.0, 5.0), (-10.0, 0.0)
        ]

    def test_empty_polygon(self):
        poly = Polygon(vertices=[Point(0, 0, 0)], metal=0)
        assert polygon_edge_vectors(poly) == []

    def test_invalid_direction_raises(self):
        poly = Polygon(vertices=[Point(0, 0, 0), Point(1, 0, 0)], metal=0)
        with pytest.raises(ValueError):
            polygon_edge_vectors(poly, direction="diagonal")


# ---- extend_last_segment_to_chip_edge ----------------------------------


class TestExtendLastSegmentToChipEdge:
    def test_extends_north_facing_to_chipy(self, tech):
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech,
                           x_origin=100, y_origin=10)
        vert = sh.rotate_xy(math.pi / 2)
        out = extend_last_segment_to_chip_edge(vert, tech)
        assert out.polygons[-1].vertices[-1].y == pytest.approx(tech.chip.chipy)

    def test_extends_east_facing_to_chipx(self, tech):
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech,
                           x_origin=100, y_origin=100)
        out = extend_last_segment_to_chip_edge(sh, tech)
        assert out.polygons[-1].vertices[-1].x == pytest.approx(tech.chip.chipx)

    def test_no_op_with_zero_chip(self, tech):
        zero_tech = type(
            "T", (), {"chip": type("C", (), {"chipx": 0, "chipy": 0})()}
        )()
        sh = reasitic.wire("W", length=50, width=2, metal="m3", tech=tech)
        out = extend_last_segment_to_chip_edge(sh, zero_tech)
        assert out.polygons[-1].vertices[-1].x == sh.polygons[-1].vertices[-1].x

    def test_empty_shape_returns_unchanged(self, tech):
        empty = Shape(name="EMPTY")
        assert extend_last_segment_to_chip_edge(empty, tech) is empty


# ---- three_class_resistance --------------------------------------------


class TestThreeClassResistance:
    def test_buckets_positive_and_ordered(self, tech):
        sh = reasitic.square_spiral(
            "L", length=200, width=10, spacing=2, turns=3,
            tech=tech, metal="m3"
        )
        r = three_class_resistance(sh, tech)
        assert r.R_a > 0 and r.R_b > 0 and r.R_c > 0
        assert r.R_a > r.R_b   # bucket-A coefficient on R_seg dominates

    def test_scales_linearly(self, tech):
        small = reasitic.wire("W1", length=100, width=10, metal="m3", tech=tech)
        big = reasitic.wire("W2", length=200, width=10, metal="m3", tech=tech)
        rs = three_class_resistance(small, tech)
        rb = three_class_resistance(big, tech)
        for a, b in zip(
            (rs.R_a, rs.R_b, rs.R_c), (rb.R_a, rb.R_b, rb.R_c), strict=True,
        ):
            assert b == pytest.approx(2.0 * a, rel=1e-9)

    def test_zero_for_empty_shape(self, tech):
        r = three_class_resistance(Shape(name="EMPTY"), tech)
        assert r == type(r)(R_a=0.0, R_b=0.0, R_c=0.0)


# ---- shapes_bounding_box -----------------------------------------------


class TestShapesBoundingBox:
    def test_empty_with_tech_returns_chip(self, tech):
        bb = shapes_bounding_box([], tech=tech)
        assert bb == (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)

    def test_empty_no_tech_returns_zeros(self):
        assert shapes_bounding_box([]) == (0.0, 0.0, 0.0, 0.0)

    def test_dict_input_works(self, tech):
        sh = reasitic.square_spiral("L1", length=200, width=10, spacing=2,
                                    turns=3, tech=tech, metal="m3")
        assert shapes_bounding_box({"L1": sh}, tech=tech) == pytest.approx(
            sh.bounding_box()
        )

    def test_union_covers_disjoint_shapes(self, tech):
        a = reasitic.square_spiral("A", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3")
        b = reasitic.square_spiral("B", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3",
                                   x_origin=200, y_origin=300)
        bb = shapes_bounding_box([a, b], tech=tech)
        assert bb[0] <= a.x_origin and bb[1] <= a.y_origin
        assert bb[2] >= b.x_origin and bb[3] >= b.y_origin

    def test_x_origin_y_origin_added(self, tech):
        a = reasitic.square_spiral("A", length=50, width=2, spacing=1,
                                   turns=2, tech=tech, metal="m3",
                                   x_origin=100, y_origin=200)
        bb = shapes_bounding_box([a])
        local_bb = a.bounding_box()
        assert bb[0] == pytest.approx(local_bb[0] + 100)
        assert bb[1] == pytest.approx(local_bb[1] + 200)

    def test_all_empty_falls_back_to_chip(self, tech):
        bb = shapes_bounding_box([Shape(name="EMPTY")], tech=tech)
        assert bb == (0.0, 0.0, tech.chip.chipx, tech.chip.chipy)


# ---- propagation_constant ----------------------------------------------


class TestPropagationConstant:
    @pytest.mark.parametrize("omega,sigma", [(0.0, 10.0),
                                             (2 * math.pi * 1e9, 0.0)])
    def test_zero_omega_or_sigma_collapses_to_real(self, omega, sigma):
        """ω=0 or σ=0 → γ = k_ρ exactly (the j·μ₀σω term vanishes)."""
        k = 100.0
        gamma = propagation_constant(k, omega_rad=omega, sigma_S_per_m=sigma)
        assert gamma == pytest.approx(complex(k, 0.0))

    def test_real_imag_both_positive(self):
        gamma = propagation_constant(1e3, 2 * math.pi * 1e9, 10.0)
        assert gamma.real > 0 and gamma.imag > 0

    def test_known_constant_2pi_mu0(self):
        assert pytest.approx(2 * math.pi * 4e-7 * math.pi,
                             rel=1e-12) == TWO_PI_MU0

    def test_gamma_squared_identity(self):
        """γ² = k² + j·2πμ₀σω."""
        k, w, s = 50.0, 2 * math.pi * 5e9, 10.0
        gamma = propagation_constant(k, w, s)
        assert gamma * gamma == pytest.approx(
            complex(k * k, TWO_PI_MU0 * s * w), rel=1e-9
        )


# ---- layer_reflection_coefficient --------------------------------------


class TestLayerReflectionCoefficient:
    def test_zero_sigma_returns_zero(self):
        gamma = layer_reflection_coefficient(
            k_rho=100.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=0.0
        )
        assert gamma == pytest.approx(complex(0.0, 0.0), abs=1e-12)

    def test_high_sigma_approaches_minus_one(self):
        gamma = layer_reflection_coefficient(
            k_rho=10.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=1e6,
        )
        assert abs(gamma + 1.0) < 0.5

    @pytest.mark.parametrize("sigma", [0.1, 10.0, 1000.0])
    @pytest.mark.parametrize("omega", [1e8, 1e10])
    def test_magnitude_passive_bound(self, sigma, omega):
        """Passive lossy substrate satisfies |Γ| ≤ 1."""
        gamma = layer_reflection_coefficient(
            k_rho=100.0, omega_rad=omega, sigma_S_per_m=sigma,
        )
        assert abs(gamma) <= 1.0 + 1e-9

    def test_imag_negative_for_passive(self):
        gamma = layer_reflection_coefficient(
            k_rho=10.0, omega_rad=2 * math.pi * 1e9, sigma_S_per_m=10.0,
        )
        assert gamma.imag < 0


# ---- eddy_packed_index -------------------------------------------------


class TestEddyPackedIndex:
    @pytest.mark.parametrize("i,j,expected", [
        (1, 1, 1), (2, 2, 5), (3, 3, 9), (5, 5, 17),    # diagonal: 4i-3
        (3, 1, -1), (4, 2, 3), (5, 1, -9),              # off-diag: 8j-4i+3
    ])
    def test_index(self, i, j, expected):
        assert eddy_packed_index(i, j) == expected


# ---- Sommerfeld integrands --------------------------------------------


class TestSommerfeldIntegrands:
    def test_oscillating_returns_finite_complex(self):
        v = green_oscillating_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, rho_m=1e-5,
        )
        assert isinstance(v, complex) and math.isfinite(v.real)

    def test_oscillating_zero_omega_real_at_dc(self):
        v = green_oscillating_integrand(
            k_rho=1e3, omega_rad=0.0,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, rho_m=1e-5,
        )
        assert abs(v.imag) < 1e-9

    def test_propagation_returns_finite(self):
        v = green_propagation_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        assert isinstance(v, complex) and math.isfinite(v.real)

    def test_propagation_huge_z_decays(self):
        v = green_propagation_integrand(
            k_rho=1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1.0,
        )
        assert abs(v) < 1e-3

    def test_kernel_a_oscillating_zero_kappa(self):
        assert green_function_kernel_a_oscillating(
            0.0, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        ) == 0.0

    def test_kernel_a_decays_at_large_kappa(self):
        small = green_function_kernel_a_oscillating(
            1e2, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-3,
        )
        large = green_function_kernel_a_oscillating(
            1e6, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-3,
        )
        assert abs(large) < abs(small)

    def test_kernel_b_uses_reflection(self):
        a = green_function_kernel_a_oscillating(
            1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        b = green_function_kernel_b_reflection(
            1e3, omega_rad=2 * math.pi * 1e9,
            sigma_a_S_per_m=10.0, sigma_b_S_per_m=1.0,
            layer_thickness_m=1e-4, z_m=1e-5,
        )
        assert math.isfinite(a) and math.isfinite(b)
        assert abs(b) <= abs(a) + 1e-9


# ---- Filament-pair primitives ------------------------------------------


class TestFilamentPairPrimitives:
    @pytest.mark.parametrize("a1,a2,b1,b2,expected", [
        # parallel → +1
        ((0, 0, 0), (100, 0, 0), (0, 10, 0), (100, 10, 0), 1.0),
        # anti-parallel → -1
        ((0, 0, 0), (100, 0, 0), (100, 10, 0), (0, 10, 0), -1.0),
        # perpendicular → 0
        ((0, 0, 0), (100, 0, 0), (0, 0, 0), (0, 100, 0), 0.0),
    ])
    def test_filament_kernel(self, a1, a2, b1, b2, expected):
        assert mutual_inductance_filament_kernel(
            Point(*a1), Point(*a2), Point(*b1), Point(*b2)
        ) == pytest.approx(expected)

    def test_filament_kernel_45deg(self):
        v = mutual_inductance_filament_kernel(
            Point(0, 0, 0), Point(100, 0, 0),
            Point(0, 0, 0), Point(50, 50, 0),
        )
        assert v == pytest.approx(1.0 / math.sqrt(2.0), rel=1e-9)

    def test_filament_zero_length(self):
        assert mutual_inductance_filament_kernel(
            Point(0, 0, 0), Point(0, 0, 0),
            Point(0, 0, 0), Point(50, 50, 0),
        ) == 0.0

    def test_wire_axial_separation_minus_radii(self):
        # |B-A| = 50, radii=2 → 50 - 4 = 46
        s = wire_axial_separation(Point(0, 0, 0), Point(30, 40, 0),
                                   radius_um=2.0)
        assert s == pytest.approx(46.0)

    def test_wire_axial_zero_radius_is_distance(self):
        assert wire_axial_separation(
            Point(0, 0, 0), Point(0, 0, 100)
        ) == pytest.approx(100.0)

    def test_wire_axial_can_be_negative(self):
        assert wire_axial_separation(
            Point(0, 0, 0), Point(0, 0, 1), radius_um=10.0
        ) < 0

    def test_wire_separation_periodic_signs(self):
        # both below fold → +
        v = wire_separation_periodic(
            i=2, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert v >= 0
        # split → −
        v = wire_separation_periodic(
            i=15, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert v <= 0

    def test_wire_separation_periodic_signed_sqrt_form(self):
        v_ab = wire_separation_periodic(
            i=2, j=3, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        v_ba = wire_separation_periodic(
            i=3, j=2, width_um=1.0, spacing_um=1.0, fold_size=10
        )
        assert abs(v_ab) == pytest.approx(abs(v_ba))


class TestBackSubstituteSolution:
    def test_passthrough_no_perm(self):
        x = np.array([1, 2, 3, 4], dtype=complex)
        out = back_substitute_solution(x)
        np.testing.assert_array_equal(out, x)

    def test_with_bias(self):
        x = np.array([1, 2, 3], dtype=complex)
        out = back_substitute_solution(x, bias=10.0)
        np.testing.assert_array_equal(out, [11, 12, 13])

    def test_node_index_permutation(self):
        x = np.array([10, 20, 30, 40], dtype=complex)
        out = back_substitute_solution(x, node_indices=[3, 1, 0])
        np.testing.assert_array_equal(out, [40, 20, 10])


# build_segment_node_list ------------------------------------------------


class TestBuildSegmentNodeList:
    def test_returns_one_entry_per_vertex(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        # Total = sum of vertex counts across polygons
        total_vertices = sum(len(p.vertices) for p in spiral.polygons)
        assert len(nodes) == total_vertices

    def test_metal_index_recorded(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        m3 = tech.metal_by_name("m3").index
        # Square spiral on m3 — every entry has metal == m3
        assert all(metal == m3 for _, _, metal in nodes)

    def test_polygon_indices_monotone(self, spiral, tech):
        nodes = build_segment_node_list(spiral, tech)
        # poly indices go 0, 0, ..., 1, 1, ... — monotone non-decreasing
        prev = -1
        for pi, _, _ in nodes:
            assert pi >= prev
            prev = pi

    def test_empty_shape(self, tech):
        from reasitic.geometry import Shape
        out = build_segment_node_list(Shape(name="EMPTY"), tech)
        assert out == []


# auto_filament_subdivisions_critical ------------------------------------


class TestAutoFilamentSubdivisionsCritical:
    def test_critical_picks_finer_cells(self, spiral, tech):
        """Critical mode uses 2× cells-per-skin-depth, so it should
        produce subdivisions ≥ those of normal mode (capped by n_max)."""
        from reasitic.inductance import auto_filament_subdivisions
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w_n, n_t_n = auto_filament_subdivisions(
            seg, rsh, freq_ghz=10.0,
        )
        n_w_c, n_t_c = auto_filament_subdivisions_critical(
            seg, rsh, freq_ghz=10.0,
        )
        assert n_w_c >= n_w_n
        assert n_t_c >= n_t_n

    def test_returns_at_least_one_each(self, spiral, tech):
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w, n_t = auto_filament_subdivisions_critical(
            seg, rsh, freq_ghz=2.0,
        )
        assert n_w >= 1
        assert n_t >= 1

    def test_dc_returns_one_one(self, spiral, tech):
        seg = spiral.segments()[0]
        rsh = tech.metal_by_name("m3").rsh
        n_w, n_t = auto_filament_subdivisions_critical(seg, rsh, freq_ghz=0.0)
        assert n_w == 1 and n_t == 1
