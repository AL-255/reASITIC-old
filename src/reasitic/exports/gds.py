"""GDSII layout export via :mod:`gdstk`.

GDSII is the de-facto standard EDA tape-out format, and modern
foundry / PDK toolchains expect designs to ship as ``.gds`` /
``.gdsii`` files. The original ASITIC binary did not write GDSII —
its only "tape-out" path was CIF — so this module is a clean
addition rather than a port. The GDS layer numbering follows the
common convention: each metal index maps to a GDS layer with
``datatype = 0``; vias get a separate ``datatype = 1`` band so
they can be filtered out cleanly with the standard GDS layer-map
tools.

Round-trip is supported: :func:`read_gds` reconstructs Python
:class:`~reasitic.geometry.Shape` objects from a GDS file written
by :func:`write_gds_file` (or any GDS that uses the same layer
convention).

Optional dependency: ``gdstk >= 1.0``. Install with
``pip install reASITIC[gds]``.
"""

from __future__ import annotations

import os
from collections.abc import Iterable

from reasitic.geometry import Point, Polygon, Shape, layout_polygons
from reasitic.tech import Tech

try:
    import gdstk
    _HAS_GDSTK = True
except ImportError:  # pragma: no cover
    gdstk = None  # type: ignore[assignment]
    _HAS_GDSTK = False


def _require_gdstk() -> None:
    if not _HAS_GDSTK:  # pragma: no cover
        raise ImportError(
            "gdstk is required for GDSII import/export — "
            "install with `pip install reASITIC[gds]`"
        )


# Layer-numbering convention: GDS layer = metal index, datatype = 0.
# Vias use datatype = 1 to separate them from metal polygons.
_VIA_DATATYPE = 1


def _shape_polygon_to_gdstk(
    poly: Polygon, x_origin: float, y_origin: float,
) -> gdstk.Polygon:
    pts = [(v.x + x_origin, v.y + y_origin) for v in poly.vertices]
    # gdstk expects closed polygons; if first != last, gdstk closes it
    return gdstk.Polygon(
        pts,
        layer=poly.metal,
        datatype=0,
    )


def write_gds(
    shapes: Iterable[Shape],
    tech: Tech | None = None,
    *,
    unit: float = 1e-6,        # 1 μm
    precision: float = 1e-9,   # 1 nm
    library_name: str = "REASITIC",
) -> bytes:
    """Serialise ``shapes`` to a GDSII byte stream.

    Each :class:`~reasitic.geometry.Shape` becomes one GDS cell. Open
    polylines are widened to ``poly.width`` μm using gdstk's path
    rendering before being baked into closed polygons.

    Args:
        shapes:        Iterable of :class:`Shape` objects.
        unit:          GDSII user unit, in metres (default 1 μm).
        precision:     GDSII database precision, in metres (default 1 nm).
        library_name:  Top-level library name to write into the file.

    Returns:
        The raw GDSII byte stream.
    """
    _require_gdstk()
    import tempfile
    lib = _build_gds_library(shapes, tech=tech, unit=unit, precision=precision,
                             library_name=library_name)
    with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
        tmp_path = f.name
    try:
        lib.write_gds(tmp_path)
        with open(tmp_path, "rb") as fr:
            return fr.read()
    finally:
        os.unlink(tmp_path)


def write_gds_file(
    path: str | os.PathLike[str],
    shapes: Iterable[Shape],
    tech: Tech | None = None,
    *,
    unit: float = 1e-6,
    precision: float = 1e-9,
    library_name: str = "REASITIC",
) -> None:
    """Write ``shapes`` as a ``.gds`` file at ``path``.

    See :func:`write_gds` for details on parameters.
    """
    _require_gdstk()
    lib = _build_gds_library(shapes, tech=tech, unit=unit, precision=precision,
                             library_name=library_name)
    lib.write_gds(os.fspath(path))


def _build_gds_library(
    shapes: Iterable[Shape],
    *,
    tech: Tech | None = None,
    unit: float,
    precision: float,
    library_name: str,
) -> gdstk.Library:
    """Construct a :class:`gdstk.Library` from a sequence of shapes."""
    lib = gdstk.Library(name=library_name, unit=unit, precision=precision)
    for shape in shapes:
        cell = gdstk.Cell(shape.name or "UNNAMED")
        use_layout = tech is not None
        polys = layout_polygons(shape, tech) if use_layout else shape.polygons
        x0 = 0.0 if use_layout else shape.x_origin
        y0 = 0.0 if use_layout else shape.y_origin
        for poly in polys:
            if len(poly.vertices) < 2:
                continue
            if _is_closed(poly):
                cell.add(_shape_polygon_to_gdstk(
                    poly, x0, y0
                ))
            else:
                pts = [
                    (v.x + x0, v.y + y0)
                    for v in poly.vertices
                ]
                w = poly.width if poly.width > 0 else 1.0
                path = gdstk.FlexPath(
                    pts, w, layer=poly.metal, datatype=0,
                    ends="flush",
                )
                cell.add(path)
        lib.add(cell)
    return lib


def _is_closed(poly: Polygon) -> bool:
    if len(poly.vertices) < 3:
        return False
    a, b = poly.vertices[0], poly.vertices[-1]
    return abs(a.x - b.x) < 1e-9 and abs(a.y - b.y) < 1e-9


# ----- Read path --------------------------------------------------------


def read_gds(
    data: bytes,
    tech: Tech | None = None,
) -> list[Shape]:
    """Parse a GDSII byte stream back into :class:`Shape` objects.

    Each top-level GDS cell becomes one :class:`Shape`; the GDS
    layer number is taken as the metal index. ``tech`` is optional —
    if provided, the metal-layer thickness is filled in on each
    polygon.

    Path elements (open polylines) are recovered as filled polygons
    matching whatever GDS represented, since GDSII does not preserve
    the source's path-vs-polygon distinction across a round-trip.
    """
    _require_gdstk()
    import tempfile
    with tempfile.NamedTemporaryFile(suffix=".gds", delete=False) as f:
        f.write(data)
        tmp_path = f.name
    try:
        lib = gdstk.read_gds(tmp_path)
    finally:
        os.unlink(tmp_path)
    return _library_to_shapes(lib, tech)


def read_gds_file(
    path: str | os.PathLike[str],
    tech: Tech | None = None,
) -> list[Shape]:
    """Read a GDSII file from disk.

    See :func:`read_gds` for the conversion details.
    """
    _require_gdstk()
    lib = gdstk.read_gds(os.fspath(path))
    return _library_to_shapes(lib, tech)


def _library_to_shapes(
    lib: gdstk.Library, tech: Tech | None,
) -> list[Shape]:
    shapes: list[Shape] = []
    for cell in lib.cells:
        # gdstk.Library.cells is a heterogeneous list of Cell and
        # RawCell; only Cell exposes .polygons / .paths.
        if not isinstance(cell, gdstk.Cell):
            continue
        polygons: list[Polygon] = []
        # gdstk Polygon objects
        for gpoly in cell.polygons:
            metal_idx = int(gpoly.layer)
            thickness = 0.0
            if tech is not None and 0 <= metal_idx < len(tech.metals):
                thickness = tech.metals[metal_idx].t
            verts = [Point(float(x), float(y), 0.0)
                     for (x, y) in gpoly.points]
            # Close the loop if needed
            if (verts and (
                abs(verts[0].x - verts[-1].x) > 1e-9
                or abs(verts[0].y - verts[-1].y) > 1e-9
            )):
                verts.append(verts[0])
            polygons.append(Polygon(
                vertices=verts,
                metal=metal_idx,
                width=0.0,
                thickness=thickness,
            ))
        # gdstk Path / FlexPath / RobustPath: convert to polygons
        for gpath in getattr(cell, "paths", ()):
            for poly_pts in gpath.to_polygons():
                metal_idx = int(getattr(gpath, "layers", [0])[0])
                thickness = 0.0
                if tech is not None and 0 <= metal_idx < len(tech.metals):
                    thickness = tech.metals[metal_idx].t
                verts = [Point(float(x), float(y), 0.0)
                         for (x, y) in poly_pts]
                if (verts and (
                    abs(verts[0].x - verts[-1].x) > 1e-9
                    or abs(verts[0].y - verts[-1].y) > 1e-9
                )):
                    verts.append(verts[0])
                polygons.append(Polygon(
                    vertices=verts,
                    metal=metal_idx,
                    width=0.0,
                    thickness=thickness,
                ))
        shapes.append(Shape(name=cell.name, polygons=polygons))
    return shapes
