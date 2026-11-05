#!/usr/bin/env python3
"""E2 L1: order Intrabays along the Interbay spine (1D QAP MILP).

Decision: assign each Intrabay a distinct integer position along the spine so
that the flow-weighted (flow * |position difference|) transport cost between bays
is minimized. This is the classic spine-layout problem solved as a MILP with
``scipy.optimize.milp`` (HiGHS).

The objective uses unit spacing between adjacent positions, so it *ranks* bay
orderings rather than representing physical inter-bay distance.
"""

from __future__ import annotations

import argparse
import json
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import Bounds, LinearConstraint, milp
from scipy.sparse import coo_matrix

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e2_common import load_bay_flows, log, write_json  # noqa: E402


def solve_bay_ordering(
    bay_names: list[str],
    bay_flows: dict[tuple[str, str], float],
    time_limit: float = 30.0,
) -> dict[str, Any]:
    """Solve the 1D bay-ordering MILP.

    Returns a dict with ``bay_ordering`` (name -> 0-based position),
    ``ranked_bays`` and ``solver`` metadata.
    """
    n = len(bay_names)
    index = {name: i for i, name in enumerate(bay_names)}
    pairs = [(i, j) for i in range(n) for j in range(i + 1, n)]
    m = len(pairs)

    # Variable layout: pos (n) | z (m) | u (m)
    num_vars = n + 2 * m
    c = np.zeros(num_vars)
    integrality = np.zeros(num_vars, dtype=int)
    lower = np.zeros(num_vars)
    upper = np.full(num_vars, np.inf)

    # pos: integer in [0, n-1]
    lower[:n] = 0.0
    upper[:n] = float(n - 1)
    integrality[:n] = 1

    # z: binary; u: continuous non-negative
    for k in range(m):
        integrality[n + k] = 1
        upper[n + k] = 1.0

    rows: list[int] = []
    cols: list[int] = []
    data: list[float] = []
    rhs: list[float] = []
    M = float(n)

    for k, (i, j) in enumerate(pairs):
        z = n + k
        u = n + m + k
        c[u] = bay_flows.get((bay_names[i], bay_names[j]), 0.0) + bay_flows.get(
            (bay_names[j], bay_names[i]), 0.0
        )

        def add(coeffs: dict[int, float], ub: float) -> None:
            row = len(rhs)
            for col, val in coeffs.items():
                if val:
                    rows.append(row)
                    cols.append(col)
                    data.append(val)
            rhs.append(ub)

        # z=1 -> pos_j >= pos_i + 1  (i before j)
        add({i: 1.0, j: -1.0, z: M}, M - 1.0)
        # z=0 -> pos_i >= pos_j + 1  (j before i)
        add({j: 1.0, i: -1.0, z: -M}, -1.0)
        # u >= |pos_i - pos_j|
        add({i: 1.0, j: -1.0, u: -1.0}, 0.0)
        add({j: 1.0, i: -1.0, u: -1.0}, 0.0)

    A = coo_matrix((data, (rows, cols)), shape=(len(rhs), num_vars)).tocsr()
    constraints = [LinearConstraint(A, -np.inf, np.array(rhs))]
    bounds = Bounds(lower, upper)

    result = milp(
        c=c,
        integrality=integrality,
        bounds=bounds,
        constraints=constraints,
        options={"time_limit": time_limit, "mip_rel_gap": 0.0},
    )

    ordering: dict[str, int] = {}
    ranked: list[str] = []
    if result.x is not None:
        positions = {bay_names[i]: int(round(float(result.x[i]))) for i in range(n)}
        ordering = positions
        ranked = sorted(positions, key=positions.get)

    return {
        "bay_ordering": ordering,
        "ranked_bays": ranked,
        "solver": {
            "status": int(result.status),
            "success": bool(result.success),
            "message": str(result.message),
            "objective": float(result.fun) if result.fun is not None else None,
            "variables": num_vars,
            "constraints": len(rhs),
        },
    }


def main() -> int:
    parser = argparse.ArgumentParser(description="Solve the E2 L1 bay-ordering MILP.")
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/e2_layout"))
    parser.add_argument("--time-limit-sec", type=float, default=30.0)
    args = parser.parse_args()

    e1_dir = args.e1_dir.resolve()
    output_dir = args.output_dir.resolve()

    log("E2-L1: 读取 Bay 间流量 ...")
    bay_flows = load_bay_flows(e1_dir / "from_to_bay.csv")
    bay_names = sorted({bay for pair in bay_flows for bay in pair})
    if not bay_names:
        raise RuntimeError("No bay flows found; run E1 first to produce from_to_bay.csv.")

    log(f"E2-L1: 共 {len(bay_names)} 个 Bay，开始求解排序 MILP（时限 {args.time_limit_sec}s）...")
    t0 = time.perf_counter()
    result = solve_bay_ordering(bay_names, bay_flows, args.time_limit_sec)
    elapsed = time.perf_counter() - t0
    solver = result["solver"]
    status_text = "最优" if solver["status"] == 0 else ("超时/达到时限" if solver["status"] == 1 else f"状态{solver['status']}")
    log(
        f"E2-L1: 求解完成，耗时 {elapsed:.1f}s，{status_text}，"
        f"目标={solver['objective']}，变量={solver['variables']}，约束={solver['constraints']}"
    )
    if result["ranked_bays"]:
        preview = " -> ".join(result["ranked_bays"][:10])
        if len(result["ranked_bays"]) > 10:
            preview += " ..."
        log(f"E2-L1: 排序结果 {preview}")

    payload = {
        "e2_l1_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "bay_count": len(bay_names),
        "solver": result["solver"],
        "bay_ordering": result["bay_ordering"],
        "ranked_bays": result["ranked_bays"],
        "objective_note": (
            "Objective is sum over bay pairs of flow * |position difference| with "
            "unit spacing; it ranks orderings rather than representing physical distance."
        ),
    }
    write_json(output_dir / "bay_order.json", payload)
    lines = [f"{pos + 1:2d}  {name}" for pos, name in enumerate(result["ranked_bays"])]
    (output_dir / "bay_order.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    print(json.dumps(payload["solver"], indent=2))
    print("ranked_bays:", " ".join(result["ranked_bays"]))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
