"""More tests to push coverage on eddy / green / filament / binary_runner."""

import math
from pathlib import Path

import pytest

from reasitic import (
    parse_tech_file,
    square_spiral,
    wire,
)
from reasitic.geometry import Point, Segment
from reasitic.inductance.eddy import (
    _image_filament,
    eddy_correction,
    solve_inductance_with_eddy,
)
from reasitic.inductance.filament import (
    Filament,
    filament_grid,
    solve_inductance_matrix,
    solve_inductance_mna,
)
from tests import _paths

_BICMOS = _paths.tech_path("BiCMOS.tek")


@pytest.fixture
def tech():
    return parse_tech_file(_BICMOS)


# Eddy correction edge cases ------------------------------------------


def test_eddy_no_layers() -> None:
    """A Tech with no substrate layers returns (0, 0)."""
    from reasitic.tech import Chip, Tech
    no_layer = Tech(chip=Chip(), layers=[], metals=[], vias=[])
    sp_dummy = wire("W", length=100, width=10, tech=parse_tech_file(_BICMOS), metal="m3")
    dL, dR = eddy_correction(sp_dummy, no_layer, freq_ghz=2.0)
    assert dL == 0.0
    assert dR == 0.0


def test_eddy_zero_resistivity(tech) -> None:
    """ρ = 0 substrate (perfect conductor) returns (0, 0) by guard."""
    # Hijack the tech file's first layer to have rho=0
    tech_zero = parse_tech_file(_BICMOS)
    tech_zero.layers[0].rho = 0
    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=2,
        tech=tech_zero, metal="m3",
    )
    dL, dR = eddy_correction(sp, tech_zero, freq_ghz=2.0)
    assert dL == 0.0
    assert dR == 0.0


def test_eddy_finite_thickness_off(tech) -> None:
    """``finite_thickness=False`` recovers semi-infinite ground."""
    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    dL_inf, _ = eddy_correction(sp, tech, freq_ghz=2.0, finite_thickness=False)
    dL_fin, _ = eddy_correction(sp, tech, freq_ghz=2.0, finite_thickness=True)
    # |dL_inf| should be >= |dL_fin| since semi-infinite couples
    # more strongly than a thin substrate.
    assert abs(dL_inf) >= abs(dL_fin) - 1e-12


def test_eddy_solve_with_eddy_off(tech) -> None:
    """include_eddy=False skips the correction."""
    sp = square_spiral(
        "L", length=200, width=10, spacing=2, turns=3,
        tech=tech, metal="m3",
    )
    L0, R0 = solve_inductance_matrix(sp, tech, freq_ghz=2.0)
    L_no_eddy, R_no_eddy = solve_inductance_with_eddy(
        sp, tech, freq_ghz=2.0, include_eddy=False,
    )
    assert L_no_eddy == pytest.approx(L0, rel=1e-12)
    assert R_no_eddy == pytest.approx(R0, rel=1e-12)


def test_eddy_image_filament_mirrors_z() -> None:
    f = Filament(
        a=Point(0, 0, 5),
        b=Point(100, 0, 5),
        width=10, thickness=2, metal=0, parent_segment=0,
    )
    img = _image_filament(f)
    # Mirrored z + reversed direction
    assert img.a.z == -5
    assert img.b.z == -5
    # Endpoints are swapped (reversed direction)
    assert img.a.x == 100
    assert img.b.x == 0


def test_eddy_handles_normal_shape(tech) -> None:
    """Smoke test: eddy correction returns finite values."""
    sp = wire("W", length=100, width=10, tech=tech, metal="m3")
    dL, dR = eddy_correction(sp, tech, freq_ghz=2.0)
    assert math.isfinite(dL)
    assert math.isfinite(dR)


# Substrate green's edge cases ----------------------------------------


def test_green_function_with_no_layers() -> None:
    """A Tech with no layers gives R_stack = 0; G is the free-space form."""
    from reasitic.substrate import green_function_static
    from reasitic.tech import Chip, Tech
    bare = Tech(chip=Chip(), layers=[], metals=[], vias=[])
    g = green_function_static(rho_um=10, z1_um=1, z2_um=1, tech=bare)
    assert math.isfinite(g)
    assert g > 0


def test_green_reflection_with_zero_layer_eps() -> None:
    """A layer with zero eps is skipped in the recursion."""
    from reasitic.substrate.green import _stack_reflection_coefficient
    from reasitic.tech import Chip, Layer, Tech
    bad = Tech(
        chip=Chip(),
        layers=[Layer(index=0, rho=10, t=100, eps=0.0)],
        metals=[],
        vias=[],
    )
    R = _stack_reflection_coefficient(bad, k_rho=1.0e6)
    assert -1.0 <= R <= 1.0


def test_integrate_green_kernel_extreme_kmax(tech) -> None:
    """A huge k_max should still give a finite (perhaps small) integral."""
    from reasitic.substrate import integrate_green_kernel
    val = integrate_green_kernel(
        rho_um=20, z1_um=2, z2_um=2, tech=tech, k_max=1e10,
    )
    assert math.isfinite(val)


# Filament solver: bigger checks --------------------------------------


def test_filament_grid_for_zero_length_segment_returns_empty() -> None:
    seg = Segment(
        a=Point(0, 0, 0), b=Point(0, 0, 0),
        width=10, thickness=2, metal=0,
    )
    fils = filament_grid(seg, n_w=2, n_t=2)
    assert fils == []


def test_solve_inductance_mna_with_4_filaments_per_seg(tech) -> None:
    """2x2 = 4 filaments per parent segment; should still be tractable."""
    sp = square_spiral(
        "L", length=200, width=20, spacing=4, turns=2,
        tech=tech, metal="m3",
    )
    L, R = solve_inductance_mna(sp, tech, freq_ghz=1.0, n_w=2, n_t=2)
    assert math.isfinite(L) and L > 0
    assert math.isfinite(R) and R > 0


# CLI dispatch coverage -----------------------------------------------


def test_cli_handles_unknown_inside_section(tech) -> None:
    """Truly unknown commands print 'Unknown' and don't crash."""
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    out = r.execute("ZZZZZ_UNKNOWN_COMMAND foo bar")
    assert out is True


def test_cli_macro_records_via_dispatch(tech) -> None:
    """RECORD captures lines as they pass through ``execute``."""
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    r.execute("RECORD")
    r.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    r.execute("LIST")
    assert r.macro is not None
    assert any("SQ" in cmd for cmd in r.macro)


def test_cli_log_writes_each_command(tmp_path: Path) -> None:
    from reasitic.cli import Repl
    r = Repl()
    r.cmd_load_tech(str(_BICMOS))
    log = tmp_path / "log.txt"
    r.cmd_log(str(log))
    r.execute("SQ NAME=A:LEN=100:W=10:S=2:N=2:METAL=m3")
    text = log.read_text()
    assert "SQ" in text