"""DC and AC resistance kernels."""

from reasitic.resistance.dc import compute_dc_resistance, segment_dc_resistance
from reasitic.resistance.skin import (
    ac_resistance_segment,
    compute_ac_resistance,
    skin_depth,
)
from reasitic.resistance.three_class import (
    ThreeClassResistance,
    three_class_resistance,
)

__all__ = [
    "ThreeClassResistance",
    "ac_resistance_segment",
    "compute_ac_resistance",
    "compute_dc_resistance",
    "segment_dc_resistance",
    "skin_depth",
    "three_class_resistance",
]
