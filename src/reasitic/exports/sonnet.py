"""Sonnet-em ``.son`` exporter (subset).

The binary's ``SonnetSave`` command (case 302) writes a Sonnet
project file that loads directly into Sonnet's full-wave EM
solver. Sonnet's format is verbose and mostly metadata; we emit the
subset needed to reproduce the spiral's geometry and layer stack
within a Sonnet project.

The header layout is::

    FTYP SONPROJ 16 ! Sonnet Project File
    HEADER
    LIC ...
    DAT ...
    BUILT_BY_AUTHOR <user>
    MDATE ...
    HDATE ...
    END HEADER
    DIM
    FREQUENCY GHZ
    INDUCTANCE NH
    LENGTH UM
    ...
    END DIM
    GEO
      ... per-layer geometry ...
    END GEO
    END

This module emits a working but minimal subset: the geometry block,
plus a few required metadata lines. Sonnet itself fills in defaults
for omitted sections.

Mirrors ``cmd_sonnet_emit`` (cases referencing the
``SONNETSAVE`` command).
"""

from __future__ import annotations

from collections.abc import Iterable
from io import StringIO
from pathlib import Path

from reasitic.geometry import Point, Polygon, Shape
from reasitic.tech import Tech


def write_sonnet(shapes: Iterable[Shape], tech: Tech) -> str:
    """Emit a minimal Sonnet ``.son`` string for ``shapes``."""
    out = StringIO()
    out.write("FTYP SONPROJ 16 ! Sonnet Project File\n")
    out.write("HEADER\n")
    out.write("BUILT_BY_AUTHOR reASITIC\n")
    out.write("END HEADER\n")
    out.write("DIM\n")
    out.write("FREQUENCY GHZ\n")
    out.write("INDUCTANCE NH\n")
    out.write("LENGTH UM\n")
    out.write("ANGLE DEG\n")
    out.write("CONDUCTIVITY SIEMENS/M\n")
    out.write("RESISTIVITY OHM CM\n")
    out.write("RESISTANCE OHM\n")
    out.write("CAPACITANCE PF\n")
    out.write("END DIM\n")
    out.write("GEO\n")
    out.write(f"BOX 1 {tech.chip.chipx:g} {tech.chip.chipy:g}\n")
    for sh in shapes:
        for p in sh.polygons:
            out.write(f"NUM {len(p.vertices)}\n")
            out.write(f"LAYER {p.metal}\n")
            for v in p.vertices:
                out.write(f"{v.x:g} {v.y:g}\n")
            out.write("END\n")
    out.write("END GEO\n")
    out.write("END\n")
    return out.getvalue()


def write_sonnet_file(path: str | Path, shapes: Iterable[Shape], tech: Tech) -> None:
    """Write the Sonnet rendering to ``path``."""
    Path(path).write_text(write_sonnet(shapes, tech))


# Reader -----------------------------------------------------------------


def read_sonnet(text: str, tech: Tech) -> list[Shape]:
    """Parse the GEO block of a Sonnet ``.son`` file into Shapes.

    Supports the subset emitted by :func:`write_sonnet`: ``NUM``
    polygon-size lines followed by ``LAYER`` and vertex coordinates,
    terminated by ``END``. Other Sonnet directives are skipped.
    Returns one Shape per file (combining all polygons).
    """
    shape = Shape(name="sonnet_imported")
    in_geo = False
    pending: list[tuple[float, float]] | None = None
    pending_layer = 0
    expected_n = 0

    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if line == "GEO":
            in_geo = True
            continue
        if line == "END GEO":
            in_geo = False
            continue
        if not in_geo:
            continue
        if line.startswith("NUM "):
            try:
                expected_n = int(line.split()[1])
            except (ValueError, IndexError):
                continue
            pending = []
            continue
        if line.startswith("LAYER "):
            try:
                pending_layer = int(line.split()[1])
            except (ValueError, IndexError):
                pending_layer = 0
            continue
        if line == "END":
            if pending is not None and len(pending) == expected_n:
                z = 0.0
                w = 0.0
                t = 0.0
                if 0 <= pending_layer < len(tech.metals):
                    m = tech.metals[pending_layer]
                    z = m.d + m.t * 0.5
                    w = 0.0
                    t = m.t
                shape.polygons.append(
                    Polygon(
                        vertices=[Point(x, y, z) for (x, y) in pending],
                        metal=pending_layer,
                        width=w,
                        thickness=t,
                    )
                )
            pending = None
            continue
        # Vertex line
        if pending is not None:
            parts = line.split()
            if len(parts) >= 2:
                import contextlib
                with contextlib.suppress(ValueError):
                    pending.append((float(parts[0]), float(parts[1])))

    return [shape]


def read_sonnet_file(path: str | Path, tech: Tech) -> list[Shape]:
    """Read a Sonnet ``.son`` file and parse the GEO block."""
    return read_sonnet(Path(path).read_text(), tech)
