"""Tests for the reasitic.summary() helper."""


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
