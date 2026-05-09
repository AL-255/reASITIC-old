"""CIF (Caltech Intermediate Format) exporter.

CIF is a 1970s-era ASCII layout format still in use as the lingua
franca for academic IC tooling and as a Sonnet/Mosis input. The
binary's ``CIFSAVE`` command (case 300) emits this format.

The format is line-oriented with semicolon terminators::

    DS 1 1 1;             // start a symbol, scale=1/1
    L NM3;                // switch to layer NM3
    B 100 50 0 0;         // box of width 100, height 50, centred at (0,0)
    P 0 0 100 0 100 50 0 50 0 0;   // polygon path
    DF;                   // end symbol
    C 1;                  // call symbol 1
    E                     // end of file

We use the polygon ``P`` form because it preserves arbitrary spiral
geometry. Each metal layer becomes a separate ``L`` directive named
after the metal in the tech file (uppercased, prefixed with ``N``).

Coordinates default to centi-microns (1 unit = 0.01 μm), matching
the convention most downstream tools expect.
"""

from __future__ import annotations

from collections.abc import Iterable
from io import StringIO
from pathlib import Path

from reasitic.geometry import Shape
from reasitic.tech import Tech

_CENTI_UM_PER_UM = 100  # 1 unit in CIF = 0.01 μm


def write_cif(
    shapes: Iterable[Shape],
    tech: Tech,
    *,
    symbol_id: int = 1,
    scale_a: int = 1,
    scale_b: int = 1,
    units_per_um: float = _CENTI_UM_PER_UM,
) -> str:
    """Render ``shapes`` to a CIF string."""
    out = StringIO()
    out.write(f"DS {symbol_id} {scale_a} {scale_b};\n")
    last_layer: str | None = None
    for sh in shapes:
        for p in sh.polygons:
            metal_idx = p.metal
            if 0 <= metal_idx < len(tech.metals):
                layer_name = "N" + tech.metals[metal_idx].name.upper()
            else:
                layer_name = f"NL{metal_idx}"
            if layer_name != last_layer:
                out.write(f"L {layer_name};\n")
                last_layer = layer_name
            coords = " ".join(
                f"{round(v.x * units_per_um)} {round(v.y * units_per_um)}"
                for v in p.vertices
            )
            out.write(f"P {coords};\n")
    out.write("DF;\n")
    out.write(f"C {symbol_id};\n")
    out.write("E\n")
    return out.getvalue()


def write_cif_file(
    path: str | Path,
    shapes: Iterable[Shape],
    tech: Tech,
    **kwargs: object,
) -> None:
    """Write the CIF rendering of ``shapes`` to ``path``."""
    text = write_cif(shapes, tech, **kwargs)  # type: ignore[arg-type]
    Path(path).write_text(text)


# Reader ------------------------------------------------------------------


def read_cif(
    text: str,
    tech: Tech,
    *,
    units_per_um: float = _CENTI_UM_PER_UM,
) -> list[Shape]:
    """Parse a CIF string back into reasitic Shapes.

    Supports the subset emitted by :func:`write_cif`: ``DS`` symbol
    open, ``L <name>`` layer switch, ``P <coords>`` polygon, ``DF``
    symbol close, ``C <id>`` symbol call, ``E`` end of file. All
    other CIF directives are silently skipped.

    The polygon's metal layer is resolved from the L name by
    matching against the tech file's metal names (case-insensitive,
    with a leading ``N`` stripped). Unknown layers fall back to
    metal 0.
    """
    from reasitic.geometry import Point, Polygon, Shape

    shape = Shape(name="cif_imported")
    metal_idx = 0
    in_symbol = False

    for raw in text.split(";"):
        line = raw.strip()
        if not line or line == "E":
            continue
        if line.startswith("DS"):
            in_symbol = True
            continue
        if line.startswith("DF"):
            in_symbol = False
            continue
        if line.startswith("C "):
            continue
        if not in_symbol:
            continue
        if line.startswith("L "):
            layer_name = line[2:].strip()
            # Strip leading N if present
            if layer_name.startswith("N"):
                layer_name = layer_name[1:]
            metal_idx = 0
            for i, m in enumerate(tech.metals):
                if m.name.upper() == layer_name.upper():
                    metal_idx = i
                    break
            continue
        if line.startswith("P "):
            tokens = line[2:].split()
            if len(tokens) % 2 != 0:
                continue
            coords = [int(t) for t in tokens]
            verts = [
                Point(coords[i] / units_per_um, coords[i + 1] / units_per_um, 0.0)
                for i in range(0, len(coords), 2)
            ]
            if metal_idx < len(tech.metals):
                m = tech.metals[metal_idx]
                w = m.t  # placeholder; CIF doesn't store conductor width
                t = m.t
                # Reset Z to the metal layer height
                z = m.d + m.t * 0.5
                verts = [Point(v.x, v.y, z) for v in verts]
            else:
                w = 0.0
                t = 0.0
            shape.polygons.append(
                Polygon(vertices=verts, metal=metal_idx, width=w, thickness=t)
            )
            continue

    return [shape]


def read_cif_file(path: str | Path, tech: Tech, **kwargs: object) -> list[Shape]:
    """Read a CIF file and parse into Shapes."""
    return read_cif(Path(path).read_text(), tech, **kwargs)  # type: ignore[arg-type]
