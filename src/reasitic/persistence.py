"""Save/Load round-trip for Tech and Shape collections.

Replaces the binary's ``BSAVE`` / ``BLOAD`` / ``SAVE`` / ``LOAD`` /
``CAT`` / ``BCAT`` commands using a portable JSON format that round-
trips losslessly through Python.

Schema (top-level keys are optional, all others must be present):

::

    {
      "version": 1,
      "tech": { ... },          // Tech, schema below
      "shapes": [ ... ]         // list of Shape dicts
    }

The Tech and Shape sub-schemas are derived directly from their
dataclass fields. The serializer drops empty ``extra`` dicts to keep
files readable.
"""

from __future__ import annotations

import json
from dataclasses import asdict
from pathlib import Path
from typing import Any

from reasitic.geometry import Point, Polygon, Shape
from reasitic.tech import Chip, Layer, Metal, Tech, Via

_FORMAT_VERSION = 1


def shape_to_dict(shape: Shape) -> dict[str, Any]:
    """Serialize a :class:`Shape` to a JSON-friendly dict."""
    return {
        "name": shape.name,
        "polygons": [
            {
                "vertices": [[v.x, v.y, v.z] for v in p.vertices],
                "metal": p.metal,
                "width": p.width,
                "thickness": p.thickness,
            }
            for p in shape.polygons
        ],
        "width": shape.width,
        "spacing": shape.spacing,
        "turns": shape.turns,
        "sides": shape.sides,
        "metal": shape.metal,
        "exit_metal": shape.exit_metal,
        "x_origin": shape.x_origin,
        "y_origin": shape.y_origin,
        "orientation": shape.orientation,
        "phase": shape.phase,
    }


def shape_from_dict(d: dict[str, Any]) -> Shape:
    """Inverse of :func:`shape_to_dict`."""
    return Shape(
        name=d["name"],
        polygons=[
            Polygon(
                vertices=[Point(*v) for v in p["vertices"]],
                metal=p["metal"],
                width=p.get("width", 0.0),
                thickness=p.get("thickness", 0.0),
            )
            for p in d["polygons"]
        ],
        width=d.get("width", 0.0),
        spacing=d.get("spacing", 0.0),
        turns=d.get("turns", 0.0),
        sides=d.get("sides", 4),
        metal=d.get("metal", 0),
        exit_metal=d.get("exit_metal"),
        x_origin=d.get("x_origin", 0.0),
        y_origin=d.get("y_origin", 0.0),
        orientation=d.get("orientation", 0),
        phase=d.get("phase", 0.0),
    )


def tech_to_dict(tech: Tech) -> dict[str, Any]:
    """Serialise a :class:`Tech` to a JSON-friendly dict."""
    return {
        "chip": _drop_empty_extra(asdict(tech.chip)),
        "layers": [_drop_empty_extra(asdict(layer)) for layer in tech.layers],
        "metals": [_drop_empty_extra(asdict(m)) for m in tech.metals],
        "vias": [_drop_empty_extra(asdict(v)) for v in tech.vias],
    }


def tech_from_dict(d: dict[str, Any]) -> Tech:
    """Inverse of :func:`tech_to_dict`."""
    return Tech(
        chip=Chip(**d["chip"]),
        layers=[Layer(**layer) for layer in d.get("layers", [])],
        metals=[Metal(**m) for m in d.get("metals", [])],
        vias=[Via(**v) for v in d.get("vias", [])],
    )


def save_session(
    path: str | Path,
    *,
    tech: Tech | None = None,
    shapes: dict[str, Shape] | None = None,
    viewport: dict[str, float] | None = None,
) -> None:
    """Save a session (tech + named shapes + optional viewport) to JSON."""
    payload: dict[str, Any] = {"version": _FORMAT_VERSION}
    if tech is not None:
        payload["tech"] = tech_to_dict(tech)
    if shapes:
        payload["shapes"] = [shape_to_dict(s) for s in shapes.values()]
    if viewport:
        payload["viewport"] = viewport
    Path(path).write_text(json.dumps(payload, indent=2))


def load_session(
    path: str | Path,
) -> tuple[Tech | None, dict[str, Shape]]:
    """Load a session JSON file. Returns ``(tech, shapes_by_name)``.

    Use :func:`load_viewport` to also read the optional viewport block.
    """
    payload = json.loads(Path(path).read_text())
    if payload.get("version", 0) > _FORMAT_VERSION:
        raise ValueError(
            f"file format version {payload['version']} is newer than "
            f"this build supports ({_FORMAT_VERSION})"
        )
    tech = tech_from_dict(payload["tech"]) if "tech" in payload else None
    shapes_list = [shape_from_dict(d) for d in payload.get("shapes", [])]
    shapes = {s.name: s for s in shapes_list}
    return tech, shapes


def load_viewport(path: str | Path) -> dict[str, float]:
    """Read the optional ``viewport`` block from a session file.

    Returns an empty dict if no viewport is recorded (older files).
    """
    payload = json.loads(Path(path).read_text())
    return payload.get("viewport", {}) or {}


def _drop_empty_extra(d: dict[str, Any]) -> dict[str, Any]:
    """Strip ``extra={}`` entries from dataclass dicts to keep JSON tidy."""
    if "extra" in d and not d["extra"]:
        d = dict(d)
        del d["extra"]
    return d
