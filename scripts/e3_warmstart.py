#!/usr/bin/env python3
"""Persistent (warm-started) HiGHS flow LP for E3.

Replaces the "rebuild the LP from scratch + cold solve" inner loop of
``e3_heuristic.solve_inner_lp`` with a single persistent ``highspy.Highs``
model whose *constraint structure never changes* during the search.

Key observation: the flow LP's constraint matrix depends only on the (fixed)
operations + equipment and the transport-arc set; the equipment distances enter
*only* the objective coefficients of the transport-arc columns.  By freezing the
arc set once (``top_k``), every layout swap becomes a pure "change objective
costs + re-solve from the previous basis" operation, which is exactly the
warm-start scenario HiGHS is designed for.
"""

from __future__ import annotations

import time
from collections import defaultdict
from typing import Any

import numpy as np
import highspy
from scipy.sparse import coo_matrix

from e1_reference_lp import build_lp


class PersistentFlowLP:
    """A single HiGHS LP model reused across many E3 layout swaps."""

    def __init__(
        self,
        operations: list[dict[str, Any]],
        equipment: list[dict[str, Any]],
        distances: np.ndarray,
        utilization: float,
        horizon_min: float,
        top_k: int,
        time_limit: float | None = None,
        output_flag: bool = False,
        presolve: str = "off",
        solver: str = "simplex",
    ) -> None:
        self.operations = operations
        self.equipment = equipment
        self.utilization = utilization
        self.horizon_min = horizon_min
        self.top_k = top_k
        self.n = len(equipment)

        # Build the LP structure once with a frozen arc set.
        builder, self.y_vars, transitions, self.model_stats = build_lp(
            operations, equipment, distances, utilization, horizon_min, top_k
        )

        # Transport-arc columns and their (source_equipment, target_equipment).
        self.flow_cols: list[int] = []
        self.flow_pairs: list[tuple[int, int]] = []
        for tr in transitions:
            for arc in tr["arcs"]:
                self.flow_cols.append(int(arc["variable"]))
                self.flow_pairs.append((int(arc["source"]), int(arc["target"])))
        self._flow_cols_i32 = np.asarray(self.flow_cols, dtype=np.int32)
        self._flow_src = np.asarray([p[0] for p in self.flow_pairs], dtype=np.int64)
        self._flow_tgt = np.asarray([p[1] for p in self.flow_pairs], dtype=np.int64)

        # Arcs incident to each equipment index (for sparse cost updates).
        self._incident: list[list[int]] = [[] for _ in range(self.n)]
        for k, (s, t) in enumerate(self.flow_pairs):
            self._incident[s].append(k)
            self._incident[t].append(k)

        # The assignment whose objective costs the model currently encodes.
        self._solved_assignment = list(range(self.n))

        self.highs = self._build_highs(builder)
        self.highs.setOptionValue("output_flag", output_flag)
        self.highs.setOptionValue("log_to_console", output_flag)
        self.highs.setOptionValue("presolve", presolve)
        self.highs.setOptionValue("solver", solver)
        if time_limit is not None:
            self.highs.setOptionValue("time_limit", float(time_limit))

    # ------------------------------------------------------------------ #
    def _build_highs(self, builder: Any) -> highspy.Highs:
        num_col = len(builder.objective)
        num_eq = len(builder.eq_rhs)
        num_ub = len(builder.ub_rhs)
        num_row = num_eq + num_ub

        # Combine equality rows (lower == upper == rhs) and <= rows.
        all_rows = np.concatenate(
            [
                np.asarray(builder.eq_rows, dtype=np.int32),
                np.asarray(builder.ub_rows, dtype=np.int32) + num_eq,
            ]
        )
        all_cols = np.concatenate(
            [
                np.asarray(builder.eq_cols, dtype=np.int32),
                np.asarray(builder.ub_cols, dtype=np.int32),
            ]
        )
        all_vals = np.concatenate(
            [
                np.asarray(builder.eq_values, dtype=np.float64),
                np.asarray(builder.ub_values, dtype=np.float64),
            ]
        )
        a_csc = coo_matrix(
            (all_vals, (all_rows, all_cols)), shape=(num_row, num_col)
        ).tocsc()

        # NOTE: highspy's HighsLp bound/cost attributes are pybind11 properties;
        # slice assignment (e.g. ``lp.row_lower_[:num_eq] = ...``) mutates a
        # temporary copy and does NOT persist.  Build full numpy arrays first,
        # then assign each one in a single whole-array assignment.
        row_lower = np.full(num_row, -highspy.kHighsInf, dtype=np.float64)
        row_upper = np.full(num_row, highspy.kHighsInf, dtype=np.float64)
        row_lower[:num_eq] = np.asarray(builder.eq_rhs, dtype=np.float64)
        row_upper[:num_eq] = np.asarray(builder.eq_rhs, dtype=np.float64)
        row_upper[num_eq:] = np.asarray(builder.ub_rhs, dtype=np.float64)

        lp = highspy.HighsLp()
        lp.num_col_ = num_col
        lp.num_row_ = num_row
        lp.col_cost_ = np.asarray(builder.objective, dtype=np.float64)
        lp.col_lower_ = np.asarray(builder.lower_bounds, dtype=np.float64)
        lp.col_upper_ = np.full(
            num_col, highspy.kHighsInf, dtype=np.float64
        )  # all variables unbounded above (None -> +inf)
        lp.row_lower_ = row_lower
        lp.row_upper_ = row_upper
        lp.sense_ = highspy.ObjSense.kMinimize
        lp.offset_ = 0.0

        sm = highspy.HighsSparseMatrix()
        sm.format_ = highspy.MatrixFormat.kColwise
        sm.num_col_ = num_col
        sm.num_row_ = num_row
        sm.start_ = a_csc.indptr.astype(np.int32)
        sm.index_ = a_csc.indices.astype(np.int32)
        sm.value_ = a_csc.data.astype(np.float64)
        lp.a_matrix_ = sm

        h = highspy.Highs()
        status = h.passModel(lp)
        if status != highspy.HighsStatus.kOk:
            raise RuntimeError(f"passModel failed: {status}")
        return h

    # ------------------------------------------------------------------ #
    def solve(self) -> dict[str, Any]:
        """Cold solve the current model (first call) and return status/obj."""
        t0 = time.perf_counter()
        self.highs.run()
        elapsed = time.perf_counter() - t0
        status = self.highs.getModelStatus()
        obj = self.highs.getObjectiveValue()
        return {"status": status, "objective": obj, "elapsed": elapsed}

    def update_costs(self, assignment: list[int], D: np.ndarray) -> int:
        """Sparse warm-start: update objective costs of only the arcs incident to
        equipment whose slot changed since the last solve.  Returns the number of
        updated columns (0 if the assignment is unchanged)."""
        changed = [
            e for e in range(self.n) if assignment[e] != self._solved_assignment[e]
        ]
        if not changed:
            return 0

        idx = np.asarray(assignment, dtype=np.int64)
        dist = D[idx][:, idx]

        cols = set()
        for e in changed:
            cols.update(self._incident[e])
        cols_arr = np.asarray(sorted(cols), dtype=np.int64)  # positions into flow_pairs
        # changeColsCost expects actual LP column indices (flow_cols[k]), not k.
        lp_cols = self._flow_cols_i32[cols_arr]
        new_costs = dist[self._flow_src[cols_arr], self._flow_tgt[cols_arr]].astype(
            np.float64
        )
        self.highs.changeColsCost(len(cols_arr), lp_cols, new_costs)
        self._solved_assignment = assignment[:]
        return len(cols_arr)

    def resolve(self, assignment: list[int], D: np.ndarray) -> dict[str, Any]:
        """Update costs for the current assignment (sparse) then re-solve (warm)."""
        n_updated = self.update_costs(assignment, D)
        t0 = time.perf_counter()
        self.highs.run()
        elapsed = time.perf_counter() - t0
        status = self.highs.getModelStatus()
        obj = self.highs.getObjectiveValue()
        return {
            "status": status,
            "objective": obj,
            "elapsed": elapsed,
            "updated_columns": n_updated,
        }

    def flows(self) -> dict[tuple[int, int], float]:
        """Extract the equipment-pair flow dict F from the current solution."""
        sol = self.highs.getSolution()
        x = sol.col_value
        F: dict[tuple[int, int], float] = defaultdict(float)
        for (s, t), col in zip(self.flow_pairs, self.flow_cols):
            val = float(x[col])
            if val > 1e-8:
                F[(s, t)] += val
        return dict(F)

    @property
    def is_optimal(self) -> bool:
        return self.highs.getModelStatus() == highspy.HighsModelStatus.kOptimal

    @property
    def has_solution(self) -> bool:
        try:
            return bool(self.highs.getSolution().value_valid)
        except Exception:
            return False


def _random_group_swap(assignment: list[int], groups: list[list[int]], seed: int = 1) -> list[int]:
    import random

    rng = random.Random(seed)
    new = assignment[:]
    for _ in range(5):
        group = rng.choice(groups)
        i, j = rng.sample(group, 2)
        new[i], new[j] = new[j], new[i]
    return new


if __name__ == "__main__":
    import sys
    from pathlib import Path

    sys.path.insert(0, str(Path(__file__).resolve().parent))

    from e0_data_audit import load_smat, load_smt
    from e1_reference_lp import (
        build_equipment_distance_matrix,
        build_operations,
        build_rail_graph,
        equipment_and_ports,
    )
    from e3_heuristic import size_groups

    data_root = Path(sys.argv[1]) if len(sys.argv) > 1 else Path("data")
    model = sys.argv[2] if len(sys.argv) > 2 else "LVHM"
    top_k = int(sys.argv[3]) if len(sys.argv) > 3 else 12

    smt = load_smt(data_root, model)
    smat = load_smat(
        sorted((data_root / "SMAT2022").glob("General Data/**/*.xlsx"))[0]
    )
    tool_names = {row.get("STN", "") for row in smt["tools"] if row.get("STN")}
    equipment, group_to_indices, _ = equipment_and_ports(smat, tool_names)
    graph, node_index, rail_meta, _ = build_rail_graph(smat, "manhattan")
    D, _ = build_equipment_distance_matrix(equipment, rail_meta, node_index, graph)
    operations, _, _ = build_operations(smt, group_to_indices, 10080.0, 0.25)
    groups = size_groups(equipment)
    n = len(equipment)

    print(f"构建持久化 LP（top_k={top_k}, presolve=off, simplex）...", flush=True)
    lp = PersistentFlowLP(
        operations, equipment, D, 0.85, 10080.0, top_k=top_k, output_flag=False
    )
    print(
        f"  变量 {lp.model_stats['variable_count']:,} / 等式 {lp.model_stats['equality_count']:,} "
        f"/ 不等式 {lp.model_stats['inequality_count']:,} / 弧 {lp.model_stats['transport_arc_count']:,}",
        flush=True,
    )

    r0 = lp.solve()
    print(
        f"冷求解(初始布局): obj={r0['objective']:.1f} 耗时={r0['elapsed']:.2f}s 状态={r0['status']}",
        flush=True,
    )

    # 随机扰动布局后稀疏热求解
    assignment = _random_group_swap(list(range(n)), groups)
    r1 = lp.resolve(assignment, D)
    print(
        f"热求解(扰动布局, 更新 {r1['updated_columns']:,} 列): "
        f"obj={r1['objective']:.1f} 耗时={r1['elapsed']:.2f}s 状态={r1['status']}",
        flush=True,
    )

    # 对照：对同一扰动布局做全新冷求解（含 build）
    idx = np.asarray(assignment, dtype=np.int64)
    dist = D[idx][:, idx]
    t0 = time.perf_counter()
    lp2 = PersistentFlowLP(
        operations, equipment, dist, 0.85, 10080.0, top_k=top_k, output_flag=False
    )
    r2 = lp2.solve()
    t_build_solve = time.perf_counter() - t0
    print(
        f"冷求解(同扰动布局): obj={r2['objective']:.1f} 耗时={t_build_solve:.2f}s 状态={r2['status']}",
        flush=True,
    )
    print(
        f"热/冷目标差 = {abs(r1['objective'] - r2['objective']):.2e}  "
        f"(匹配={abs(r1['objective'] - r2['objective']) < 1e-3})",
        flush=True,
    )
    print(
        f"加速比(热 vs 冷求解) ≈ {t_build_solve / r1['elapsed']:.1f}x",
        flush=True,
    )
