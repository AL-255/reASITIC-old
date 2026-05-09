"""Tektronix-style line-drawing dumps.

The binary's ``PrintTekFile`` command (case 214) writes a Tek 4014-
emulator command stream that draws the current view to a vector
plotter / terminal. We support two outputs:

* :func:`write_tek` — gnuplot-friendly x/y text format::

      # name=L1 metal=2
      x1 y1
      x2 y2
      ...
      (blank line)

  Loads via ``plot 'foo.tek' with lines``.

* :func:`write_tek4014` — true Tek 4014 escape-code stream
  (GS for graphics, US for ASCII, addressed-vector mode HiY/HiX/LoY/LoX
  bytes). Mirrors the binary's textual output byte-for-byte for tools
  that expect that format (Tektronix terminal emulators).
"""

from __future__ import annotations

from collections.abc import Iterable
from io import StringIO
from pathlib import Path

from reasitic.geometry import Shape


def write_tek(shapes: Iterable[Shape]) -> str:
    """Emit a gnuplot-style x/y dump of every polygon in ``shapes``."""
    out = StringIO()
    for sh in shapes:
        for p in sh.polygons:
            out.write(f"# name={sh.name} metal={p.metal}\n")
            for v in p.vertices:
                out.write(f"{v.x:.4f} {v.y:.4f}\n")
            out.write("\n")
    return out.getvalue()


def write_tek_file(path: str | Path, shapes: Iterable[Shape]) -> None:
    """Write the Tek/gnuplot rendering of ``shapes`` to ``path``."""
    Path(path).write_text(write_tek(shapes))


def write_tek4014(
    shapes: Iterable[Shape],
    *,
    extent_x: float | None = None,
    extent_y: float | None = None,
) -> bytes:
    """Emit a Tek 4014-format escape-code byte stream.

    Tek 4014 graphics: ``\x1d`` enters graphics mode; coordinates
    are 12-bit (0–4095) sent as four bytes::

        HiY = 0x20 + (Y >> 7) & 0x1f
        LoY = 0x60 + (Y & 0x7f) >> 2     # not actually exposed
        HiX = 0x20 + (X >> 7) & 0x1f
        LoX = 0x40 + (X & 0x7f) >> 2

    The first vector after GS is "dark" (move-to); subsequent
    vectors are "bright" (line-to) until the next GS. Returns
    bytes (binary) since Tek 4014 isn't pure ASCII.
    """
    shape_list = list(shapes)
    if not shape_list:
        return b""
    if extent_x is None or extent_y is None:
        all_x: list[float] = []
        all_y: list[float] = []
        for sh in shape_list:
            for p in sh.polygons:
                for v in p.vertices:
                    all_x.append(v.x)
                    all_y.append(v.y)
        if not all_x:
            return b""
        extent_x = max(extent_x or 0, max(all_x) - min(all_x), 1e-6)
        extent_y = max(extent_y or 0, max(all_y) - min(all_y), 1e-6)
        x_off = -min(all_x)
        y_off = -min(all_y)
    else:
        x_off = 0.0
        y_off = 0.0

    out = bytearray()
    GS = 0x1D  # graphics mode

    def addr(x: float, y: float) -> bytes:
        # Map (x, y) into 0..4095 range using the chip extent.
        ix = int(((x + x_off) / max(extent_x, 1e-9)) * 4095.0)
        iy = int(((y + y_off) / max(extent_y, 1e-9)) * 4095.0)
        ix = max(0, min(4095, ix))
        iy = max(0, min(4095, iy))
        hi_y = 0x20 | ((iy >> 7) & 0x1F)
        lo_y = 0x60 | ((iy >> 2) & 0x1F)  # 5-bit rather than 7
        hi_x = 0x20 | ((ix >> 7) & 0x1F)
        lo_x = 0x40 | ((ix >> 2) & 0x1F)
        return bytes([hi_y, lo_y, hi_x, lo_x])

    for sh in shape_list:
        for poly in sh.polygons:
            if not poly.vertices:
                continue
            out.append(GS)  # enter graphics
            v0 = poly.vertices[0]
            out.extend(addr(v0.x, v0.y))  # dark vector (move)
            for v in poly.vertices[1:]:
                out.extend(addr(v.x, v.y))  # bright vector (line-to)
    # Exit graphics with US (unit separator)
    out.append(0x1F)
    return bytes(out)


def write_tek4014_file(
    path: str | Path,
    shapes: Iterable[Shape],
    **kwargs: object,
) -> None:
    """Write a Tek 4014 binary stream to ``path``."""
    Path(path).write_bytes(write_tek4014(shapes, **kwargs))  # type: ignore[arg-type]
