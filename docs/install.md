# Installation

## From PyPI

```bash
pip install reASITIC                 # base library
pip install reASITIC[plot]           # + matplotlib for plotting helpers
```

## Development install

```bash
git clone https://github.com/AL-255/reASITIC.git
cd reASITIC
pip install -e ".[dev,docs]"
```

The `[dev]` extra installs the testing toolchain (pytest, pytest-cov,
ruff, mypy, matplotlib). The `[docs]` extra installs Sphinx, Furo and
the MyST parser used to build this site.

## Runtime requirements

| Package      | Minimum version |
| ------------ | --------------- |
| Python       | 3.10            |
| NumPy        | 1.24            |
| SciPy        | 1.10            |
| matplotlib   | 3.7 (optional)  |

reASITIC follows
[NEP 29](https://numpy.org/neps/nep-0029-deprecation_policy.html) for
its Python and NumPy support window.

## Verifying the install

```bash
reasitic --version
python -c "import reasitic; print(reasitic.summary())"
```

## Optional: legacy binary

The original 1999 ASITIC binary (`asitic.linux.2.2`) ships in the
`run/` directory of the upstream repository. The cross-validation
harness under `reasitic.validation.binary_runner` drives it through
`xvfb-run` to compare geometric outputs against the Python port. The
binary is *not* required for normal use; it is only used by the test
suite under `tests/test_validation_binary.py`, which auto-skips if
the binary is missing.
