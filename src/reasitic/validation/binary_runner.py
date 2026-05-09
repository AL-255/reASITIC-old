"""Drive the original 1999 ASITIC binary headlessly and parse its
output, so reASITIC's numerical results can be compared to the
ground truth.

The binary lives at ``../run/asitic.linux.2.2`` (relative to the
reASITIC source tree). It is a 32-bit ELF that depends on the
bundled libstdc++/Mesa/X11/readline shipped under ``../run/libs/``;
running it requires a working X display (the binary ``--ngr``
flag does not fully bypass the X init). We use ``xvfb-run`` to
provide a virtual display when one isn't already available.

Notes on the legacy binary's quirks:

* The ``Ind`` / inductance commands segfault in headless mode on
  modern Linux (uninitialized table read at ``-4`` offset, traced
  to ``cmd_inductance_compute`` reading ``g_metal_layer_table``
  before it has been fully populated). We therefore validate
  numerical results against published Greenhouse / Grover formulas
  rather than against the binary's ``Ind`` output. Geometry-only
  commands (``Geom``, ``MetArea``, ``ListSegs``, etc.) work and
  are the basis of binary-driven testing here.
* When stdin closes the binary loops forever printing
  ``Unknown or Mistyped Commnd``; therefore every script must end
  with a quit command (``Q`` / ``QUIT`` / ``EXIT``).
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import textwrap
from dataclasses import dataclass
from pathlib import Path


class BinaryNotFoundError(RuntimeError):
    """Raised when the legacy ``asitic`` binary cannot be located."""


def _default_binary_path() -> Path:
    """Locate the legacy binary relative to the package tree."""
    # reasitic/validation/binary_runner.py → repo root is 4 levels up
    here = Path(__file__).resolve()
    for parent in here.parents:
        candidate = parent / "run" / "asitic"
        if candidate.exists():
            return candidate
    # Allow override
    env = os.environ.get("REASITIC_BINARY")
    if env and Path(env).exists():
        return Path(env)
    raise BinaryNotFoundError("could not locate run/asitic launcher")


@dataclass
class GeomResult:
    """Parsed output of the ``Geom <name>`` command."""

    name: str
    kind: str  # "Wire", "Square spiral", "Spiral", ...
    length_um: float | None = None  # for Wire, the length; for spirals, L1
    width_um: float | None = None
    metal: str | None = None
    total_length_um: float | None = None
    total_area_um2: float | None = None
    location: tuple[float, float] | None = None
    n_segments: int | None = None
    spiral_l1_um: float | None = None
    spiral_l2_um: float | None = None
    spiral_spacing_um: float | None = None
    spiral_turns: float | None = None
    raw: str = ""


_GEOM_HEADER_RE = re.compile(r"^(.+?)\s+<([^>]+)>\s+has the following geometry")
_LW_RE = re.compile(r"L\s*=\s*([0-9.]+)\s*,\s*W\s*=\s*([0-9.]+)\s*,\s*Metal\s*=\s*(\S+)")
_TOTAL_RE = re.compile(
    r"Total length\s*=\s*([0-9.]+)\s*\(um\),\s*Total Area\s*=\s*([0-9.]+)"
)
_LOC_RE = re.compile(
    r"Located at\s*\(\s*(-?[0-9.]+)\s*,\s*(-?[0-9.]+)\s*\) with\s+(\d+)\s+segments"
)
_SPIRAL_PARAMS_RE = re.compile(
    r"L1\s*=\s*([0-9.]+)\s*,\s*L2\s*=\s*([0-9.]+)\s*,\s*W\s*=\s*([0-9.]+)"
    r"\s*,\s*S\s*=\s*([0-9.]+)\s*,\s*N\s*=\s*([0-9.]+)"
)


def parse_geom_output(text: str) -> GeomResult:
    """Parse the textual block emitted by ``Geom <name>``."""
    result = GeomResult(name="", kind="", raw=text)
    for line in text.splitlines():
        m = _GEOM_HEADER_RE.search(line)
        if m:
            result.kind = m.group(1)
            result.name = m.group(2)
            continue
        m = _LW_RE.search(line)
        if m:
            result.length_um = float(m.group(1))
            result.width_um = float(m.group(2))
            result.metal = m.group(3)
            continue
        m = _TOTAL_RE.search(line)
        if m:
            result.total_length_um = float(m.group(1))
            result.total_area_um2 = float(m.group(2))
            continue
        m = _LOC_RE.search(line)
        if m:
            result.location = (float(m.group(1)), float(m.group(2)))
            result.n_segments = int(m.group(3))
            continue
        m = _SPIRAL_PARAMS_RE.search(line)
        if m:
            result.spiral_l1_um = float(m.group(1))
            result.spiral_l2_um = float(m.group(2))
            result.width_um = float(m.group(3))
            result.spiral_spacing_um = float(m.group(4))
            result.spiral_turns = float(m.group(5))
    return result


@dataclass
class BinaryRunner:
    """Runs the legacy ``asitic`` binary against a script."""

    binary: Path
    tech_file: Path
    cwd: Path
    timeout_s: float = 30.0
    use_xvfb: bool = True

    @classmethod
    def auto(
        cls,
        tech_file: str | Path = "tek/BiCMOS.tek",
        timeout_s: float = 30.0,
    ) -> BinaryRunner:
        """Construct a runner using the legacy binary at ``run/asitic``.

        ``tech_file`` is resolved relative to the binary's directory if
        not absolute. ``xvfb-run`` is auto-enabled when no DISPLAY is
        set on the host.
        """
        binary = _default_binary_path()
        cwd = binary.parent  # the run/ directory
        tech = Path(tech_file)
        if not tech.is_absolute():
            tech = cwd / tech
        if not tech.exists():
            raise FileNotFoundError(tech)
        use_xvfb = (
            shutil.which("xvfb-run") is not None
            and "DISPLAY" not in os.environ
        )
        return cls(binary=binary, tech_file=tech, cwd=cwd, timeout_s=timeout_s, use_xvfb=use_xvfb)

    def run_script(self, script: str) -> str:
        """Run ``script`` (newline-separated commands) and return stdout."""
        if not script.endswith("\n"):
            script += "\n"
        # `Q` is the Q-factor command, not quit. Always end with EXIT
        # so the binary leaves the prompt loop cleanly.
        if "QUIT\n" not in script.upper() and "EXIT\n" not in script.upper():
            script += "EXIT\n"

        argv: list[str] = []
        if self.use_xvfb:
            argv.extend(["xvfb-run", "-a"])
        argv.extend([str(self.binary), "-t", str(self.tech_file)])

        # start_new_session=True isolates us from the SIGQUIT that
        # xvfb-run sends to its process group when the legacy
        # libstdc++ runtime tears down the X connection on exit.
        proc = subprocess.run(
            argv,
            input=script,
            text=True,
            capture_output=True,
            cwd=str(self.cwd),
            timeout=self.timeout_s,
            check=False,
            start_new_session=True,
        )
        # The binary prints results inline on stdout. Note: Ind crashes,
        # but Geom and other geometry commands work.
        return proc.stdout

    def geom(self, build_command: str, name: str) -> GeomResult:
        """Build ``name`` via ``build_command`` then run ``Geom <name>``.

        Example::

            r = runner.geom(
                "W NAME=W1:LEN=100:WID=10:METAL=m3:XORG=0:YORG=0",
                "W1",
            )
            assert r.length_um == 100.0
        """
        script = textwrap.dedent(
            f"""\
            {build_command}
            Geom {name}
            """
        )
        out = self.run_script(script)
        # Carve out just the lines after "Geom <name>"
        marker = f"Geom {name}"
        idx = out.find(marker)
        if idx < 0:
            return parse_geom_output(out)
        return parse_geom_output(out[idx:])
