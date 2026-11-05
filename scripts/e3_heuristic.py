#!/usr/bin/env python3
"""E3: global layout-flow joint optimization via simulated annealing + LNS.

This extends E1 (fixed-layout flow LP) to a *global* layout optimization: equipment
is re-assigned among the fixed slots (each slot carries a fixed port + rail
connection, hence a fixed on-rail shortest-path distance to every other slot),
while the inner LP re-solves the optimal flows periodically.

Key ideas:
  * Slots = the 1068 movable-equipment positions from the SMAT2022 reference layout.
  * The slot-to-slot directed rail distance matrix D is precomputed once (Dijkstra).
  * Outer search (SA + LNS) explores the assignment of equipment -> slots.
  * Inner LP (E1's build_lp + HiGHS) refreshes the equipment-pair flow F periodically.
  * Equipment may only swap into same-footprint slots (width/height class).

This is a heuristic; it is not an exact global solver.
"""

from __future__ import annotations

import argparse
import math
import random
import sys
import time
from collections import defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e0_data_audit import load_smat, load_smt  # noqa: E402
from e1_reference_lp import (  # noqa: E402
    build_equipment_distance_matrix,
    build_lp,
    build_operations,
    build_rail_graph,
    equipment_and_ports,
    evaluate_solution,
)
from e2_common import log, read_csv, write_csv, write_json  # noqa: E402

try:  # noqa: E402
    from e3_warmstart import PersistentFlowLP
except ImportError:  # highspy not installed -> fall back to cold scipy solves
    PersistentFlowLP = None


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="E3 global layout-flow joint optimization (SA + LNS).")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--production-model", choices=("LVHM", "HVLM"), default="LVHM")
    parser.add_argument("--smat-file", type=Path, default=None)
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/e3_global"))
    parser.add_argument("--horizon-min", type=float, default=10080.0)
    parser.add_argument("--demand-scale", type=float, default=0.25)
    parser.add_argument("--utilization", type=float, default=0.85)
    parser.add_argument("--top-k", type=int, default=12, help="LP arc sparsification (0 = all arcs).")
    parser.add_argument("--edge-length-mode", choices=("manhattan", "euclidean"), default="manhattan")
    parser.add_argument("--max-epochs", type=int, default=100)
    parser.add_argument("--iter-per-epoch", type=int, default=200)
    parser.add_argument("--alpha", type=float, default=0.95)
    parser.add_argument("--t-min", type=float, default=1e-3)
    parser.add_argument("--lp-every", type=int, default=10, help="Refresh the inner LP every K accepted moves.")
    parser.add_argument("--lns-prob", type=float, default=0.15, help="Probability of an LNS shuffle move.")
    parser.add_argument("--lp-time-limit", type=float, default=120.0)
    parser.add_argument(
        "--warm-start",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Use a persistent warm-started HiGHS LP (recommended); --no-warm-start falls back to cold scipy solves.",
    )
    parser.add_argument("--seed", type=int, default=0)
    return parser.parse_args()


def default_smat_file(data_root: Path) -> Path:
    matches = sorted((data_root / "SMAT2022").glob("General Data/**/*.xlsx"))
    if not matches:
        raise FileNotFoundError("No SMAT2022 workbook found.")
    return matches[0]


def size_groups(equipment: list[dict[str, Any]]) -> list[list[int]]:
    """Group equipment indices by footprint class (width x height)."""
    groups: dict[tuple[float, float], list[int]] = defaultdict(list)
    for idx, e in enumerate(equipment):
        key = (round(float(e["width"]), 1), round(float(e["height"]), 1))
        groups[key].append(idx)
    return [g for g in groups.values() if len(g) >= 2]


def load_initial_flows(
    transport_flow_csv: Path, name_to_idx: dict[str, int]
) -> dict[tuple[int, int], float]:
    flows: dict[tuple[int, int], float] = defaultdict(float)
    for row in read_csv(transport_flow_csv):
        s = name_to_idx.get(row.get("source_equipment", ""))
        t = name_to_idx.get(row.get("target_equipment", ""))
        if s is not None and t is not None:
            flows[(s, t)] += float(row.get("flow_lots") or 0.0)
    return dict(flows)


def build_adjacency(F: dict[tuple[int, int], float]) -> tuple[dict[int, list], dict[int, list]]:
    adj_out: dict[int, list] = defaultdict(list)
    adj_in: dict[int, list] = defaultdict(list)
    for (e, e2), flow in F.items():
        if flow > 0:
            adj_out[e].append((e2, flow))
            adj_in[e2].append((e, flow))
    return dict(adj_out), dict(adj_in)


def full_cost(
    assignment: list[int], D: np.ndarray, F: dict[tuple[int, int], float]
) -> float:
    total = 0.0
    for (e, e2), flow in F.items():
        total += flow * float(D[assignment[e], assignment[e2]])
    return total


def delta_swap(
    assignment: list[int],
    i: int,
    j: int,
    D: np.ndarray,
    adj_out: dict[int, list],
    adj_in: dict[int, list],
    F: dict[tuple[int, int], float],
) -> float:
    """Cost delta of swapping the slots of equipment i and j (O(degree))."""
    si, sj = assignment[i], assignment[j]
    delta = 0.0
    for e2, flow in adj_out.get(i, []):
        if e2 == j:
            continue
        delta += flow * (float(D[sj, assignment[e2]]) - float(D[si, assignment[e2]]))
    for e0, flow in adj_in.get(i, []):
        if e0 == j:
            continue
        delta += flow * (float(D[assignment[e0], sj]) - float(D[assignment[e0], si]))
    for e2, flow in adj_out.get(j, []):
        if e2 == i:
            continue
        delta += flow * (float(D[si, assignment[e2]]) - float(D[sj, assignment[e2]]))
    for e0, flow in adj_in.get(j, []):
        if e0 == i:
            continue
        delta += flow * (float(D[assignment[e0], si]) - float(D[assignment[e0], sj]))
    # i <-> j pair (directed distances differ on a directed rail graph)
    delta += F.get((i, j), 0.0) * (float(D[sj, si]) - float(D[si, sj]))
    delta += F.get((j, i), 0.0) * (float(D[si, sj]) - float(D[sj, si]))
    return delta


def lns_shuffle(
    assignment: list[int],
    D: np.ndarray,
    F: dict[tuple[int, int], float],
    groups: list[list[int]],
) -> tuple[list[int], float]:
    """Randomly re-shuffle a subset of one footprint class (LNS destroy-repair)."""
    group = random.choice(groups)
    k = max(2, min(len(group), max(2, int(len(group) * 0.5))))
    devices = random.sample(group, k)
    slots = [assignment[e] for e in devices]
    random.shuffle(slots)
    new_assign = assignment[:]
    for e, s in zip(devices, slots):
        new_assign[e] = s
    delta = full_cost(new_assign, D, F) - full_cost(assignment, D, F)
    return new_assign, delta


def solve_inner_lp(
    assignment: list[int],
    D: np.ndarray,
    operations: list[dict[str, Any]],
    equipment: list[dict[str, Any]],
    utilization: float,
    horizon_min: float,
    top_k: int,
    time_limit: float,
) -> tuple[dict[tuple[int, int], float] | None, float | None, bool]:
    """Solve E1's flow LP under the current assignment; return flows, cost, ok."""
    idx = np.array(assignment, dtype=int)
    distances = D[idx][:, idx]
    builder, y_vars, transitions, _ = build_lp(
        operations, equipment, distances, utilization, horizon_min, top_k
    )
    a_ub, b_ub, a_eq, b_eq = builder.matrices()
    options = {"time_limit": time_limit}
    result = linprog(
        np.asarray(builder.objective),
        A_ub=a_ub,
        b_ub=b_ub,
        A_eq=a_eq,
        b_eq=b_eq,
        bounds=list(zip(builder.lower_bounds, builder.upper_bounds)),
        method="highs",
        options=options,
    )
    if result.x is None:
        return None, None, False

    solution = evaluate_solution(
        result, operations, equipment, y_vars, transitions, horizon_min, utilization
    )
    name_to_idx = {item["name"]: item["index"] for item in equipment}
    F: dict[tuple[int, int], float] = defaultdict(float)
    for row in solution["transport_rows"]:
        s = name_to_idx.get(row["source_equipment"])
        t = name_to_idx.get(row["target_equipment"])
        if s is not None and t is not None:
            F[(s, t)] += float(row["flow_lots"])
    return dict(F), float(result.fun), True


def estimate_initial_temp(
    assignment: list[int],
    D: np.ndarray,
    adj_out: dict[int, list],
    adj_in: dict[int, list],
    F: dict[tuple[int, int], float],
    groups: list[list[int]],
    n_samples: int = 100,
) -> float:
    deltas = []
    for _ in range(n_samples):
        group = random.choice(groups)
        i, j = random.sample(group, 2)
        deltas.append(abs(delta_swap(assignment, i, j, D, adj_out, adj_in, F)))
    if not deltas:
        return 1.0
    return max(sum(deltas) / len(deltas) * 10.0, 1.0)


def main() -> int:
    args = parse_args()
    random.seed(args.seed)
    data_root = args.data_root.resolve()
    smat_path = args.smat_file.resolve() if args.smat_file else default_smat_file(data_root).resolve()
    output_dir = args.output_dir.resolve()

    # 1. Load data, slots (equipment with fixed port/rail), and rail graph.
    log("E3: 加载 SMT/SMAT 数据 ...")
    smt = load_smt(data_root, args.production_model)
    smat = load_smat(smat_path)
    tool_names = {row.get("STN", "") for row in smt["tools"] if row.get("STN")}
    equipment, group_to_indices, _ = equipment_and_ports(smat, tool_names)
    n = len(equipment)
    name_to_idx = {item["name"]: item["index"] for item in equipment}

    log(f"E3: {n} 个可移动设备槽位，构建有向轨道图 ...")
    graph, node_index, rail_meta, _ = build_rail_graph(smat, args.edge_length_mode)

    log("E3: 预计算槽位对真实轨道距离矩阵 ...")
    D, dist_stats = build_equipment_distance_matrix(equipment, rail_meta, node_index, graph)
    log(f"E3: 距离矩阵完成，不可达设备对 {dist_stats['unreachable_equipment_pairs']}")

    # 2. Operations (fixed) and initial flows (from E1 reference LP).
    log("E3: 构建工序 ...")
    operations, demands, _ = build_operations(
        smt, group_to_indices, args.horizon_min, args.demand_scale
    )
    log("E3: 读取 E1 参考流量作为初始流量 ...")
    F = load_initial_flows(args.e1_dir.resolve() / "transport_flow.csv", name_to_idx)
    adj_out, adj_in = build_adjacency(F)

    # 3. Footprint classes for legal swaps.
    groups = size_groups(equipment)
    log(f"E3: {len(groups)} 个可交换尺寸类")

    # 3b. Persistent warm-started HiGHS LP (built once; reused across refreshes).
    persistent_lp = None
    if args.warm_start:
        if PersistentFlowLP is None:
            log("E3: highspy 不可用，回退到 scipy 冷求解 ...")
        else:
            log("E3: 构建持久化 HiGHS LP（warm-start，presolve=off + simplex）...")
            persistent_lp = PersistentFlowLP(
                operations, equipment, D,
                args.utilization, args.horizon_min, args.top_k,
                time_limit=args.lp_time_limit, output_flag=False,
            )

    # 4. Simulated annealing + LNS.
    assignment = list(range(n))
    C = full_cost(assignment, D, F)
    best_assign = assignment[:]
    best_C = C
    log(f"E3: 初始成本 = {C:.1f}（参考布局 + E1 流量）")

    T = estimate_initial_temp(assignment, D, adj_out, adj_in, F, groups)
    log(f"E3: 初始温度 T0 = {T:.3f}")
    t0 = time.perf_counter()
    accept_since_lp = 0
    lp_count = 0

    for epoch in range(args.max_epochs):
        for _ in range(args.iter_per_epoch):
            if random.random() < args.lns_prob:
                new_assign, delta = lns_shuffle(assignment, D, F, groups)
                swapped = None
            else:
                group = random.choice(groups)
                i, j = random.sample(group, 2)
                delta = delta_swap(assignment, i, j, D, adj_out, adj_in, F)
                swapped = (i, j)

            if delta < 0 or random.random() < math.exp(-delta / T):
                if swapped is None:
                    assignment = new_assign
                else:
                    i, j = swapped
                    assignment[i], assignment[j] = assignment[j], assignment[i]
                C += delta
                accept_since_lp += 1
                if C < best_C:
                    best_C = C
                    best_assign = assignment[:]
                if accept_since_lp >= args.lp_every:
                    if persistent_lp is not None:
                        r = persistent_lp.resolve(assignment, D)
                        ok = persistent_lp.has_solution
                        cost_new = r["objective"] if ok else None
                        F_new = persistent_lp.flows() if ok else None
                    else:
                        F_new, cost_new, ok = solve_inner_lp(
                            assignment, D, operations, equipment,
                            args.utilization, args.horizon_min, args.top_k, args.lp_time_limit,
                        )
                    lp_count += 1
                    if ok and F_new is not None:
                        F = F_new
                        adj_out, adj_in = build_adjacency(F)
                        C = cost_new
                        if C < best_C:
                            best_C = C
                            best_assign = assignment[:]
                        log(
                            f"E3: [epoch {epoch}] LP 刷新 #{lp_count}：成本 = {C:.1f}，"
                            f"最优 = {best_C:.1f}"
                        )
                    accept_since_lp = 0

        T *= args.alpha
        log(f"E3: epoch {epoch} 完成，T = {T:.4f}，当前成本 = {C:.1f}，最优 = {best_C:.1f}")
        if T < args.t_min:
            break

    elapsed = time.perf_counter() - t0
    log(f"E3: 搜索完成，耗时 {elapsed:.1f}s，LP 求解 {lp_count} 次")

    # 5. Final precise LP on the best assignment.
    F_final, cost_final, ok = solve_inner_lp(
        best_assign, D, operations, equipment,
        args.utilization, args.horizon_min, 0, args.lp_time_limit,
    )
    if ok and cost_final is not None:
        best_C = cost_final
        F = F_final if F_final is not None else F

    ref_cost = full_cost(list(range(n)), D, load_initial_flows(
        args.e1_dir.resolve() / "transport_flow.csv", name_to_idx
    ))

    # 6. Output.
    layout_rows = []
    for idx, e in enumerate(equipment):
        slot = best_assign[idx]
        layout_rows.append(
            {
                "equipment_name": e["name"],
                "tool_group": e["group"],
                "bay": equipment[slot]["bay"],
                "x": equipment[slot]["position_x"],
                "y": equipment[slot]["position_y"],
                "width": e["width"],
                "height": e["height"],
                "original_slot": idx,
                "new_slot": slot,
            }
        )
    write_csv(
        output_dir / "layout.csv",
        layout_rows,
        ["equipment_name", "tool_group", "bay", "x", "y", "width", "height", "original_slot", "new_slot"],
    )
    summary = {
        "e3_version": "1.0",
        "equipment_count": n,
        "reference_cost": ref_cost,
        "optimized_cost": best_C,
        "cost_reduction": ref_cost - best_C,
        "cost_reduction_pct": 100.0 * (ref_cost - best_C) / ref_cost if ref_cost else 0.0,
        "lp_count": lp_count,
        "elapsed_sec": elapsed,
        "moved": sum(1 for idx in range(n) if best_assign[idx] != idx),
        "distance": dist_stats,
    }
    write_json(output_dir / "e3_summary.json", summary)
    print(
        f"reference_cost={ref_cost:.1f} optimized_cost={best_C:.1f} "
        f"reduction={summary['cost_reduction_pct']:.3f}% moved={summary['moved']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
