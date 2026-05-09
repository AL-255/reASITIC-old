"""Tests for the reasitic.summary() helper."""

from __future__ import annotations

import sys


def test_summary_returns_string() -> None:
    import reasitic

    s = reasitic.summary()
    assert isinstance(s, str)
    assert reasitic.__version__ in s
    assert "Python" in s


def test_summary_mentions_scipy_state() -> None:
    import reasitic

    s = reasitic.summary()
    # Either "scipy <ver>" or "scipy missing" should appear
    assert "scipy" in s


def test_summary_mentions_matplotlib_state() -> None:
    import reasitic

    s = reasitic.summary()
    assert "matplotlib" in s


def test_summary_handles_missing_scipy(monkeypatch) -> None:
    """When scipy can't be imported, summary() should report it."""
    import reasitic

    # Force `import scipy` to raise ImportError inside summary()
    monkeypatch.setitem(sys.modules, "scipy", None)
    s = reasitic.summary()
    assert "scipy missing" in s


def test_summary_handles_missing_matplotlib(monkeypatch) -> None:
    """When matplotlib can't be imported, summary() should report it
    along with the install hint."""
    import reasitic

    monkeypatch.setitem(sys.modules, "matplotlib", None)
    s = reasitic.summary()
    assert "matplotlib not installed" in s
    assert "pip install reASITIC[plot]" in s


def test_summary_handles_both_missing(monkeypatch) -> None:
    """Both extras missing simultaneously."""
    import reasitic

    monkeypatch.setitem(sys.modules, "scipy", None)
    monkeypatch.setitem(sys.modules, "matplotlib", None)
    s = reasitic.summary()
    assert "scipy missing" in s
    assert "matplotlib not installed" in s
