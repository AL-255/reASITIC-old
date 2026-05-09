"""Frequency-swept 2-port analysis.

Drives :func:`reasitic.network.spiral_y_at_freq` over a frequency
range and packages the per-frequency Y / Z / S / Pi results into a
:class:`NetworkSweep` object that can be exported to Touchstone or
inspected programmatically. Mirrors the binary's ``2Port`` /
``2PortX`` / ``2PortGnd`` family of commands (case 528, 539, 529).
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np

from reasitic.geometry import Shape
from reasitic.network.touchstone import TouchstonePoint
from reasitic.network.twoport import (
    PiModel,
    pi_equivalent,
    spiral_y_at_freq,
    y_to_s,
    y_to_z,
)
from reasitic.tech import Tech


@dataclass
class NetworkSweep:
    """A frequency sweep of 2-port parameters for a single shape."""

    freqs_ghz: list[float]
    Y: list[np.ndarray]
    Z: list[np.ndarray]
    S: list[np.ndarray]
    pi: list[PiModel]

    def to_touchstone_points(self, *, param: str = "S") -> list[TouchstonePoint]:
        """Pack the sweep into :class:`TouchstonePoint` rows for export."""
        if param == "S":
            mats = self.S
        elif param == "Y":
            mats = self.Y
        elif param == "Z":
            mats = self.Z
        else:
            raise ValueError(f"unknown param {param!r}")
        return [
            TouchstonePoint(freq_ghz=f, matrix=m)
            for f, m in zip(self.freqs_ghz, mats, strict=True)
        ]


def two_port_sweep(
    shape: Shape,
    tech: Tech,
    freqs_ghz: list[float],
    *,
    z0_ohm: float = 50.0,
) -> NetworkSweep:
    """Compute Y / Z / S / Pi at every frequency in ``freqs_ghz``.

    ``z0_ohm`` is used for the S-parameter conversion (defaults to
    50 Ω, matching the binary's hardcoded reference).
    """
    if not freqs_ghz:
        raise ValueError("freqs_ghz must not be empty")
    y_list: list[np.ndarray] = []
    z_list: list[np.ndarray] = []
    s_list: list[np.ndarray] = []
    pi_list: list[PiModel] = []
    y0 = 1.0 / z0_ohm
    # Y can be singular for series-only spirals (no shunts) — Z then
    # contains inf entries by design. Suppress the divide warnings.
    with np.errstate(divide="ignore", invalid="ignore"):
        for f in freqs_ghz:
            Y = spiral_y_at_freq(shape, tech, freq_ghz=f)
            y_list.append(Y)
            z_list.append(y_to_z(Y))
            s_list.append(y_to_s(Y, y0=y0))
            pi_list.append(pi_equivalent(Y, freq_ghz=f))
    return NetworkSweep(
        freqs_ghz=list(freqs_ghz),
        Y=y_list,
        Z=z_list,
        S=s_list,
        pi=pi_list,
    )


def linear_freqs(start_ghz: float, stop_ghz: float, step_ghz: float) -> list[float]:
    """Generate an inclusive linear frequency list (the binary's stride)."""
    if step_ghz <= 0:
        raise ValueError("step_ghz must be positive")
    if stop_ghz < start_ghz:
        raise ValueError("stop must be >= start")
    n = round((stop_ghz - start_ghz) / step_ghz) + 1
    return [start_ghz + i * step_ghz for i in range(n)]
