# reASITIC examples

Runnable scripts demonstrating the library's main use cases. Each
example uses the BiCMOS technology file at ``../run/tek/BiCMOS.tek``
and works without ``pip install`` (it puts ``src/`` on ``sys.path``).

| Script | What it shows |
|--------|---------------|
| [01_single_spiral.py](./01_single_spiral.py) | Single-spiral L/R/Q/Pi analysis at one frequency |
| [02_freq_sweep_s2p.py](./02_freq_sweep_s2p.py) | Frequency sweep + Touchstone S2P export |
| [03_optimise.py](./03_optimise.py) | OptSq / OptArea / OptSymSq for the same target |
| [04_transformer.py](./04_transformer.py) | CalcTrans: coupled-spiral analysis (M, k, n) |
| [05_design_report.py](./05_design_report.py) | Multi-frequency `design_report` aggregator |
| [06_jupyter_demo.ipynb](./06_jupyter_demo.ipynb) | Notebook with inline plots (needs `pip install reASITIC[plot]`) |

Run any of them with::

    python examples/01_single_spiral.py
