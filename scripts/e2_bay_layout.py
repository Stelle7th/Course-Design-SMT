#!/usr/bin/env python3
"""E2 L2: re-order equipment within each bay along the two rail-side columns.

Each Intrabay holds equipment in exactly two fixed x-columns (one on each side of
the OHT rail). Equipment keeps its reference column and is only re-ordered along
the rail direction (y); non-overlap is therefore one-dimensional. The objective
minimizes flow-weighted |y difference| between equipment centers.

The flow matrix is fixed and comes from E1's ``transport_flow.csv``, so this is
the "fixed flow -> optimize layout" half of the alternating optimization. The
"fixed layout -> re-solve flow" half is E1 itself.
"""

from __future__ import annotations

import argparse
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e2_common import (  # noqa: E402
    group_by_bay,
    load_equipment,
    load_transport_flows,
    log,
    manhattan_cost,
    write_csv,
    write_json,
)


def solve_bay_layout(
    items: list[dict[str, Any]],
    flows: dict[tuple[str, str], float],
    time_limit: float = 60.0,
    mip_gap: float = 0.01,
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    """Solve the within-bay layout MILP for one bay (two fixed columns, 1-D reorder).

    Equipment keeps its reference x-column (left/right of the rail) and is only
    re-ordered along the rail direction (y). Non-overlap is one-dimensional, and
    the objective minimizes flow-weighted |y difference| between equipment centers.
    Returns ``(new_items, info)``.
    """
    n = len(items)
    if n <= 1:
        return items, {
            "status": 0,
            "success": True,
            "message": "trivial (<=1 equipment)",
            "objective": 0.0,
            "equipment_count": n,
            "variables": 0,
            "constraints": 0,
            "kept_reference": True,
        }

    # 1. Determine the two fixed x-columns from the reference layout.
    xs = [item["x"] for item in items]
    x_left, x_right = min(xs), max(xs)
    col = [
        0 if abs(item["x"] - x_left) <= abs(item["x"] - x_right) else 1
        for item in items
    ]

    ys = [item["y"] for item in items]
    hs = [item["height"] for item in items]
    ymin, ymax = min(ys), max(ys)
    H = max(ymax - ymin, 1.0)
    M = 2.0 * H + max(hs)

    flow_index = {item["name"]: i for i, item in enumerate(items)}
    directed: dict[tuple[int, int], float] = defaultdict(float)
    for (src, dst), flow in flows.items():
        i = flow_index.get(src)
        j = flow_index.get(dst)
        if i is None or j is None or i == j:
            continue
        directed[(i, j)] += flow

    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    pair_idx = {p: k for k, p in enumerate(pairs)}
    m = len(pairs)
    same_pairs = [p for p in pairs if col[p[0]] == col[p[1]]]
    same_idx = {p: k for k, p in enumerate(same_pairs)}
    ns = len(same_pairs)

    # Variables: y_i (0..n-1), u_{ij} (n..n+m-1), z_{ij} (n+m..n+m+ns-1).
    num_vars = n + m + ns
    c = np.zeros(num_vars)
    integrality = np.zeros(num_vars, dtype=int)
    lower = np.zeros(num_vars)
    upper = np.full(num_vars, np.inf)

    # y_i bounded inside the bay's reference y-range.
    for i in range(n):
        lo = ymin + hs[i] / 2.0
        hi = ymax - hs[i] / 2.0
        if hi < lo:
            lo, hi = ymin, ymax
        lower[i], upper[i] = lo, hi

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    rhs: list[float] = []

    def add(coeffs: dict[int, float], ub: float) -> None:
        row = len(rhs)
        for col, val in coeffs.items():
            if val:
                rows.append(row)
                cols.append(col)
                data.append(val)
        rhs.append(ub)

    # Distance linearization for every pair.
    for (i, j) in pairs:
        u = n + pair_idx[(i, j)]
        flow = directed.get((i, j), 0.0) + directed.get((j, i), 0.0)
        c[u] = flow
        # u >= |y_i - y_j|
        add({i: 1.0, j: -1.0, u: -1.0}, 0.0)
        add({j: 1.0, i: -1.0, u: -1.0}, 0.0)

    # Non-overlap along y for same-column pairs only.
    for (i, j) in same_pairs:
        z = n + m + same_idx[(i, j)]
        integrality[z] = 1
        upper[z] = 1.0
        hy = (hs[i] + hs[j]) / 2.0
        # y_j - y_i + M*z <= M - hy   (z=1 -> i above j)
        add({j: 1.0, i: -1.0, z: M}, M - hy)
        # y_i - y_j - M*z <= -hy      (z=0 -> j above i)
        add({i: 1.0, j: -1.0, z: -M}, -hy)

    A = coo_matrix((data, (rows, cols)), shape=(len(rhs), num_vars)).tocsr()
    constraints = [LinearConstraint(A, -np.inf, np.array(rhs))]
    bounds = Bounds(lower, upper)

    result = milp(
        c=c,
        integrality=integrality,
        bounds=bounds,
        constraints=constraints,
        options={"time_limit": time_limit, "mip_rel_gap": mip_gap},
    )

    # Constant x-distance contribution of cross-column pairs (columns are fixed).
    const_x = 0.0
    for (i, j) in pairs:
        if col[i] != col[j]:
            flow = directed.get((i, j), 0.0) + directed.get((j, i), 0.0)
            const_x += flow * abs(xs[i] - xs[j])

    new_items = [dict(item) for item in items]
    if result.x is not None:
        for i in range(n):
            new_items[i]["y"] = float(result.x[i])
            # x column is kept fixed (rail-side constraint).

    info = {
        "status": int(result.status),
        "success": bool(result.success),
        "message": str(result.message),
        "objective": float(result.fun) + const_x if result.fun is not None else None,
        "equipment_count": n,
        "variables": num_vars,
        "constraints": len(rhs),
        "kept_reference": result.x is None,
    }
    return new_items, info


def main() -> int:
    parser = argparse.ArgumentParser(description="Solve the E2 L2 within-bay layout MILP.")
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--e0-dir", type=Path, default=Path("output/e0_audit"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/e2_layout"))
    parser.add_argument("--time-limit-sec", type=float, default=60.0)
    args = parser.parse_args()

    e1_dir = args.e1_dir.resolve()
    e0_dir = args.e0_dir.resolve()
    output_dir = args.output_dir.resolve()

    log("E2-L2: 读取设备几何与设备间流量 ...")
    equipment = load_equipment(
        e1_dir / "selected_equipment_ports.csv",
        e0_dir / "equipment_mapping.csv",
    )
    flows = load_transport_flows(e1_dir / "transport_flow.csv")

    by_bay = group_by_bay(equipment)
    bay_names = sorted(by_bay)
    log(
        f"E2-L2: 共 {len(equipment)} 台设备、{len(bay_names)} 个 Bay、"
        f"{len(flows)} 条设备对流量，逐 Bay 求解布局 MILP ..."
    )
    optimized: list[dict[str, Any]] = []
    bay_infos: dict[str, dict[str, Any]] = {}
    for idx, bay in enumerate(bay_names, start=1):
        items = by_bay[bay]
        original_cost = manhattan_cost(items, flows)
        log(f"E2-L2: [{idx}/{len(bay_names)}] Bay {bay}（{len(items)} 台设备）求解中 ...")
        t0 = time.perf_counter()
        new_items, info = solve_bay_layout(items, flows, args.time_limit_sec)
        elapsed = time.perf_counter() - t0
        info["original_bay_cost"] = original_cost
        bay_infos[bay] = info
        optimized.extend(new_items)
        if info["kept_reference"]:
            log(
                f"E2-L2: [{idx}/{len(bay_names)}] Bay {bay} 未收敛（状态={info['status']}，"
                f"耗时 {elapsed:.1f}s），保留参考布局"
            )
        else:
            log(
                f"E2-L2: [{idx}/{len(bay_names)}] Bay {bay} 完成，耗时 {elapsed:.1f}s，"
                f"目标={info['objective']:.1f}（原 {original_cost:.1f}）"
            )

    baseline = manhattan_cost(equipment, flows)
    optimized_cost = manhattan_cost(optimized, flows)

    layout_rows = [
        {
            "equipment_name": item["name"],
            "bay": item["bay"],
            "x": item["x"],
            "y": item["y"],
            "width": item["width"],
            "height": item["height"],
        }
        for item in optimized
    ]
    write_csv(
        output_dir / "new_layout.csv",
        layout_rows,
        ["equipment_name", "bay", "x", "y", "width", "height"],
    )
    write_json(
        output_dir / "e2_summary.json",
        {
            "e2_version": "1.0",
            "equipment_count": len(equipment),
            "bay_count": len(by_bay),
            "baseline_cost_manhattan": baseline,
            "optimized_cost_manhattan": optimized_cost,
            "cost_reduction": baseline - optimized_cost,
            "bay_infos": bay_infos,
            "distance_note": (
                "Cost is flow * Manhattan coordinate distance (layout proxy). "
                "E1 uses the directed rail-graph shortest path."
            ),
        },
    )

    print(f"equipment={len(equipment)} bays={len(by_bay)}")
    print(f"baseline_cost={baseline:.1f} optimized_cost={optimized_cost:.1f}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
