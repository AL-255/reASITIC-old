"""Branch-coverage tests for under-tested non-Tk paths.

Targets the specific uncovered branches in:
- network/sweep.py (param routing in to_touchstone_points,
  linear_freqs validation)
- exports/spice.py (substrate-loss conductance Rsub branch)
- resistance/dc.py (out-of-range metal index → 0 contribution)
- substrate/shunt.py (degenerate polygon / metal layer cases)
"""

from __future__ import annotations

import numpy as np
import pytest

import reasitic
from reasitic.exports import write_spice_subckt
from reasitic.geometry import Point, Polygon, Segment, Shape
from reasitic.network import linear_freqs, two_port_sweep
from reasitic.resistance import segment_dc_resistance
from reasitic.substrate import shape_shunt_capacitance
from reasitic.tech import Layer
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return reasitic.parse_tech_file(_BICMOS)


@pytest.fixture
def spiral(tech):
    return reasitic.square_spiral(
        "L1", length=170, width=10, spacing=3, turns=2,
        tech=tech, metal="m3"
    )


# network/sweep.py -------------------------------------------------------


class TestSweepBranches:
    def test_to_touchstone_y_param(self, spiral, tech):
        sw = two_port_sweep(spiral, tech, [1.0, 2.0])
        pts = sw.to_touchstone_points(param="Y")
        assert len(pts) == 2
        np.testing.assert_array_equal(pts[0].matrix, sw.Y[0])

    def test_to_touchstone_z_param(self, spiral, tech):
        sw = two_port_sweep(spiral, tech, [1.0, 2.0])
        pts = sw.to_touchstone_points(param="Z")
        np.testing.assert_array_equal(pts[1].matrix, sw.Z[1])

    def test_to_touchstone_unknown_param_raises(self, spiral, tech):
        sw = two_port_sweep(spiral, tech, [1.0])
        with pytest.raises(ValueError):
            sw.to_touchstone_points(param="ABCD")

    def test_two_port_sweep_empty_freq_raises(self, spiral, tech):
        with pytest.raises(ValueError):
            two_port_sweep(spiral, tech, [])

    def test_linear_freqs_zero_step_raises(self):
        with pytest.raises(ValueError):
            linear_freqs(1.0, 5.0, 0.0)

    def test_linear_freqs_negative_step_raises(self):
        with pytest.raises(ValueError):
            linear_freqs(1.0, 5.0, -0.5)

    def test_linear_freqs_stop_below_start_raises(self):
        with pytest.raises(ValueError):
            linear_freqs(5.0, 1.0, 0.5)

    def test_linear_freqs_inclusive_endpoint(self):
        fs = linear_freqs(1.0, 3.0, 0.5)
        assert fs[0] == pytest.approx(1.0)
        assert fs[-1] == pytest.approx(3.0)


# exports/spice.py -------------------------------------------------------


class TestSpiceSubstrateLossBranch:
    def test_substrate_loss_emits_rsub_lines(self, monkeypatch, tech):
        """When the Pi-model has positive substrate-loss conductance,
        the SPICE deck should emit Rsub1 / Rsub2 nodes.

        The default substrate model produces g_p1 = g_p2 = 0
        (purely capacitive shunt), so we monkeypatch
        ``pi_model_at_freq`` to return a synthetic PiResult with
        positive conductance to exercise the loss branch.
        """
        from reasitic.exports import spice as spice_mod
        from reasitic.network.analysis import PiResult

        sp = reasitic.square_spiral(
            "L1", length=200, width=10, spacing=2, turns=3,
            tech=tech, metal="m3",
        )

        def _lossy_pi(shape, tech, freq_ghz):
            return PiResult(
                freq_ghz=freq_ghz, L_nH=2.0, R_series=1.5,
                C_p1_fF=50.0, C_p2_fF=50.0,
                g_p1=1e-3, g_p2=2e-3,
            )

        monkeypatch.setattr(spice_mod, "pi_model_at_freq", _lossy_pi)
        text = write_spice_subckt(sp, tech, freq_ghz=2.4)
        assert "Rsub1" in text
        assert "Rsub2" in text

    def test_lossless_pi_omits_rsub_lines(self, tech):
        """No Rsub lines for the default lossless Pi model."""
        sp = reasitic.square_spiral(
            "L1", length=200, width=10, spacing=2, turns=3,
            tech=tech, metal="m3",
        )
        text = write_spice_subckt(sp, tech, freq_ghz=2.4)
        assert "Rsub" not in text


# resistance/dc.py -------------------------------------------------------


class TestSegmentDCResistance:
    def test_zero_length_returns_zero(self, tech):
        seg = Segment(
            a=Point(0, 0, 0), b=Point(0, 0, 0),
            width=10.0, thickness=1.0, metal=0,
        )
        assert segment_dc_resistance(seg, tech) == 0.0

    def test_zero_width_returns_zero(self, tech):
        seg = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=0.0, thickness=1.0, metal=0,
        )
        assert segment_dc_resistance(seg, tech) == 0.0

    def test_out_of_range_metal_returns_zero(self, tech):
        """Past the metal-layer count → 0 contribution rather than
        silently using a wrong layer's rsh."""
        seg = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=10.0, thickness=1.0, metal=999,
        )
        assert segment_dc_resistance(seg, tech) == 0.0

    def test_negative_metal_returns_zero(self, tech):
        seg = Segment(
            a=Point(0, 0, 0), b=Point(100, 0, 0),
            width=10.0, thickness=1.0, metal=-1,
        )
        assert segment_dc_resistance(seg, tech) == 0.0


# substrate/shunt.py -----------------------------------------------------


class TestShuntBranches:
    def test_shunt_no_layers_returns_zero(self, tech):
        empty_tech = type(
            "T", (), {
                "chip": tech.chip, "layers": [],
                "metals": tech.metals, "vias": tech.vias,
            }
        )()
        sp = reasitic.square_spiral(
            "L", length=100, width=10, spacing=2, turns=1,
            tech=tech, metal="m3"
        )
        assert shape_shunt_capacitance(sp, empty_tech) == 0.0

    def test_shunt_skips_polygons_with_invalid_metal(self, tech):
        """A polygon whose metal index is past the metal-layer count
        should be silently skipped (not crash)."""
        sh = Shape(
            name="X",
            polygons=[
                Polygon(
                    vertices=[
                        Point(0, 0, 0), Point(10, 0, 0),
                        Point(10, 10, 0), Point(0, 0, 0),
                    ],
                    metal=999,
                )
            ],
        )
        # Should return 0 (skipped) rather than raise
        assert shape_shunt_capacitance(sh, tech) == 0.0

    def test_shunt_skips_metal_with_invalid_layer(self, tech):
        """A metal whose .layer index is past the substrate layer
        count should be skipped."""
        # Build a tech variant where m3's layer points past the
        # substrate-layer count.
        bogus_tech = type(
            "T", (), {
                "chip": tech.chip,
                "layers": [tech.layers[0]],  # only 1 layer
                "metals": [
                    type(
                        "M", (), {
                            "name": "mX", "rsh": 0.0, "t": 1.0, "d": 0.5,
                            "layer": 99, "color": "white",
                            "index": 0, "extra": {},
                        }
                    )()
                ],
                "vias": [],
            }
        )()
        sh = Shape(
            name="X",
            polygons=[
                Polygon(
                    vertices=[
                        Point(0, 0, 0), Point(10, 0, 0),
                        Point(10, 10, 0), Point(0, 0, 0),
                    ],
                    metal=0,
                )
            ],
        )
        assert shape_shunt_capacitance(sh, bogus_tech) == 0.0

    def test_shunt_zero_path_height_returns_zero(self):
        """A metal sitting on layer 0 with d=0 → h_total = 0 → skip."""
        layer0 = Layer(index=0, rho=10.0, t=100.0, eps=11.7)
        bogus_tech = type(
            "T", (), {
                "chip": type("C", (), {"chipx": 0, "chipy": 0})(),
                "layers": [layer0],
                "metals": [
                    type(
                        "M", (), {
                            "name": "mZ", "rsh": 0.0, "t": 0.0, "d": 0.0,
                            "layer": 0, "color": "white",
                            "index": 0, "extra": {},
                        }
                    )()
                ],
                "vias": [],
            }
        )()
        sh = Shape(
            name="Z",
            polygons=[
                Polygon(
                    vertices=[
                        Point(0, 0, 0), Point(10, 0, 0),
                        Point(10, 10, 0), Point(0, 0, 0),
                    ],
                    metal=0,
                )
            ],
        )
        assert shape_shunt_capacitance(sh, bogus_tech) == 0.0
