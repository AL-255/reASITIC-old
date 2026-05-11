# reASITIC

[![CI](https://github.com/AL-255/reASITIC/actions/workflows/ci.yml/badge.svg)](https://github.com/AL-255/reASITIC/actions/workflows/ci.yml)
[![Docs](https://github.com/AL-255/reASITIC/actions/workflows/docs.yml/badge.svg)](https://al-255.github.io/reASITIC/)
![Python](https://img.shields.io/badge/python-3.10%2B-blue)
![License](https://img.shields.io/badge/license-GPL--2.0-blue)

<!-- DOCS-INTRO -->
A clean-room Python re-implementation of [ASITIC][asitic] — the planar
RF inductor analysis tool originally developed at UC Berkeley by Ali
M. Niknejad in 1999. The library exposes geometry builders, partial-
inductance / Q / resistance / S-parameter / Pi-model analyses, and
CIF / GDS / Sonnet / SPICE / FastHenry / Touchstone exports.
<!-- /DOCS-INTRO -->

## Install

```bash
pip install reASITIC                 # base library (numpy + scipy)
pip install reASITIC[plot]           # + matplotlib
pip install -e ".[dev]"              # development install
```

## Example

```python
import reasitic

tech = reasitic.parse_tech_file("BiCMOS.tek")

sp = reasitic.square_spiral(
    "L1", length=170, width=10, spacing=3, turns=2,
    tech=tech, metal="m3",
)

L_nH = reasitic.compute_self_inductance(sp)
Q    = reasitic.metal_only_q(sp, tech, freq_ghz=2.0)
print(f"L = {L_nH:.3f} nH,  Q(2 GHz) = {Q:.1f}")
```

The same flow is available via the REPL CLI (`reasitic`), a Tk
workspace (`reasitic-gui`), and an in-browser Pyodide REPL bundled
into the docs site.

## Documentation

Full HTML docs (tutorial, cookbook, API reference, CLI reference,
C ↔ Python mapping) live at **<https://al-255.github.io/reASITIC/>**
and rebuild from `docs/` on every push to `main`.

## License

GPL-2.0-only. See [LICENSE](LICENSE).

[asitic]: https://rfic.eecs.berkeley.edu/~niknejad/asitic.html
