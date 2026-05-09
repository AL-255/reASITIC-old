# Graphical interface

`reASITIC` ships with an optional desktop GUI that mirrors the
original ASITIC X11 front-end: a 2-D top-down layout view (pan,
zoom, chip outline, substrate grid, click-to-select) over an
embedded REPL pane that drives every one of the 117 binary commands.

```bash
reasitic-gui                                # empty workspace
reasitic-gui -t run/tek/BiCMOS.tek          # auto-load tech
reasitic-gui -s mysession.json              # auto-load saved session
python -m reasitic.gui                      # equivalent invocation
```

The GUI uses **Tkinter** (Python standard library) so no extra
runtime dependency is required on most platforms. On Linux you may
need the `python3-tk` system package; on macOS a built-in
ActiveState Tk is shipped with the python.org installers.

## Layout

```
┌──────────────────────────────────────────────────────────────┐
│  File  View  Help                              menu bar       │
├──────────────────────────────────────────────────────────────┤
│  [Fit] [Zoom +] [Zoom −] [Reset] [Grid] [Redraw]  toolbar     │
├──────────────────────────────────────────────────────────────┤
│                                                              │
│           Top-down layout view (pan / zoom)                  │
│           Tk Canvas — chip outline, grid, shapes             │
│                                                              │
├──────────────────────────────────────────────────────────────┤
│  reasitic> SQ NAME=L1:LEN=170:W=10:S=3:N=2:METAL=m3          │
│  reasitic> ...                                  console pane │
├──────────────────────────────────────────────────────────────┤
│  x= 100.5 μm   y= -75.0 μm   zoom=1.4 px/μm   selected=L1     │
└──────────────────────────────────────────────────────────────┘
```

## Mouse and keyboard

| Action                   | Effect                                                |
| ------------------------ | ------------------------------------------------------ |
| Drag (left mouse button) | Pan the view                                           |
| Scroll wheel             | Zoom in/out around the cursor                          |
| Click on a shape         | Select it (highlights its bounding box)                |
| `f`                      | Fit all shapes to the canvas                           |
| `g`                      | Toggle the substrate grid overlay                      |
| `r`                      | Force-redraw the layout                                |
| `Esc`                    | Clear the current selection                            |
| `Ctrl-Q`                 | Quit                                                   |
| `↑` / `↓` (in entry)     | Walk the command history                               |

## Console pane

Every line typed into the input row at the bottom is forwarded
verbatim to the embedded :class:`reasitic.cli.Repl`. Output from
the REPL is captured and printed into the scrollback above.

This means:

* Every CLI command works in the GUI, with identical syntax and output.
* After a `SQ` / `SP` / `LOAD` / `OPTSQ` command, the layout view
  automatically refreshes.
* `quit` / `exit` closes the GUI cleanly.

## Programmatic API

```python
from reasitic.gui import run

run(tech_path="run/tek/BiCMOS.tek")
```

Or for finer control:

```python
from reasitic.gui.app import GuiApp
from reasitic.cli import Repl

repl = Repl()
app = GuiApp(repl=repl)
app._run("load-tech run/tek/BiCMOS.tek")
app._run("SQ NAME=L1:LEN=170:W=10:S=3:N=2:METAL=m3")
app.action_fit()
app.mainloop()
```

## Testing without a display

The viewport math (`reasitic.gui.viewport.Viewport`) is decoupled
from Tk and fully unit-tested headlessly. The Tk-bound smoke tests
(`tests/gui/test_app_smoke.py`) probe for a usable display and
auto-skip when none is available, so they're CI-safe.
