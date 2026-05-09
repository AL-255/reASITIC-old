"""Touchstone v1 (``.sNp``) writer.

Touchstone is the de-facto interchange format for n-port network
parameters; supported by virtually every RF simulator (ADS, AWR,
Sonnet, HFSS, ngspice). The format spec (`IBIS-Open Forum`,
v1.1, 2002) defines a simple option line followed by one row per
frequency point::

    # <freq_unit> <param_type> <fmt> R <ref_impedance>
    <freq>  <p11_a> <p11_b>  <p12_a> <p12_b>  ...

For 2-port files the entries within a row are ordered
``S11 S21 S12 S22`` (a Touchstone v1 quirk). For higher ports the
ordering is row-major ``S11 S12 ... S1N S21 ...`` with each port row
allowed to span multiple text lines (continued by leading whitespace).

The binary's ``2Port`` REPL command (case 528) prints the same data
in a different textual form; we choose Touchstone because it round-
trips through standard tools and is well documented.
"""

from __future__ import annotations

import math
from collections.abc import Iterable
from dataclasses import dataclass
from io import StringIO
from pathlib import Path

import numpy as np

_FreqUnit = str  # "Hz", "kHz", "MHz", "GHz"


@dataclass
class TouchstonePoint:
    """One entry in a Touchstone sweep: frequency and the matrix at it."""

    freq_ghz: float
    matrix: np.ndarray


def _hz_per_unit(unit: _FreqUnit) -> float:
    """How many Hz one ``unit`` represents (1 GHz = 1e9 Hz)."""
    return {"Hz": 1.0, "kHz": 1.0e3, "MHz": 1.0e6, "GHz": 1.0e9}[unit]


def _format_pair(z: complex, fmt: str) -> tuple[float, float]:
    """Convert a complex value to the two scalars Touchstone records.

    ``fmt`` is one of ``"MA"`` (magnitude/angle in degrees), ``"DB"``
    (20·log10|z| / angle in degrees), or ``"RI"`` (real/imag).
    """
    if fmt == "MA":
        mag = abs(z)
        ang = math.degrees(math.atan2(z.imag, z.real))
        return mag, ang
    if fmt == "DB":
        mag = abs(z)
        db = 20.0 * math.log10(mag) if mag > 0 else -1e6
        ang = math.degrees(math.atan2(z.imag, z.real))
        return db, ang
    if fmt == "RI":
        return z.real, z.imag
    raise ValueError(f"unknown Touchstone fmt {fmt!r}")


def write_touchstone(
    points: Iterable[TouchstonePoint],
    *,
    param: str = "S",
    fmt: str = "MA",
    z0_ohm: float = 50.0,
    freq_unit: _FreqUnit = "GHz",
) -> str:
    """Serialise a sequence of ``TouchstonePoint`` rows to a Touchstone string.

    ``param`` is one of ``"S"``, ``"Y"``, ``"Z"``. ``fmt`` is
    ``"MA"`` / ``"DB"`` / ``"RI"``. Z₀ defaults to 50 Ω.

    For 2-port matrices the entry order within a row is
    ``11 21 12 22`` per Touchstone v1 convention; higher-port files
    use row-major order ``i1 i2 ... iN`` for each i.
    """
    pts = list(points)
    if not pts:
        raise ValueError("at least one frequency point is required")
    n_ports = pts[0].matrix.shape[0]
    if any(p.matrix.shape != (n_ports, n_ports) for p in pts):
        raise ValueError("all points must share the same matrix shape")

    out = StringIO()
    out.write(f"# {freq_unit} {param} {fmt} R {z0_ohm:g}\n")
    hz_per_unit = _hz_per_unit(freq_unit)
    for p in pts:
        # Row-major iteration. For 2-port the Touchstone v1 spec
        # asks for 11 21 12 22; we honour that by transposing the
        # 2x2 case while higher-port files stay row-major.
        if n_ports == 2:
            order = [(0, 0), (1, 0), (0, 1), (1, 1)]
        else:
            order = [(i, j) for i in range(n_ports) for j in range(n_ports)]
        f_native = p.freq_ghz * 1.0e9 / hz_per_unit
        cells = [f"{f_native:.10g}"]
        for i, j in order:
            a, b = _format_pair(complex(p.matrix[i, j]), fmt)
            cells.append(f"{a:.10g}")
            cells.append(f"{b:.10g}")
        out.write(" ".join(cells) + "\n")
    return out.getvalue()


def write_touchstone_file(
    path: str | Path,
    points: Iterable[TouchstonePoint],
    **kwargs: object,
) -> None:
    """Write a Touchstone file. ``kwargs`` are forwarded to
    :func:`write_touchstone`."""
    text = write_touchstone(points, **kwargs)  # type: ignore[arg-type]
    Path(path).write_text(text)


# Reader ------------------------------------------------------------------


@dataclass
class TouchstoneFile:
    """Result of parsing a Touchstone v1 file.

    ``param`` is one of ``"S"`` / ``"Y"`` / ``"Z"``.
    ``points`` is the list of per-frequency matrices.
    ``z0_ohm`` is the reference impedance (typically 50).
    ``n_ports`` is the matrix dimension.
    """

    n_ports: int
    param: str
    z0_ohm: float
    points: list[TouchstonePoint]


def _parse_pair(a: float, b: float, fmt: str) -> complex:
    if fmt == "MA":
        return a * (math.cos(math.radians(b)) + 1j * math.sin(math.radians(b)))
    if fmt == "DB":
        mag = 10 ** (a / 20.0)
        return mag * (math.cos(math.radians(b)) + 1j * math.sin(math.radians(b)))
    if fmt == "RI":
        return complex(a, b)
    raise ValueError(f"unknown Touchstone fmt {fmt!r}")


def read_touchstone(text: str) -> TouchstoneFile:
    """Parse a Touchstone v1 string. Detects port count from line width."""
    lines = [ln.strip() for ln in text.splitlines()]
    # Skip blank/comment lines until we find the option line
    fmt = "MA"
    param = "S"
    z0_ohm = 50.0
    freq_unit = "GHz"
    rows: list[list[float]] = []
    for ln in lines:
        if not ln or ln.startswith("!"):
            continue
        if ln.startswith("#"):
            tokens = ln[1:].split()
            for tok in tokens:
                tu = tok.upper()
                if tu in ("HZ", "KHZ", "MHZ", "GHZ"):
                    freq_unit = {"HZ": "Hz", "KHZ": "kHz",
                                  "MHZ": "MHz", "GHZ": "GHz"}[tu]
                elif tu in ("S", "Y", "Z", "G", "H"):
                    param = tu
                elif tu in ("MA", "DB", "RI"):
                    fmt = tu
                elif tu == "R":
                    pass  # next token is z0
                else:
                    import contextlib
                    with contextlib.suppress(ValueError):
                        z0_ohm = float(tok)
            continue
        rows.append([float(t) for t in ln.split()])

    if not rows:
        raise ValueError("Touchstone file has no data rows")

    # Infer n_ports from row width: 1 freq + n*n*2 scalars
    cells_per_row = len(rows[0])
    # n*n*2 + 1 = cells → n = sqrt((cells - 1) / 2)
    n_squared = (cells_per_row - 1) // 2
    n_ports = round(math.sqrt(n_squared))
    if n_ports * n_ports * 2 + 1 != cells_per_row:
        raise ValueError(
            f"row width {cells_per_row} doesn't match a valid port count"
        )

    # Convert frequency to GHz
    hz_per_unit = _hz_per_unit(freq_unit)

    points: list[TouchstonePoint] = []
    for row in rows:
        f_native = row[0]
        f_ghz = f_native * hz_per_unit / 1.0e9
        # Build the matrix from the 2-scalar pairs
        mat = np.zeros((n_ports, n_ports), dtype=complex)
        if n_ports == 2:
            order = [(0, 0), (1, 0), (0, 1), (1, 1)]
        else:
            order = [(i, j) for i in range(n_ports) for j in range(n_ports)]
        for k, (i, j) in enumerate(order):
            a = row[1 + 2 * k]
            b = row[2 + 2 * k]
            mat[i, j] = _parse_pair(a, b, fmt)
        points.append(TouchstonePoint(freq_ghz=f_ghz, matrix=mat))

    return TouchstoneFile(
        n_ports=n_ports,
        param=param,
        z0_ohm=z0_ohm,
        points=points,
    )


def read_touchstone_file(path: str | Path) -> TouchstoneFile:
    """Read and parse a Touchstone file from disk."""
    return read_touchstone(Path(path).read_text())
