#!/usr/bin/env python3
"""GPU-accelerated (CuPy) equipment-to-equipment rail distance matrix.

Replaces the O(n^2) matrix-assembly / direct-movement-correction loops inside
``e1_reference_lp.build_equipment_distance_matrix`` with vectorized CuPy kernels.

Notes
-----
* The shortest-path stage (``scipy.sparse.csgraph.dijkstra``) is kept on the
  CPU: the rail graph is small (a few thousand nodes / edges), so it is not the
  bottleneck.  Moving it to cuGraph would pull in the full RAPIDS stack for no
  measurable benefit here.
* The results are bit-compatible with the CPU implementation for the float
  arithmetic used (element-wise adds and ``min``), and the ``__main__`` block
  verifies exact equality against the CPU version.
* Falls back to the original CPU implementation when CuPy is unavailable.
"""

from __future__ import annotations

from typing import Any

import numpy as np
from scipy.sparse import csr_matrix
from scipy.sparse.csgraph import dijkstra

try:  # pragma: no cover - exercised at runtime
    import cupy as cp

    _HAS_CUPY = True
except Exception:  # pragma: no cover
    cp = None
    _HAS_CUPY = False


def has_gpu() -> bool:
    """Return True when CuPy can allocate a CUDA device."""
    if not _HAS_CUPY:
        return False
    try:
        cp.cuda.runtime.getDeviceCount()
        return True
    except Exception:
        return False


def _setup_ports(
    equipment: list[dict[str, Any]],
    rail_meta: dict[str, dict[str, Any]],
    node_index: dict[str, int],
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray, list[int], list[str]]:
    count = len(equipment)
    out_nodes = np.full(count, -1, dtype=np.int64)
    in_nodes = np.full(count, -1, dtype=np.int64)
    out_offsets = np.full(count, np.inf, dtype=float)
    in_offsets = np.full(count, np.inf, dtype=float)
    missing: list[str] = []
    for item in equipment:
        index = item["index"]
        rail = rail_meta.get(item["rail_name"])
        position = item["port_distance"]
        if rail is None or position is None:
            missing.append(item["name"])
            continue
        position = min(max(float(position), 0.0), float(rail["length"]))
        item["port_distance_clamped"] = position
        out_nodes[index] = node_index[rail["to_node"]]
        in_nodes[index] = node_index[rail["from_node"]]
        out_offsets[index] = float(rail["length"]) - position
        in_offsets[index] = position
    valid = [index for index in range(count) if out_nodes[index] >= 0]
    return out_nodes, in_nodes, out_offsets, in_offsets, valid, missing


def build_equipment_distance_matrix_gpu(
    equipment: list[dict[str, Any]],
    rail_meta: dict[str, dict[str, Any]],
    node_index: dict[str, int],
    graph: csr_matrix,
) -> tuple[np.ndarray, dict[str, Any]]:
    """CuPy-accelerated drop-in replacement for the CPU distance matrix.

    Returns ``(distance_matrix, stats)`` exactly like the CPU function.
    """
    if not has_gpu():
        from e1_reference_lp import build_equipment_distance_matrix

        return build_equipment_distance_matrix(equipment, rail_meta, node_index, graph)

    count = len(equipment)
    out_nodes, in_nodes, out_offsets, in_offsets, valid, missing = _setup_ports(
        equipment, rail_meta, node_index
    )
    valid_arr = np.asarray(valid, dtype=np.int64)
    v_count = len(valid)

    # Shortest paths from every distinct source node (CPU; graph is small).
    unique_sources = sorted({int(out_nodes[index]) for index in valid})
    distance_from_source = dijkstra(graph, directed=True, indices=unique_sources)
    source_row = {node: row for row, node in enumerate(unique_sources)}
    src_rows = np.asarray(
        [source_row[int(out_nodes[i])] for i in valid], dtype=np.int64
    )

    # --- GPU assembly: distance_matrix[s, t] = out_off[s] + D[row_s, in_node[t]] + in_off[t] ---
    D_gpu = cp.asarray(distance_from_source)  # (U, N) float64
    sub = D_gpu[cp.asarray(src_rows)]  # (V, N)
    tgt = cp.asarray(in_nodes)  # (count,)
    reachable = tgt >= 0
    gathered = sub[:, cp.clip(tgt, 0, None)]  # (V, count)
    assembled = (
        cp.asarray(out_offsets[valid_arr])[:, None]
        + gathered
        + cp.asarray(in_offsets)[None, :]
    )
    assembled = cp.where(reachable[None, :], assembled, cp.inf)

    full = cp.full((count, count), cp.inf, dtype=cp.float64)
    full[valid_arr] = assembled  # advanced row assignment: (V, count)

    # --- GPU direct-movement correction on the valid x valid sub-matrix ---
    rid = np.full(count, -1, dtype=np.int64)
    pos = np.full(count, np.nan, dtype=float)
    rail_ids: dict[str, int] = {}
    for i in range(count):
        name = equipment[i]["rail_name"]
        if name not in rail_ids:
            rail_ids[name] = len(rail_ids)
        rid[i] = rail_ids[name]
        pos[i] = equipment[i].get("port_distance_clamped", np.nan)

    rid_v = cp.asarray(rid[valid_arr])  # (V,)
    pos_v = cp.asarray(pos[valid_arr])  # (V,)
    same = rid_v[:, None] == rid_v[None, :]  # (V, V)
    src_pos = pos_v[:, None]
    tgt_pos = pos_v[None, :]
    direct = cp.where(same & (tgt_pos >= src_pos), tgt_pos - src_pos, cp.inf)

    rows = cp.repeat(cp.asarray(valid_arr), v_count)
    cols = cp.tile(cp.asarray(valid_arr), v_count)
    existing = full[rows, cols]
    full[rows, cols] = cp.minimum(existing, direct.reshape(-1))

    distance_matrix = cp.asnumpy(full)
    unreachable = int(np.isinf(distance_matrix).sum())
    return distance_matrix, {
        "equipment_count": count,
        "missing_port_path": missing,
        "unreachable_equipment_pairs": unreachable,
        "reachable_equipment_pairs": count * count - unreachable,
    }


if __name__ == "__main__":
    import sys
    import time
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from e0_data_audit import load_smat, load_smt
    from e1_reference_lp import (
        build_equipment_distance_matrix,
        build_rail_graph,
        equipment_and_ports,
    )

    data_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    model = sys.argv[2] if len(sys.argv) > 2 else "LVHM"
    smat_file = (
        Path(sys.argv[3])
        if len(sys.argv) > 3
        else sorted((data_root / "SMAT2022").glob("General Data/**/*.xlsx"))[0]
    )

    smt = load_smt(data_root, model)
    smat = load_smat(smat_file)
    tool_names = {row.get("STN", "") for row in smt["tools"] if row.get("STN")}
    equipment, _, _ = equipment_and_ports(smat, tool_names)
    graph, node_index, rail_meta, _ = build_rail_graph(smat, "manhattan")

    print(f"GPU available: {has_gpu()}")

    t0 = time.perf_counter()
    D_cpu, stats_cpu = build_equipment_distance_matrix(
        equipment, rail_meta, node_index, graph
    )
    t_cpu = time.perf_counter() - t0

    t0 = time.perf_counter()
    D_gpu, stats_gpu = build_equipment_distance_matrix_gpu(
        equipment, rail_meta, node_index, graph
    )
    t_gpu = time.perf_counter() - t0

    same = np.array_equal(D_cpu, D_gpu)
    max_diff = float(np.max(np.abs(D_cpu - D_gpu))) if not same else 0.0

    print(f"CPU time : {t_cpu:.4f}s")
    print(f"GPU time : {t_gpu:.4f}s")
    print(f"identical: {same}  (max |diff| = {max_diff:.3e})")
    print(f"stats equal: {stats_cpu == stats_gpu}")
