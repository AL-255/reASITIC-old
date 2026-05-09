"""FastHenry input-file (``.inp``) writer.

FastHenry (Kamon, Tsuk, White, MIT 1994) is the de-facto open-source
inductance-extraction tool, taking a polygonal-conductor description
and producing the full 3-D inductance matrix at user-supplied
frequencies. Its ``.inp`` format is line-oriented::

    .units um
    .default sigma=...

    N1 x=... y=... z=...
    N2 x=... y=... z=...

    E1 N1 N2 w=... h=... sigma=...

    .external N1 N2

    .freq fmin=1e9 fmax=10e9 ndec=1

    .end

Lets users feed reASITIC's geometry into FastHenry for cross-
validation against an independent solver.
"""

from __future__ import annotations

from io import StringIO
from pathlib import Path

from reasitic.geometry import Shape
from reasitic.tech import Tech


def write_fasthenry(
    shape: Shape,
    tech: Tech,
    *,
    freqs_ghz: list[float] | None = None,
) -> str:
    """Render ``shape`` as a FastHenry ``.inp`` string.

    Each segment becomes one ``E`` element with two named nodes;
    consecutive segments share end nodes so the spiral forms a
    proper conductor chain.
    """
    out = StringIO()
    out.write("* reASITIC FastHenry input\n")
    out.write(".units um\n")
    out.write(".default x=0 y=0 z=0\n")

    segments = shape.segments()
    if not segments:
        out.write(".end\n")
        return out.getvalue()

    # Emit nodes: one per unique endpoint
    nodes: dict[tuple[float, float, float], str] = {}
    for s in segments:
        for v in (s.a, s.b):
            key = (v.x, v.y, v.z)
            if key not in nodes:
                nodes[key] = f"N{len(nodes) + 1}"
                out.write(
                    f"{nodes[key]} x={v.x:g} y={v.y:g} z={v.z:g}\n"
                )

    # Emit segments
    for i, s in enumerate(segments):
        n_a = nodes[(s.a.x, s.a.y, s.a.z)]
        n_b = nodes[(s.b.x, s.b.y, s.b.z)]
        if 0 <= s.metal < len(tech.metals):
            rsh = tech.metals[s.metal].rsh
            t_um = tech.metals[s.metal].t
            # Conductivity from rsh (Ω/sq) and t (μm): σ = 1/(rsh·t)
            sigma_si = (
                1.0 / (rsh * t_um * 1.0e-6) if rsh > 0 and t_um > 0 else 4e7
            )
        else:
            sigma_si = 4e7
        out.write(
            f"E{i + 1} {n_a} {n_b}"
            f" w={s.width:g} h={s.thickness:g} sigma={sigma_si:g}\n"
        )

    # External ports = first and last node
    first_node = nodes[(segments[0].a.x, segments[0].a.y, segments[0].a.z)]
    last_node = nodes[(segments[-1].b.x, segments[-1].b.y, segments[-1].b.z)]
    out.write(f".external {first_node} {last_node}\n")

    # Frequency directive
    if freqs_ghz:
        f_min = min(freqs_ghz) * 1.0e9
        f_max = max(freqs_ghz) * 1.0e9
        n_pts = max(1, len(freqs_ghz) - 1)
        out.write(f".freq fmin={f_min:g} fmax={f_max:g} ndec={n_pts}\n")
    out.write(".end\n")
    return out.getvalue()


def write_fasthenry_file(
    path: str | Path,
    shape: Shape,
    tech: Tech,
    *,
    freqs_ghz: list[float] | None = None,
) -> None:
    """Write the FastHenry rendering of ``shape`` to ``path``."""
    Path(path).write_text(write_fasthenry(shape, tech, freqs_ghz=freqs_ghz))
