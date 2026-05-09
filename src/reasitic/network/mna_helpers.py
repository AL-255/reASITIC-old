"""Modified-Nodal-Analysis matrix helpers.

Mirrors a cluster of small MNA-pipeline functions from the binary:

* :func:`assemble_mna_matrix`     ↔ ``node_eq_assemble`` (decomp ``0x0806cc30``)
* :func:`setup_mna_rhs`           ↔ ``node_eq_setup_rhs`` (``0x08054a08``)
* :func:`unpack_mna_solution_forward`  ↔ ``node_eq_unpack_forward`` (``0x0806de64``)
* :func:`unpack_mna_solution_backward` ↔ ``node_eq_unpack_backward`` (``0x0806df14``)
* :func:`lmat_subblock_assemble`  ↔ ``lmat_subblock_assemble`` (``0x0805556c``)
* :func:`lmat_compute_partial_traces` ↔ ``lmat_compute_partial_traces`` (``0x08055fe0``)

The binary's MNA solver is a 2401-byte LAPACK-backed routine
``solve_3port_equations`` plus a 3078-byte ``solve_node_equations``;
faithfully porting the byte-level FPU shuffling produces hard-to-
test mess. The Python equivalents below provide clean
NumPy / SciPy-backed implementations with the same API contracts:
they take the same inputs, produce equivalent outputs, and pass
the same physical-correctness tests.
"""

from __future__ import annotations

import numpy as np


def assemble_mna_matrix(
    n_nodes: int,
    *,
    branch_admittances: list[tuple[int, int, complex]] | None = None,
    port_nodes: list[int] | None = None,
) -> np.ndarray:
    """Build a Modified-Nodal-Analysis stamp matrix.

    Mirrors ``node_eq_assemble`` (decomp ``0x0806cc30``). Each branch
    contribution ``(i, j, y)`` adds the standard MNA stamp::

        Y[i, i] += y     Y[j, j] += y
        Y[i, j] -= y     Y[j, i] -= y

    If ``port_nodes`` is given, those rows are *not* eliminated —
    the caller drives current sources directly into them.

    Args:
        n_nodes:            Total node count (rows / cols of Y).
        branch_admittances: List of (node_i, node_j, admittance)
                            triples to stamp. ``-1`` for a node
                            index means ground (skipped).
        port_nodes:         Indices of port nodes (kept independent;
                            they're informational here — the actual
                            elimination happens in ``solve_*``).

    Returns:
        ``(n_nodes, n_nodes)`` complex Y-matrix with all stamps.
    """
    Y = np.zeros((n_nodes, n_nodes), dtype=complex)
    if branch_admittances:
        for i, j, y in branch_admittances:
            if i >= 0:
                Y[i, i] += y
            if j >= 0:
                Y[j, j] += y
            if i >= 0 and j >= 0:
                Y[i, j] -= y
                Y[j, i] -= y
    _ = port_nodes  # retained for API parity with the binary
    return Y


def setup_mna_rhs(
    n_nodes: int,
    *,
    current_sources: list[tuple[int, complex]] | None = None,
) -> np.ndarray:
    """Build the right-hand-side vector for the MNA solve.

    Mirrors ``node_eq_setup_rhs`` (decomp ``0x08054a08``). Stamps a
    list of injected currents at specific nodes:

    .. code-block:: text

        b[i] += I_i  for each (i, I_i) in current_sources

    Returns the dense complex RHS vector ``b``.
    """
    b = np.zeros(n_nodes, dtype=complex)
    if current_sources:
        for i, current in current_sources:
            if 0 <= i < n_nodes:
                b[i] += current
    return b


def unpack_mna_solution_forward(
    x: np.ndarray,
    *,
    port_nodes: list[int] | None = None,
) -> np.ndarray:
    """Extract port voltages from an MNA solution vector.

    Mirrors ``node_eq_unpack_forward`` (decomp ``0x0806de64``). For
    a solved MNA system ``Y · v = b``, returns the per-port subset
    of ``x`` (the node voltages at ``port_nodes``). If
    ``port_nodes`` is None, returns the full vector unchanged.
    """
    if port_nodes is None:
        return np.asarray(x, dtype=complex)
    return np.asarray([x[i] for i in port_nodes], dtype=complex)


def unpack_mna_solution_backward(
    x: np.ndarray,
    *,
    port_nodes: list[int] | None = None,
    n_nodes: int | None = None,
) -> np.ndarray:
    """Pad a port-voltage vector back into the full node-voltage layout.

    Mirrors ``node_eq_unpack_backward`` (decomp ``0x0806df14``).
    Inverse of :func:`unpack_mna_solution_forward`. Given a port-
    sized ``x`` and the original ``port_nodes`` mapping, returns a
    full ``n_nodes``-sized vector with the port entries filled in
    and the rest set to zero.
    """
    if port_nodes is None or n_nodes is None:
        return np.asarray(x, dtype=complex)
    out = np.zeros(n_nodes, dtype=complex)
    for k, idx in enumerate(port_nodes):
        out[idx] = x[k]
    return out


# LMAT helpers --------------------------------------------------------------


def lmat_subblock_assemble(
    L_full: np.ndarray,
    row_indices: list[int],
    col_indices: list[int],
) -> np.ndarray:
    """Extract a sub-block of the partial-L matrix.

    Mirrors ``lmat_subblock_assemble`` (decomp ``0x0805556c``).
    Returns ``L_full[row_indices, :][:, col_indices]`` as a fresh
    array. Used by the LMAT export when the user picks a subset of
    segments / spirals to dump.
    """
    if L_full.ndim != 2:
        raise ValueError(f"L_full must be 2-D, got shape {L_full.shape}")
    return np.asarray(L_full[np.ix_(row_indices, col_indices)].copy())


def lmat_compute_partial_traces(
    L_full: np.ndarray,
    block_sizes: list[int],
) -> np.ndarray:
    """Block-diagonal trace decomposition of the partial-L matrix.

    Mirrors ``lmat_compute_partial_traces`` (decomp ``0x08055fe0``):
    given the partial-inductance matrix ``L_full`` and a partition
    of its rows into ``block_sizes`` consecutive groups, returns a
    1-D array of per-block trace values
    ``[Tr(L_block_0), Tr(L_block_1), ...]``.

    These are the per-segment self-inductance sums that the binary
    uses as a sanity check on the LMAT export — for a single
    segment the trace is exactly its self-L; for a turn-block the
    trace gives the total self-L of that turn.
    """
    if L_full.ndim != 2 or L_full.shape[0] != L_full.shape[1]:
        raise ValueError("L_full must be a square matrix")
    if sum(block_sizes) > L_full.shape[0]:
        raise ValueError(
            f"block_sizes sum {sum(block_sizes)} exceeds matrix size "
            f"{L_full.shape[0]}"
        )
    traces = np.zeros(len(block_sizes))
    offset = 0
    for k, n in enumerate(block_sizes):
        if n <= 0:
            continue
        block = L_full[offset: offset + n, offset: offset + n]
        traces[k] = float(np.trace(block))
        offset += n
    return traces
