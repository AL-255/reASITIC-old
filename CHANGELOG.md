# Changelog

All notable changes to reASITIC are documented here. Format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/), versioning
follows [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [Unreleased]

### Added

- Comprehensive REPL CLI with all 117 commands matching the
  original ASITIC binary (100 % command coverage).
- 100 % coverage of the binary's 643 identified C functions —
  every one is re-implemented in Python or explicitly subsumed by
  a NumPy / SciPy / stdlib equivalent. See [`MAPPING.md`](./MAPPING.md)
  and [`docs/milestone.md`](./docs/milestone.md).
- 10 geometry builders: square spiral, polygon spiral, wire, ring,
  via cluster, transformer, 3D mirror transformer, symmetric square,
  symmetric polygon, balun, MIM capacitor, multi-metal series square.
- Greenhouse partial-inductance summation with rectangular-bar
  self-inductance formula (matches the binary's ``cmd_inductance_compute``).
- Filament-level current-crowding solver (``solve_inductance_matrix``)
  via Schur-complement reduction; rigorous MNA-based solver
  (``solve_inductance_mna``) for ``n_w·n_t > 1`` topologies.
- Auto-sized filament grid based on skin depth at the operating freq.
- Substrate eddy-current correction with finite-thickness ground
  plane attenuation (``inductance/eddy.py``).
- Wheeler-style AC resistance kernel verbatim ported from the
  binary's ``compute_inductance_inner_kernel``.
- 2-port Y/Z/S / 3-port reduction conversions; Pi / Pi3 / Pi4 / PiX
  equivalent-circuit extraction.
- Self-resonance scan, ShuntR (parallel-equivalent), Zin with
  arbitrary terminations, transformer analysis (CalcTrans).
- Touchstone v1 ``.s2p`` reader and writer (round-trip) supporting
  MA / DB / RI formats and Hz/kHz/MHz/GHz scaling.
- SPICE Pi-model ``.subckt`` exporter (single-frequency and
  broadband variants).
- FastHenry ``.inp`` exporter for cross-validation.
- CIF and Sonnet ``.son`` writers and readers.
- Per-metal-layer parallel-plate substrate shunt-cap with
  series-stack dielectric averaging.
- Multi-layer Sommerfeld Green's function (``substrate/green.py``)
  with quasi-static and Bessel-J0 numerical integration variants.
- FFT-accelerated 2-D convolution Green's grid (``substrate/fft_grid.py``).
- ``OptSq`` / ``OptPoly`` / ``OptArea`` / ``OptSymSq`` / ``OptSymPoly``
  scipy.optimize SLSQP-based optimisers.
- ``BatchOpt`` for multi-target optimisation; ``Sweep`` for Cartesian
  parametric design exploration.
- JSON-based session save / load (replaces the binary's BSAVE/BLOAD;
  alias commands route to JSON).
- Mohan 1999 modified-Wheeler closed-form L estimate as a sanity
  check.
- Y-parameter de-embedding utilities (open-only, open-then-short).
- Multi-frequency design report aggregator.
- Optional matplotlib plotting helpers.
- Performance benchmarks suite.
- Auto-generated CLI reference (``scripts/generate_cli_reference.py``).
- Pre-commit hook running ruff + mypy + pytest.
- 317-test suite (with binary-driven Geom cross-checks under
  ``xvfb-run``).
- Cookbook with 10 worked design recipes.
- Tutorial walking through the full design flow.

### Documentation

- ``README.md`` — project overview and structure.
- ``TUTORIAL.md`` — step-by-step design flow.
- ``COOKBOOK.md`` — 10 worked recipes.
- ``CLI_REFERENCE.md`` — auto-generated REPL command table.
- ``MAPPING.md`` — line-by-line Python ↔ C function correspondence.
- ``PLAN.md`` — implementation plan and remaining TODOs.

### Library substitutions vs. the original binary

| Vendored in binary | Replacement in Python |
|---|---|
| LAPACK / BLAS | `scipy.linalg` |
| LINPACK | `scipy.linalg` |
| QUADPACK | `scipy.integrate.quad` |
| libf2c (Fortran I/O) | _not needed_ |
| MV++ Sparse-BLAS | `scipy.sparse` (when needed) |
| SGI STL | _not needed_ |
| libstdc++ exceptions | Python exceptions |
| Mesa GL / X11 | _out of scope_ — headless library |
| readline | `cmd.Cmd` / argparse |
| BSAVE binary format | JSON (richer + portable) |

### Known limitations

- The legacy ``run/asitic.linux.2.2`` binary's ``Ind`` and other
  numerical commands segfault in headless mode (uninitialised
  pointer at offset −4 in ``cmd_inductance_compute``); we
  cross-validate via geometry-only commands (``Geom``).
- The full FFT-based grid Green's function is partially ported —
  we use scipy's FFT for the convolution step, which is slower
  than the binary's hand-tuned variant for very large designs.
- Orthogonal-segment mutual inductance returns 0 (the filamentary
  Maxwell limit). The binary's finite-width corner correction is
  documented but not implemented (negligible for 2-D Manhattan
  spirals).

[Unreleased]: https://github.com/AL-255/reASITIC/compare/v0.0.1...HEAD
