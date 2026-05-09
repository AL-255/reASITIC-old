import reasitic


def test_version_exposed() -> None:
    assert isinstance(reasitic.__version__, str)
    assert reasitic.__version__
