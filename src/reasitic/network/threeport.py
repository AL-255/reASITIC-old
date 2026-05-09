"""3-port to 2-port network reduction.

Mirrors the binary's ``reduce_3port_z_to_2port_y``
(``asitic_kernel.c:8652``, address ``0x080881a8``):

The standard reduction is to invert the full 3×3 Z, then take the
2×2 sub-block of Y between the two retained ports. That is
mathematically equivalent to grounding the third port (V₃ = 0) and
solving for I₁, I₂ in terms of V₁, V₂.

We also provide :func:`z_to_s_3port` corresponding to
``z_to_s_3port_50ohm`` (``0x080884b8``).
"""

from __future__ import annotations

import numpy as np


def reduce_3port_z_to_2port_y(Z3: np.ndarray, ground_port: int = 2) -> np.ndarray:
    """Reduce a 3×3 Z matrix to a 2×2 Y by grounding ``ground_port``.

    Returns the 2×2 Y matrix between the two non-grounded ports
    (with the relative ordering preserved). The default
    ``ground_port=2`` matches the binary's behaviour of grounding
    port 3 (zero-indexed: port 2).
    """
    if Z3.shape != (3, 3):
        raise ValueError(f"expected 3x3 matrix, got {Z3.shape}")
    if ground_port not in (0, 1, 2):
        raise ValueError("ground_port must be 0, 1 or 2")
    Y3 = np.linalg.inv(Z3)
    keep = [i for i in range(3) if i != ground_port]
    return np.asarray(Y3[np.ix_(keep, keep)], dtype=complex)


def z_to_s_3port(Z3: np.ndarray, z0_ohm: float = 50.0) -> np.ndarray:
    """Convert a 3×3 Z matrix to a scattering matrix S₃.

    .. math::

        S = (Z - Z_0 I)(Z + Z_0 I)^{-1}

    Mirrors ``z_to_s_3port_50ohm`` (``0x080884b8``).
    """
    if Z3.shape != (3, 3):
        raise ValueError(f"expected 3x3 matrix, got {Z3.shape}")
    eye = np.eye(3, dtype=complex)
    return np.asarray(np.linalg.solve((Z3 + z0_ohm * eye).T, (Z3 - z0_ohm * eye).T).T)
