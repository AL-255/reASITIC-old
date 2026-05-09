"""DC and AC resistance kernels."""

from reasitic.resistance.dc import compute_dc_resistance, segment_dc_resistance
from reasitic.resistance.skin import (
    ac_resistance_segment,
    compute_ac_resistance,
    skin_depth,
)

__all__ = [
    "ac_resistance_segment",
    "compute_ac_resistance",
    "compute_dc_resistance",
    "segment_dc_resistance",
    "skin_depth",
]
