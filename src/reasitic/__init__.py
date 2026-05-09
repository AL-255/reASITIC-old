"""reASITIC — reverse-engineered Python implementation of ASITIC.

Top-level package re-exports the most-used symbols. Submodules:

* :mod:`reasitic.tech` — ``.tek`` parser and the Tech / Layer /
  Metal / Via dataclasses.
* :mod:`reasitic.geometry` — Point / Segment / Polygon / Shape and
  9 shape builders (square / polygon / wire / ring / via /
  transformer / 3D-transformer / symmetric-square / balun /
  capacitor).
* :mod:`reasitic.inductance` — Greenhouse partial-inductance
  summation, filament-level current crowding, eddy-current
  correction.
* :mod:`reasitic.resistance` — DC and Wheeler skin-effect AC
  resistance.
* :mod:`reasitic.quality` — metal-loss-only Q.
* :mod:`reasitic.network` — Y/Z/S conversions, Pi/Pi3/Pi4 models,
  Zin, SelfRes, ShuntR, transformer analysis, frequency sweep,
  Touchstone export.
* :mod:`reasitic.optimise` — OptSq, OptPoly, OptArea, OptSymSq,
  BatchOpt, parametric sweeps.
* :mod:`reasitic.substrate` — per-metal-layer parallel-plate shunt
  cap, Sommerfeld Green's function, FFT-grid Green's.
* :mod:`reasitic.exports` — CIF, Sonnet, Tek, SPICE.
* :mod:`reasitic.persistence` — JSON save/load.
* :mod:`reasitic.report` — multi-frequency design report.
* :mod:`reasitic.info` — MetArea, ListSegs, LRMAT.
* :mod:`reasitic.plot` — optional matplotlib helpers.
* :mod:`reasitic.validation` — driver for the legacy ASITIC binary.
* :mod:`reasitic.cli` — REPL CLI (44 commands).
"""

from reasitic._version import __version__
from reasitic.geometry import (
    Point,
    Polygon,
    Segment,
    Shape,
    balun,
    capacitor,
    emit_vias_at_layer_transitions,
    extend_last_segment_to_chip_edge,
    extend_terminal_segment,
    multi_metal_square,
    polygon_edge_vectors,
    polygon_spiral,
    ring,
    shapes_bounding_box,
    square_spiral,
    symmetric_polygon,
    symmetric_square,
    transformer,
    transformer_3d,
    via,
    wire,
)
from reasitic.inductance import (
    compute_mutual_inductance,
    compute_self_inductance,
    coupling_coefficient,
)
from reasitic.quality import metal_only_q
from reasitic.resistance import (
    compute_ac_resistance,
    compute_dc_resistance,
    three_class_resistance,
)
from reasitic.spiral_helpers import (
    segment_pair_distance_metric,
    spiral_max_n,
    spiral_radius_for_n,
    spiral_turn_position,
    wire_position_periodic_fold,
)
from reasitic.tech import (
    Tech,
    parse_tech,
    parse_tech_file,
    write_tech,
    write_tech_file,
)


def summary() -> str:
    """Return a one-line description of this reASITIC install.

    Useful from the REPL or scripts to confirm version, optional
    extras (matplotlib), and Python version. Returns the string;
    callers can ``print(summary())`` if needed.
    """
    import sys

    parts = [f"reASITIC {__version__}"]
    parts.append(f"Python {sys.version_info.major}.{sys.version_info.minor}")
    try:
        import scipy
        parts.append(f"scipy {scipy.__version__}")
    except ImportError:
        parts.append("scipy missing")
    try:
        import matplotlib  # noqa: F401
        parts.append("matplotlib available")
    except ImportError:
        parts.append("matplotlib not installed (pip install reASITIC[plot])")
    return " | ".join(parts)

__all__ = [
    "Point",
    "Polygon",
    "Segment",
    "Shape",
    "Tech",
    "__version__",
    "balun",
    "capacitor",
    "compute_ac_resistance",
    "compute_dc_resistance",
    "compute_mutual_inductance",
    "compute_self_inductance",
    "coupling_coefficient",
    "emit_vias_at_layer_transitions",
    "extend_last_segment_to_chip_edge",
    "extend_terminal_segment",
    "metal_only_q",
    "multi_metal_square",
    "parse_tech",
    "parse_tech_file",
    "polygon_edge_vectors",
    "polygon_spiral",
    "ring",
    "segment_pair_distance_metric",
    "shapes_bounding_box",
    "spiral_max_n",
    "spiral_radius_for_n",
    "spiral_turn_position",
    "square_spiral",
    "summary",
    "symmetric_polygon",
    "symmetric_square",
    "three_class_resistance",
    "transformer",
    "transformer_3d",
    "via",
    "wire",
    "wire_position_periodic_fold",
    "write_tech",
    "write_tech_file",
]
