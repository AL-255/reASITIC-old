"""Shared filesystem paths for tests.

The tech files (``BiCMOS.tek``, ``CMOS.tek``) live in
``tests/data/`` so the test suite is self-contained and runs cleanly
when the repo is checked out standalone (e.g. on CI). Older test
files referenced ``../../run/tek/...`` from the parent ``asitic-re``
checkout; that lookup is preserved as a fallback for developers who
keep the legacy submodule layout.
"""

from __future__ import annotations

from pathlib import Path

_TESTS_DIR = Path(__file__).resolve().parent
DATA_DIR = _TESTS_DIR / "data"


def tech_path(name: str) -> Path:
    """Locate a bundled tech file by basename (e.g. ``"BiCMOS.tek"``).

    Looks first under ``tests/data/``; if missing, falls back to the
    legacy submodule layout at ``<repo>/../run/tek/``.
    """
    bundled = DATA_DIR / name
    if bundled.exists():
        return bundled
    legacy = _TESTS_DIR.parent.parent / "run" / "tek" / name
    if legacy.exists():
        return legacy
    raise FileNotFoundError(
        f"tech file {name!r} not found in tests/data or legacy run/tek"
    )


BICMOS = tech_path("BiCMOS.tek")
CMOS = tech_path("CMOS.tek")
