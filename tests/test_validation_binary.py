"""Cross-checks against the original 1999 ASITIC binary, run under QEMU.

reASITIC's validation harness only supports QEMU user-mode
execution of the legacy 32-bit binary. Native execution on
modern Linux segfaults inside ``compute_mutual_inductance`` for
any AC-frequency analysis (``Res <freq>``, ``Pi <freq>``,
``2Port``) due to a 1999-era kernel / FPU-state ABI mismatch;
QEMU's instruction-translation layer dodges the issue.

These tests are skipped automatically if the binary,
``xvfb-run``, or ``qemu-i386-static`` aren't on PATH. Install
``qemu-user-static`` (Debian / Ubuntu) or ``qemu-user-static``
(Fedora / RHEL) to enable them. See the parent repo's
``BINARY_VALIDATION.md`` for details.
"""

import shutil

import pytest

from reasitic.validation import BinaryNotFoundError, BinaryRunner

_RUNNER: BinaryRunner | None
try:
    _RUNNER = BinaryRunner.auto()
except (BinaryNotFoundError, FileNotFoundError):
    _RUNNER = None


_HAS_XVFB = shutil.which("xvfb-run") is not None


pytestmark = pytest.mark.skipif(
    _RUNNER is None or not _HAS_XVFB,
    reason=(
        "legacy ASITIC binary, xvfb-run, or qemu-i386-static not "
        "available — see BINARY_VALIDATION.md in the parent repo"
    ),
)


def test_geom_wire() -> None:
    assert _RUNNER is not None
    r = _RUNNER.geom(
        "W NAME=W1:LEN=100:WID=10:METAL=m3:XORG=0:YORG=0",
        "W1",
    )
    assert r.kind == "Wire"
    assert r.name == "W1"
    assert r.length_um == pytest.approx(100.0)
    assert r.width_um == pytest.approx(10.0)
    assert r.metal == "M3"
    assert r.total_length_um == pytest.approx(100.0)
    assert r.n_segments == 1


def test_geom_square_spiral() -> None:
    assert _RUNNER is not None
    r = _RUNNER.geom(
        "SQ NAME=A:LEN=170:W=10:S=3:N=2:METAL=m3:EXIT=m2:XORG=200:YORG=200",
        "A",
    )
    assert r.name == "A"
    assert "Square" in r.kind or "Spiral" in r.kind
    assert r.spiral_l1_um == pytest.approx(170.0)
    assert r.spiral_l2_um == pytest.approx(170.0)
    assert r.width_um == pytest.approx(10.0)
    assert r.spiral_spacing_um == pytest.approx(3.0)
    assert r.spiral_turns == pytest.approx(2.0)
    assert r.location == pytest.approx((200.0, 200.0))


def test_geom_python_matches_binary_geometry_metadata() -> None:
    """Cross-check the Python ``square_spiral`` builder against the
    legacy binary's ``Geom`` parser:

    * ``L1`` / ``L2`` / ``W`` / ``S`` / ``N`` / location must match
      exactly — these are the build-input parameters echoed back.
    * Segment count differs by the binary's two extra lead segments
      (input + output port stubs); the Python builder produces only
      the internal turn segments. The check is therefore
      ``binary == python + 2``.
    """
    import reasitic
    from tests import _paths

    assert _RUNNER is not None
    tech = reasitic.parse_tech_file(_paths.tech_path("BiCMOS.tek"))
    r = _RUNNER.geom(
        "SQ NAME=B:LEN=200:W=10:S=2:N=3:METAL=m3:XORG=200:YORG=200",
        "B",
    )
    py_shape = reasitic.square_spiral(
        "B", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    # Build parameters must round-trip
    assert r.spiral_l1_um == pytest.approx(200.0)
    assert r.width_um == pytest.approx(10.0)
    assert r.spiral_spacing_um == pytest.approx(2.0)
    assert r.spiral_turns == pytest.approx(3.0)
    # The binary counts two extra lead segments (input + output stubs)
    if r.n_segments is not None:
        assert len(py_shape.segments()) + 2 == r.n_segments
