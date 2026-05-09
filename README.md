# reASITIC

Reverse-engineered, clean-room Python implementation of [ASITIC][asitic] — a
planar RF inductor analysis and design tool originally developed at UC
Berkeley.

> **Status:** planning. The package skeleton is in place; numerical kernels
> and the analysis surface are not yet implemented.

## Install

From source, in a virtual environment:

```bash
pip install -e ".[dev]"
```

Once published:

```bash
pip install reASITIC
```

## Usage

```python
import reasitic

print(reasitic.__version__)
```

The public API will grow as analysis primitives (geometry, Greenhouse-style
partial inductances, substrate Green's functions, S/Y/Z extraction, …) are
ported.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check .
mypy
```

## License

GPL-2.0-only. See [LICENSE](LICENSE).

[asitic]: https://rfic.eecs.berkeley.edu/~niknejad/asitic.html
