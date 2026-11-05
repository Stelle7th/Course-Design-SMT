#!/usr/bin/env python3
"""E2 orchestration: bay ordering (L1) + within-bay layout (L2).

Runs both E2 layers against E1's fixed-flow output, compares the reference
(E1) vs optimized (E2) flow-weighted Manhattan-distance cost, and writes
``new_layout.csv``, ``bay_order.json``/``bay_order.txt``, ``e2_summary.json``
and ``e2_report.md``.
"""

from __future__ import annotations

import argparse
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e2_bay_layout import solve_bay_layout  # noqa: E402
from e2_bay_ordering import solve_bay_ordering  # noqa: E402
from e2_common import (  # noqa: E402
    group_by_bay,
    load_bay_flows,
    load_equipment,
    load_transport_flows,
    log,
    manhattan_cost,
    write_csv,
    write_json,
)


def build_report(summary: dict[str, Any]) -> str:
    bay_infos = summary["bay_infos"]
    lines = []
    for bay in sorted(bay_infos):
        info = bay_infos[bay]
        obj = "-" if info["objective"] is None else f"{info['objective']:,.1f}"
        lines.append(
            f"| {bay} | {info['status']} | {info['equipment_count']} | {obj} |"
        )
    bay_table = "\n".join(lines)

    ranked = summary.get("ranked_bays", [])
    ranked_text = (
        " ".join(f"{i + 1}.{name}" for i, name in enumerate(ranked))
        if ranked
        else "（未求解或已跳过）"
    )

    return f"""# E2 布局优化报告

生成时间：{summary['generated_at_utc']}

## 结果对比（流量 × 曼哈顿距离）

| 指标 | 值 |
|---|---:|
| 设备数量 | {summary['equipment_count']} |
| Bay 数量 | {summary['bay_count']} |
| 参考布局成本 | {summary['baseline_cost_manhattan']:,.1f} |
| 优化布局成本 | {summary['optimized_cost_manhattan']:,.1f} |
| 成本下降 | {summary['cost_reduction']:,.1f} |
| 下降比例 | {summary['cost_reduction_pct']:.2f}% |

## Bay 排序建议（L1）

{ranked_text}

## 各 Bay 求解状态（L2）

| Bay | 状态 | 设备数 | 目标值 |
|---|---:|---:|
{bay_table}

## 说明

- 距离为设备中心的曼哈顿坐标距离，作为搬运距离的布局代理；E1 中真实距离为有向轨道图最短路径。
- 设备限制在原 Bay 包围盒内重排（不跨 Bay），保持 Bay 占地面积不变。
- 流量矩阵固定来自 E1 的 `transport_flow.csv`。
- 完整的「流量 ↔ 布局」交替迭代（重新映射轨道并重跑 E1）为后续工作。

## 输出文件

- `new_layout.csv`：优化后的设备坐标；
- `e2_summary.json`：完整结果与各 Bay 求解信息；
- `bay_order.json` / `bay_order.txt`：Bay 排序建议（L1）。
"""


def main() -> int:
    parser = argparse.ArgumentParser(description="Run the E2 layout optimization.")
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--e0-dir", type=Path, default=Path("output/e0_audit"))
    parser.add_argument("--output-dir", type=Path, default=Path("output/e2_layout"))
    parser.add_argument("--l1-time-limit-sec", type=float, default=30.0)
    parser.add_argument("--l2-time-limit-sec", type=float, default=60.0)
    parser.add_argument("--skip-l1", action="store_true", help="Skip the L1 bay ordering.")
    args = parser.parse_args()

    e1_dir = args.e1_dir.resolve()
    e0_dir = args.e0_dir.resolve()
    output_dir = args.output_dir.resolve()

    log("E2: 读取 E0/E1 产物（设备、设备流量、Bay 流量）...")
    equipment = load_equipment(
        e1_dir / "selected_equipment_ports.csv",
        e0_dir / "equipment_mapping.csv",
    )
    flows = load_transport_flows(e1_dir / "transport_flow.csv")
    bay_flows = load_bay_flows(e1_dir / "from_to_bay.csv")

    baseline_cost = manhattan_cost(equipment, flows)
    log(
        f"E2: 加载完成，设备 {len(equipment)} 台、设备对流量 {len(flows)} 条、"
        f"Bay 流量 {len(bay_flows)} 条；参考成本 = {baseline_cost:.1f}"
    )

    # L1: bay ordering (advisory; does not change the within-bay cost proxy).
    ranked_bays: list[str] = []
    l1_solver: dict[str, Any] = {}
    if not args.skip_l1:
        bay_names = sorted({bay for pair in bay_flows for bay in pair})
        log(f"E2-L1: 求解 {len(bay_names)} 个 Bay 的排序 MILP（时限 {args.l1_time_limit_sec}s）...")
        t0 = time.perf_counter()
        l1 = solve_bay_ordering(bay_names, bay_flows, args.l1_time_limit_sec)
        elapsed = time.perf_counter() - t0
        ranked_bays = l1["ranked_bays"]
        l1_solver = l1["solver"]
        log(
            f"E2-L1: 完成，耗时 {elapsed:.1f}s，状态={l1_solver['status']}，"
            f"目标={l1_solver['objective']}"
        )
    else:
        log("E2-L1: 已跳过（--skip-l1）")
        write_json(
            output_dir / "bay_order.json",
            {
                "e2_l1_version": "1.0",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "bay_count": len(bay_names),
                "solver": l1_solver,
                "bay_ordering": l1["bay_ordering"],
                "ranked_bays": ranked_bays,
                "objective_note": (
                    "Objective is sum over bay pairs of flow * |position difference| "
                    "with unit spacing; it ranks orderings rather than representing "
                    "physical distance."
                ),
            },
        )
        lines = [f"{pos + 1:2d}  {name}" for pos, name in enumerate(ranked_bays)]
        (output_dir / "bay_order.txt").write_text("\n".join(lines) + "\n", encoding="utf-8")

    # L2: within-bay layout.
    by_bay = group_by_bay(equipment)
    bay_names = sorted(by_bay)
    log(f"E2-L2: 逐 Bay 求解布局 MILP，共 {len(bay_names)} 个 Bay ...")
    optimized: list[dict[str, Any]] = []
    bay_infos: dict[str, dict[str, Any]] = {}
    for idx, bay in enumerate(bay_names, start=1):
        items = by_bay[bay]
        original_bay_cost = manhattan_cost(items, flows)
        log(f"E2-L2: [{idx}/{len(bay_names)}] Bay {bay}（{len(items)} 台设备）求解中 ...")
        t0 = time.perf_counter()
        new_items, info = solve_bay_layout(items, flows, args.l2_time_limit_sec)
        elapsed = time.perf_counter() - t0
        info["original_bay_cost"] = original_bay_cost
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
                f"目标={info['objective']:.1f}（原 {original_bay_cost:.1f}）"
            )

    optimized_cost = manhattan_cost(optimized, flows)
    cost_reduction = baseline_cost - optimized_cost
    pct = 100.0 * cost_reduction / baseline_cost if baseline_cost else 0.0
    log(f"E2: 优化成本 = {optimized_cost:.1f}，下降 = {cost_reduction:.1f}（{pct:.2f}%）")

    summary: dict[str, Any] = {
        "e2_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "equipment_count": len(equipment),
        "bay_count": len(by_bay),
        "baseline_cost_manhattan": baseline_cost,
        "optimized_cost_manhattan": optimized_cost,
        "cost_reduction": cost_reduction,
        "cost_reduction_pct": (
            100.0 * cost_reduction / baseline_cost if baseline_cost else 0.0
        ),
        "l1_skip": args.skip_l1,
        "l1_solver": l1_solver,
        "ranked_bays": ranked_bays,
        "bay_infos": bay_infos,
        "distance_note": (
            "Cost is flow * Manhattan coordinate distance (layout proxy). "
            "E1 uses the directed rail-graph shortest path."
        ),
    }
    write_json(output_dir / "e2_summary.json", summary)

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
    (output_dir / "e2_report.md").write_text(build_report(summary), encoding="utf-8")

    print(f"equipment={len(equipment)} bays={len(by_bay)}")
    print(f"baseline_cost={baseline_cost:.1f} optimized_cost={optimized_cost:.1f}")
    print(f"cost_reduction={cost_reduction:.1f} ({summary['cost_reduction_pct']:.2f}%)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
