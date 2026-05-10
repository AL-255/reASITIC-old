# In-browser REPL

The published documentation site ships a **fully in-browser version of
reASITIC** — Python, NumPy, SciPy and the `reasitic` wheel all run via
[Pyodide](https://pyodide.org/) inside your tab, no install required.

```{raw} html
<p style="font-size: 1.05rem;">
  <a href="repl/index.html" target="_blank" rel="noopener"
     style="display:inline-block;padding:0.55rem 0.95rem;border-radius:6px;
            background:#0a7;color:#fff;text-decoration:none;font-weight:600;">
    🚀 Launch the REPL
  </a>
</p>
```

(If you're reading this on GitHub the link above points to the
deployed site at <https://AL-255.github.io/reASITIC/repl/>.)

## What you can do

- Pick a tech file (`BiCMOS.tek` or `CMOS.tek`) and one of the **13
  geometry primitives** ASITIC supports:

  | Section | Commands |
  |---|---|
  | Single-trace primitives | Wire, Capacitor, Ring, Via |
  | Single-port spirals | Square (SQ), Polygon (SP), Multi-metal square (SQMM) |
  | Centre-tapped | Symmetric square (SYMSQ), Symmetric polygon (SYMPOLY) |
  | Two-coil | Transformer (TRANS) primary + secondary, Balun primary + secondary |

- Adjust the per-shape parameters (LEN / RADIUS / W / S / N / ILEN / SIDES /
  ORIENT / PHASE / EXIT metal …). The layout updates live.

- Run the analysis routines:
  - **L · R · Q** at the chosen frequency
  - **Pi-model** extraction
  - **S-parameter sweep** with self-resonance estimate
  - **.s2p / SPICE** export buttons download the result
  - **Geom info** dumps the polygon set

- Open the **Python REPL** tab to script against the live `shape` and
  `tech` objects:

  ```python
  import reasitic
  print(reasitic.summary())
  print("L =", round(reasitic.compute_self_inductance(shape), 4), "nH")
  ```

## CIF parity

Every shape in the REPL renders the **exact same vertices** the original
1999 ASITIC binary writes to its CIF / GDS output — verified by 91
vertex-for-vertex regression tests against the C-binary's golden CIFs.
What you see in the canvas is the layout the binary would emit.

## How it works

The REPL is a static page with three pieces:

1. **Pyodide** is fetched from the official CDN on first load (~30 MB,
   cached thereafter).
2. The `reasitic` wheel and a small bridge (`bridge.py`) are loaded from
   the same directory (deployed at `repl/wheels/` and `repl/bridge.py`).
3. The UI (`app.js`, `draw.js`) calls into the bridge for `build_shape`,
   `analyze_*` and `export_*` and renders the polygons as SVG.

Nothing is sent off your machine after the initial Pyodide download.
Everything — geometry, inductance, Pi-model, SPICE — runs in your browser.

## Running the REPL locally

```bash
cd docs/repl
python -m http.server 8000
# then open http://localhost:8000/ in your browser
```

(A plain `file://` URL won't work because Pyodide / the wheel install
need a real HTTP server for `fetch()`.)
