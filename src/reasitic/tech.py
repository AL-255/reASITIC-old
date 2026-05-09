"""Parser for ASITIC technology files (``.tek``).

The file format is a free-form, line-oriented text format with four
section markers (``<chip>``, ``<layer>``, ``<metal>``, ``<via>``),
``key = value`` body lines, and ``;`` line comments. The original
parser lives in ``techfile_*`` functions of ``asitic_repl.c``; the
recognised key set was recovered from those functions plus the
sample tech files at ``run/tek/{BiCMOS,CMOS}.tek``.

Parser design notes:

* Sections are delimited by their opening token ``<name>``; sections
  may include a numeric *index* on the same line (``<layer> 0``) which
  is the position the entry occupies in the per-kind table.
* Keys are case-insensitive and matched ignoring whitespace. The
  value runs to end-of-line or the first ``;`` (line comment).
* Numeric values use Python's float parser. The ``rsh`` (sheet-
  resistance) field is in **mΩ/sq** in the file and gets converted
  to **Ω/sq** here.
* Unknown keys are accepted and stored in ``Section.extra`` so
  downstream code can distinguish "we don't model this yet" from
  "the file is malformed". The original treats unknown keys as a
  warning, not an error.
"""

from __future__ import annotations

import io
import os
import re
from dataclasses import dataclass, field
from pathlib import Path

from reasitic.units import MOHM_PER_SQ_TO_OHM

_SECTION_RE = re.compile(r"^<\s*([A-Za-z]+)\s*>(.*)$")
_KV_RE = re.compile(r"^\s*([A-Za-z][A-Za-z0-9_]*)\s*=\s*(.+?)\s*$")


@dataclass
class Chip:
    """Top-level ``<chip>`` section."""

    chipx: float = 0.0  # microns
    chipy: float = 0.0  # microns
    fftx: int = 0
    ffty: int = 0
    tech_file: str = ""
    tech_path: str = "."
    freq: float = 1.0  # GHz
    eddy: bool = False
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Layer:
    """One substrate ``<layer>`` (silicon, oxide, ...)."""

    index: int
    rho: float = 0.0  # Ω·cm
    t: float = 0.0  # microns
    eps: float = 1.0  # relative permittivity
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Metal:
    """One ``<metal>`` layer descriptor."""

    index: int
    layer: int = 0  # which substrate layer the metal sits in
    rsh: float = 0.0  # Ω/sq (converted from the file's mΩ/sq)
    t: float = 0.0  # microns
    d: float = 0.0  # microns from bottom of substrate layer
    name: str = ""
    color: str = "white"
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Via:
    """One ``<via>`` descriptor connecting two metal layers."""

    index: int
    top: int = 0  # metal index
    bottom: int = 0  # metal index
    r: float = 0.0  # Ω per unit-cell via
    width: float = 0.0  # microns
    space: float = 0.0  # microns
    overplot1: float = 0.0
    overplot2: float = 0.0
    name: str = ""
    color: str = "white"
    extra: dict[str, str] = field(default_factory=dict)


@dataclass
class Tech:
    """Complete tech-file contents."""

    chip: Chip
    layers: list[Layer]
    metals: list[Metal]
    vias: list[Via]

    def metal_by_name(self, name: str) -> Metal:
        """Look up a metal layer by its tech-file name. Raises KeyError."""
        for m in self.metals:
            if m.name == name:
                return m
        raise KeyError(f"no metal named {name!r}")

    def via_by_name(self, name: str) -> Via:
        """Look up a via descriptor by its tech-file name. Raises KeyError."""
        for v in self.vias:
            if v.name == name:
                return v
        raise KeyError(f"no via named {name!r}")


# Parser ----------------------------------------------------------------


class TechParseError(ValueError):
    """Raised when a ``.tek`` file is malformed."""


def parse_tech_file(path: str | os.PathLike[str]) -> Tech:
    """Parse a tech file at ``path`` and return a :class:`Tech` instance."""
    text = Path(path).read_text()
    return parse_tech(text)


def parse_tech(source: str | io.TextIOBase) -> Tech:
    """Parse a tech file from a string or text stream."""
    text = source.read() if hasattr(source, "read") else source

    chip = Chip()
    layers: list[Layer] = []
    metals: list[Metal] = []
    vias: list[Via] = []

    current_kind: str | None = None
    current_index: int | None = None
    current_extra: dict[str, str] = {}

    def commit() -> None:
        nonlocal current_extra
        if current_kind is None:
            return
        if current_kind == "chip":
            for k, v in current_extra.items():
                _apply_chip_kv(chip, k, v)
        elif current_kind == "layer":
            assert current_index is not None
            layers.append(_build_layer(current_index, current_extra))
        elif current_kind == "metal":
            assert current_index is not None
            metals.append(_build_metal(current_index, current_extra))
        elif current_kind == "via":
            assert current_index is not None
            vias.append(_build_via(current_index, current_extra))
        else:
            # unknown sections are silently dropped, matching the C parser
            pass
        current_extra = {}

    for raw_line in text.splitlines():
        line = _strip_comment(raw_line).strip()
        if not line:
            continue

        m = _SECTION_RE.match(line)
        if m:
            commit()
            kind = m.group(1).lower()
            tail = m.group(2).strip()
            current_kind = kind
            current_index = _parse_optional_int(tail) if tail else None
            current_extra = {}
            continue

        kv = _KV_RE.match(line)
        if not kv:
            # Some tech files put bare commentary; we tolerate it
            continue
        key = kv.group(1).lower()
        value = kv.group(2).strip()
        current_extra[key] = value

    commit()

    return Tech(chip=chip, layers=layers, metals=metals, vias=vias)


# Helpers ---------------------------------------------------------------


def _strip_comment(line: str) -> str:
    semi = line.find(";")
    return line if semi < 0 else line[:semi]


def _parse_optional_int(s: str) -> int | None:
    try:
        return int(s.split()[0])
    except (ValueError, IndexError):
        return None


def _as_float(s: str) -> float:
    return float(s)


def _as_bool(s: str) -> bool:
    s = s.strip().lower()
    if s in ("1", "true", "yes", "on"):
        return True
    if s in ("0", "false", "no", "off"):
        return False
    # Some tek files use bare numbers; non-zero means True
    try:
        return float(s) != 0.0
    except ValueError as e:
        raise TechParseError(f"cannot parse {s!r} as bool") from e


def _apply_chip_kv(chip: Chip, key: str, value: str) -> None:
    if key == "chipx":
        chip.chipx = _as_float(value)
    elif key == "chipy":
        chip.chipy = _as_float(value)
    elif key == "fftx":
        chip.fftx = int(_as_float(value))
    elif key == "ffty":
        chip.ffty = int(_as_float(value))
    elif key == "techfile":
        chip.tech_file = value
    elif key == "techpath":
        chip.tech_path = value
    elif key == "freq":
        chip.freq = _as_float(value)
    elif key == "eddy":
        chip.eddy = _as_bool(value)
    else:
        chip.extra[key] = value


def _build_layer(index: int, kv: dict[str, str]) -> Layer:
    layer = Layer(index=index)
    for k, v in kv.items():
        if k == "rho":
            layer.rho = _as_float(v)
        elif k == "t":
            layer.t = _as_float(v)
        elif k == "eps":
            layer.eps = _as_float(v)
        else:
            layer.extra[k] = v
    return layer


def _build_metal(index: int, kv: dict[str, str]) -> Metal:
    metal = Metal(index=index)
    for k, v in kv.items():
        if k == "layer":
            metal.layer = int(_as_float(v))
        elif k == "rsh":
            # tek file is mΩ/sq, internal is Ω/sq
            metal.rsh = _as_float(v) * MOHM_PER_SQ_TO_OHM
        elif k == "t":
            metal.t = _as_float(v)
        elif k == "d":
            metal.d = _as_float(v)
        elif k == "name":
            metal.name = v
        elif k == "color":
            metal.color = v
        else:
            metal.extra[k] = v
    return metal


def write_tech_file(tech: Tech, path: str | os.PathLike[str]) -> None:
    """Serialise a Tech object back to a ``.tek`` text file.

    The output format matches the parser: ``<chip>`` /``<layer>`` /
    ``<metal>`` / ``<via>`` sections with ``key = value`` body lines.
    Round-trips losslessly through :func:`parse_tech_file` for the
    canonical fields; ``extra`` dicts are preserved.
    """
    Path(path).write_text(write_tech(tech))


def write_tech(tech: Tech) -> str:
    """Render a Tech object as ``.tek``-format text."""
    lines: list[str] = []
    # Chip section
    lines.append("<chip>")
    chip = tech.chip
    if chip.chipx:
        lines.append(f"\tchipx = {_fmt(chip.chipx)}")
    if chip.chipy:
        lines.append(f"\tchipy = {_fmt(chip.chipy)}")
    if chip.fftx:
        lines.append(f"\tfftx = {chip.fftx}")
    if chip.ffty:
        lines.append(f"\tffty = {chip.ffty}")
    if chip.tech_file:
        lines.append(f"\tTechFile = {chip.tech_file}")
    if chip.tech_path and chip.tech_path != ".":
        lines.append(f"\tTechPath = {chip.tech_path}")
    if chip.freq:
        lines.append(f"\tfreq = {_fmt(chip.freq)}")
    lines.append(f"\teddy = {1 if chip.eddy else 0}")
    for k, v in chip.extra.items():
        lines.append(f"\t{k} = {v}")
    lines.append("")

    # Layers
    for layer in tech.layers:
        lines.append(f"<layer> {layer.index}")
        lines.append(f"\trho = {_fmt(layer.rho)}")
        lines.append(f"\tt = {_fmt(layer.t)}")
        lines.append(f"\teps = {_fmt(layer.eps)}")
        for k, v in layer.extra.items():
            lines.append(f"\t{k} = {v}")
        lines.append("")

    # Metals: convert rsh back to mΩ/sq
    for metal in tech.metals:
        lines.append(f"<metal> {metal.index}")
        lines.append(f"\tlayer = {metal.layer}")
        lines.append(f"\trsh = {_fmt(metal.rsh / MOHM_PER_SQ_TO_OHM)}")
        lines.append(f"\tt = {_fmt(metal.t)}")
        lines.append(f"\td = {_fmt(metal.d)}")
        if metal.name:
            lines.append(f"\tname = {metal.name}")
        if metal.color and metal.color != "white":
            lines.append(f"\tcolor = {metal.color}")
        for k, v in metal.extra.items():
            lines.append(f"\t{k} = {v}")
        lines.append("")

    # Vias
    for via in tech.vias:
        lines.append(f"<via> {via.index}")
        lines.append(f"\ttop = {via.top}")
        lines.append(f"\tbottom = {via.bottom}")
        lines.append(f"\tr = {_fmt(via.r)}")
        lines.append(f"\twidth = {_fmt(via.width)}")
        lines.append(f"\tspace = {_fmt(via.space)}")
        if via.overplot1:
            lines.append(f"\toverplot1 = {_fmt(via.overplot1)}")
        if via.overplot2:
            lines.append(f"\toverplot2 = {_fmt(via.overplot2)}")
        if via.name:
            lines.append(f"\tname = {via.name}")
        if via.color and via.color != "white":
            lines.append(f"\tcolor = {via.color}")
        for k, v in via.extra.items():
            lines.append(f"\t{k} = {v}")
        lines.append("")
    return "\n".join(lines)


def _fmt(value: float) -> str:
    """Format a float compactly (drop trailing zeros)."""
    if value == int(value):
        return str(int(value))
    return f"{value:g}"


def _build_via(index: int, kv: dict[str, str]) -> Via:
    via = Via(index=index)
    for k, v in kv.items():
        if k == "top":
            via.top = int(_as_float(v))
        elif k == "bottom":
            via.bottom = int(_as_float(v))
        elif k == "r":
            via.r = _as_float(v)
        elif k == "width":
            via.width = _as_float(v)
        elif k == "space":
            via.space = _as_float(v)
        elif k == "overplot1":
            via.overplot1 = _as_float(v)
        elif k == "overplot2":
            via.overplot2 = _as_float(v)
        elif k == "name":
            via.name = v
        elif k == "color":
            via.color = v
        else:
            via.extra[k] = v
    return via
