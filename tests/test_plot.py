"""Tests for the (optional) matplotlib plot helpers."""

from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
)

_BICMOS = Path(__file__).resolve().parents[2] / "run" / "tek" / "BiCMOS.tek"


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


@pytest.fixture
def matplotlib_or_skip():
    try:
        import matplotlib
        matplotlib.use("Agg")  # headless
        import matplotlib.pyplot as plt
        return plt
    except ImportError:
        pytest.skip("matplotlib not available")


def test_plot_shape_returns_axes(matplotlib_or_skip, tech) -> None:
    from reasitic.plot import plot_shape

    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=3, tech=tech, metal="m3"
    )
    ax = plot_shape(sp)
    assert ax is not None
    assert ax.get_title() == "Shape <S>"


def test_plot_sweep_with_all_series(matplotlib_or_skip) -> None:
    from reasitic.plot import plot_sweep

    fs = [1.0, 2.0, 3.0]
    Ls = [1.0, 1.1, 1.3]
    Rs = [2.0, 2.4, 3.1]
    Qs = [3.1, 5.5, 6.2]
    ax = plot_sweep(fs, Ls, Rs, Qs)
    assert ax is not None


def test_plot_lr_matrix(matplotlib_or_skip, tech) -> None:
    from reasitic.plot import plot_lr_matrix

    sp = square_spiral(
        "S", length=200, width=10, spacing=2, turns=2, tech=tech, metal="m3"
    )
    ax = plot_lr_matrix(sp)
    assert ax is not None


def test_import_raises_clear_error_when_matplotlib_missing(monkeypatch) -> None:
    """Without matplotlib installed, _require_matplotlib raises ImportError."""
    import sys

    # Hide matplotlib from the import system
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    monkeypatch.setitem(sys.modules, "matplotlib.pyplot", None)
    from reasitic.plot import _require_matplotlib

    with pytest.raises(ImportError):
        _require_matplotlib()
