#!/usr/bin/env python3
"""E1 reference-layout LP for the SMT2020/SMAT2022 layout study.

The model fixes the current SMAT2022 equipment placement and optimizes only
aggregated deterministic production and transport flows. Equipment locations
are represented by one selected equipment port and transport distances are
computed on the directed rail graph.
"""

from __future__ import annotations

import argparse
import csv
import json
import math
import sys
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

import numpy as np
from scipy.optimize import linprog
from scipy.sparse import coo_matrix, csr_matrix
from scipy.sparse.csgraph import dijkstra

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e0_data_audit import (  # noqa: E402
    FIXED_AMHS_GROUPS,
    load_smat,
    load_smt,
    numeric,
    resolve_name,
)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Solve the E1 reference-layout LP.")
    parser.add_argument("--data-root", type=Path, default=Path("data"))
    parser.add_argument("--production-model", choices=("LVHM", "HVLM"), default="LVHM")
    parser.add_argument("--smat-file", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--horizon-min", type=float, default=10080.0)
    parser.add_argument("--demand-scale", type=float, default=0.25)
    parser.add_argument("--utilization", type=float, default=0.85)
    parser.add_argument(
        "--top-k",
        type=int,
        default=12,
        help="Keep this many nearest destination devices per source device. 0 keeps all arcs.",
    )
    parser.add_argument(
        "--edge-length-mode",
        choices=("manhattan", "euclidean"),
        default="manhattan",
        help="Coordinate distance used for each rail edge.",
    )
    parser.add_argument(
        "--time-limit-sec",
        type=float,
        default=None,
        help="Optional HiGHS time limit.",
    )
    return parser.parse_args()


def default_smat_file(data_root: Path) -> Path:
    matches = sorted((data_root / "SMAT2022").glob("General Data/**/*.xlsx"))
    if not matches:
        raise FileNotFoundError("No SMAT2022 workbook found.")
    return matches[0]


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        writer.writerows({field: row.get(field, "") for field in fields} for row in rows)


def equipment_and_ports(
    smat: dict[str, list[dict[str, Any]]],
    tool_names: set[str],
) -> tuple[list[dict[str, Any]], dict[str, int], list[str]]:
    equipment_by_name = {
        str(row.get("NAME")): row
        for row in smat["Equipment"]
        if row.get("NAME")
    }
    ports_by_equipment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for port in smat["Port"]:
        equipment = str(port.get("EQP_NAME") or "").strip()
        if equipment in equipment_by_name:
            ports_by_equipment[equipment].append(port)

    equipment: list[dict[str, Any]] = []
    group_to_indices: dict[str, list[int]] = defaultdict(list)
    warnings: list[str] = []
    for name, row in sorted(equipment_by_name.items()):
        raw_group = str(row.get("TOOL_GROUP") or "").strip()
        is_fixed = raw_group in FIXED_AMHS_GROUPS
        if is_fixed:
            continue
        mapped_group, reason = resolve_name(raw_group, tool_names)
        if not mapped_group:
            warnings.append(f"Unmapped movable equipment group: {raw_group}")
            continue
        ports = ports_by_equipment.get(name, [])
        if not ports:
            warnings.append(f"Equipment has no port: {name}")
            continue
        preferred = [port for port in ports if port.get("PORT_TYPE") == "EQPPort"]
        selected = sorted(preferred or ports, key=lambda port: str(port.get("NAME", "")))[0]
        equipment_index = len(equipment)
        equipment.append(
            {
                "index": equipment_index,
                "name": name,
                "raw_group": raw_group,
                "group": mapped_group,
                "bay": str(row.get("BAY") or ""),
                "width": numeric(row.get("WIDTH")),
                "height": numeric(row.get("HEIGHT")),
                "position_x": numeric(row.get("POSITION_X")),
                "position_y": numeric(row.get("POSITION_Y")),
                "port_name": str(selected.get("NAME") or ""),
                "port_type": str(selected.get("PORT_TYPE") or ""),
                "rail_name": str(selected.get("RAILLINE_NAME") or ""),
                "port_distance": numeric(selected.get("DISTANCE")),
                "port_selection": "EQPPort" if preferred else "first_available",
            }
        )
        group_to_indices[mapped_group].append(equipment_index)
    return equipment, dict(group_to_indices), warnings


def build_rail_graph(
    smat: dict[str, list[dict[str, Any]]],
    edge_length_mode: str,
) -> tuple[csr_matrix, dict[str, int], dict[str, dict[str, Any]], dict[str, int]]:
    node_rows = [row for row in smat["Address"] if row.get("NAME")]
    node_names = [str(row["NAME"]) for row in node_rows]
    node_index = {name: index for index, name in enumerate(node_names)}
    edges: list[tuple[int, int, float]] = []
    rail_meta: dict[str, dict[str, Any]] = {}
    bad_edges = 0
    for row in smat["Rail"]:
        rail_name = str(row.get("NAME") or "")
        source_name = str(row.get("FROM_NODE") or "")
        target_name = str(row.get("TO_NODE") or "")
        if source_name not in node_index or target_name not in node_index:
            bad_edges += 1
            continue
        source = node_rows[node_index[source_name]]
        target = node_rows[node_index[target_name]]
        x1, y1 = numeric(source.get("POSITION_X")), numeric(source.get("POSITION_Y"))
        x2, y2 = numeric(target.get("POSITION_X")), numeric(target.get("POSITION_Y"))
        if None in (x1, y1, x2, y2):
            bad_edges += 1
            continue
        if edge_length_mode == "manhattan":
            length = abs(x2 - x1) + abs(y2 - y1)
        else:
            length = math.hypot(x2 - x1, y2 - y1)
        if length <= 0:
            bad_edges += 1
            continue
        edges.append((node_index[source_name], node_index[target_name], length))
        rail_meta[rail_name] = {
            "from_node": source_name,
            "to_node": target_name,
            "length": length,
        }
    graph = coo_matrix(
        (
            [edge[2] for edge in edges],
            ([edge[0] for edge in edges], [edge[1] for edge in edges]),
        ),
        shape=(len(node_names), len(node_names)),
    ).tocsr()
    return graph, node_index, rail_meta, {"bad_edges": bad_edges}


def build_equipment_distance_matrix(
    equipment: list[dict[str, Any]],
    rail_meta: dict[str, dict[str, Any]],
    node_index: dict[str, int],
    graph: csr_matrix,
) -> tuple[np.ndarray, dict[str, Any]]:
    count = len(equipment)
    out_nodes = np.full(count, -1, dtype=np.int64)
    in_nodes = np.full(count, -1, dtype=np.int64)
    out_offsets = np.full(count, np.inf, dtype=float)
    in_offsets = np.full(count, np.inf, dtype=float)
    missing = []
    for item in equipment:
        index = item["index"]
        rail = rail_meta.get(item["rail_name"])
        position = item["port_distance"]
        if rail is None or position is None:
            missing.append(item["name"])
            continue
        position = min(max(float(position), 0.0), float(rail["length"]))
        item["port_distance_clamped"] = position
        out_node = node_index[rail["to_node"]]
        in_node = node_index[rail["from_node"]]
        out_nodes[index] = out_node
        in_nodes[index] = in_node
        out_offsets[index] = float(rail["length"]) - position
        in_offsets[index] = position

    valid = [index for index in range(count) if out_nodes[index] >= 0]
    distance_from_source = dijkstra(
        graph,
        directed=True,
        indices=sorted({int(out_nodes[index]) for index in valid}),
    )
    source_row = {
        node: row for row, node in enumerate(sorted({int(out_nodes[index]) for index in valid}))
    }
    distance_matrix = np.full((count, count), np.inf, dtype=float)
    for source in valid:
        row = distance_from_source[source_row[int(out_nodes[source])]]
        targets = np.asarray(in_nodes, dtype=np.int64)
        reachable = targets >= 0
        values = np.full(count, np.inf, dtype=float)
        values[reachable] = (
            out_offsets[source]
            + row[targets[reachable]]
            + in_offsets[reachable]
        )
        distance_matrix[source, :] = values

    # A direct movement on the same directed rail edge can be shorter than
    # leaving the edge and re-entering it through the graph.
    for source in valid:
        source_item = equipment[source]
        for target in valid:
            target_item = equipment[target]
            if source_item["rail_name"] == target_item["rail_name"]:
                source_pos = source_item["port_distance_clamped"]
                target_pos = target_item["port_distance_clamped"]
                if target_pos >= source_pos:
                    distance_matrix[source, target] = min(
                        distance_matrix[source, target],
                        target_pos - source_pos,
                    )
    unreachable = int(np.isinf(distance_matrix).sum())
    return distance_matrix, {
        "equipment_count": count,
        "missing_port_path": missing,
        "unreachable_equipment_pairs": unreachable,
        "reachable_equipment_pairs": count * count - unreachable,
    }


def order_rates(
    orders: list[dict[str, str]],
) -> tuple[dict[str, float], dict[str, float], list[str]]:
    rates: defaultdict[str, float] = defaultdict(float)
    pieces: dict[str, float] = {}
    warnings: list[str] = []
    for row in orders:
        part = row.get("PART", "")
        repeat = numeric(row.get("REPEAT"))
        lots_per_repeat = numeric(row.get("LOTSPERRPT"))
        part_pieces = numeric(row.get("PIECES"))
        if not part or repeat is None or repeat <= 0 or lots_per_repeat is None:
            warnings.append(f"Invalid order rate row: {row.get('LOT', '')}")
            continue
        rates[part] += lots_per_repeat / repeat
        if part_pieces is not None:
            if part in pieces and not math.isclose(pieces[part], part_pieces):
                warnings.append(f"Multiple PIECES values for {part}")
            pieces.setdefault(part, part_pieces)
    return dict(rates), pieces, warnings


def build_operations(
    smt: dict[str, Any],
    group_to_indices: dict[str, list[int]],
    horizon_min: float,
    demand_scale: float,
) -> tuple[list[dict[str, Any]], dict[str, float], list[str]]:
    rates, pieces_by_part, warnings = order_rates(smt["orders"])
    part_to_route = {
        row["PART"]: row for row in smt["parts"] if row.get("PART")
    }
    operations: list[dict[str, Any]] = []
    demands = {
        part: demand_scale * rate * horizon_min
        for part, rate in rates.items()
    }
    for part, part_row in part_to_route.items():
        route_file = Path(smt["directory"]) / part_row["ROUTEFILE"]
        route_rows = []
        with route_file.open("r", encoding="latin1", newline="") as handle:
            route_rows = list(csv.DictReader(handle, delimiter="\t"))
        for row in route_rows:
            raw_family = row.get("STNFAM", "")
            if raw_family.casefold().startswith("delay"):
                continue
            group, _ = resolve_name(raw_family, set(group_to_indices))
            devices = group_to_indices.get(group, [])
            if not devices:
                raise ValueError(
                    f"No reference-layout equipment for route family {raw_family} in {part}."
                )
            ptime = numeric(row.get("PTIME"))
            if ptime is None:
                raise ValueError(f"Missing PTIME in {part}/{part_row['ROUTEFILE']} step {row.get('STEP')}")
            ptper = row.get("PTPER", "")
            piece_count = pieces_by_part.get(part, 25.0)
            if ptper == "per_piece":
                tau = ptime * piece_count
            elif ptper == "per_batch":
                batch_min = numeric(row.get("BATCHMN"))
                batch_max = numeric(row.get("BATCHMX"))
                if batch_min is None or batch_max is None or batch_min <= 0 or batch_max <= 0:
                    raise ValueError(
                        f"Invalid batch bounds in {part}/{part_row['ROUTEFILE']} step {row.get('STEP')}"
                    )
                tau = ptime * piece_count / ((batch_min + batch_max) / 2.0)
            elif ptper == "per_lot":
                tau = ptime
            else:
                warnings.append(
                    f"Unknown PTPER={ptper!r} in {part}/{part_row['ROUTEFILE']} step {row.get('STEP')}; using PTIME."
                )
                tau = ptime
            operations.append(
                {
                    "operation_index": len(operations),
                    "part": part,
                    "route": part_row["ROUTE"],
                    "route_file": part_row["ROUTEFILE"],
                    "step": int(row.get("STEP") or 0),
                    "desc": row.get("DESC", ""),
                    "raw_stnfam": raw_family,
                    "stnfam": group,
                    "ptper": ptper,
                    "ptime": ptime,
                    "tau_per_lot": tau,
                    "demand_lots": demands.get(part, 0.0),
                    "devices": devices,
                }
            )
    return operations, demands, warnings


class LPBuilder:
    def __init__(self) -> None:
        self.objective: list[float] = []
        self.lower_bounds: list[float] = []
        self.upper_bounds: list[float | None] = []
        self.eq_rows: list[int] = []
        self.eq_cols: list[int] = []
        self.eq_values: list[float] = []
        self.eq_rhs: list[float] = []
        self.ub_rows: list[int] = []
        self.ub_cols: list[int] = []
        self.ub_values: list[float] = []
        self.ub_rhs: list[float] = []

    def variable(self, objective: float = 0.0) -> int:
        index = len(self.objective)
        self.objective.append(objective)
        self.lower_bounds.append(0.0)
        self.upper_bounds.append(None)
        return index

    def add_eq(self, coefficients: dict[int, float], rhs: float) -> int:
        row = len(self.eq_rhs)
        for col, value in coefficients.items():
            if value:
                self.eq_rows.append(row)
                self.eq_cols.append(col)
                self.eq_values.append(value)
        self.eq_rhs.append(rhs)
        return row

    def add_ub(self, coefficients: dict[int, float], rhs: float) -> int:
        row = len(self.ub_rhs)
        for col, value in coefficients.items():
            if value:
                self.ub_rows.append(row)
                self.ub_cols.append(col)
                self.ub_values.append(value)
        self.ub_rhs.append(rhs)
        return row

    def matrices(self) -> tuple[csr_matrix | None, np.ndarray | None, csr_matrix | None, np.ndarray | None]:
        n = len(self.objective)
        a_eq = None
        if self.eq_rhs:
            a_eq = coo_matrix(
                (self.eq_values, (self.eq_rows, self.eq_cols)),
                shape=(len(self.eq_rhs), n),
            ).tocsr()
        a_ub = None
        if self.ub_rhs:
            a_ub = coo_matrix(
                (self.ub_values, (self.ub_rows, self.ub_cols)),
                shape=(len(self.ub_rhs), n),
            ).tocsr()
        return a_ub, np.asarray(self.ub_rhs), a_eq, np.asarray(self.eq_rhs)


def build_lp(
    operations: list[dict[str, Any]],
    equipment: list[dict[str, Any]],
    distances: np.ndarray,
    utilization: float,
    horizon_min: float,
    top_k: int,
) -> tuple[LPBuilder, dict[tuple[int, int], int], list[dict[str, Any]], dict[str, Any]]:
    builder = LPBuilder()
    y_vars: dict[tuple[int, int], int] = {}
    for operation in operations:
        for equipment_index in operation["devices"]:
            y_vars[(operation["operation_index"], equipment_index)] = builder.variable()

    transition_records: list[dict[str, Any]] = []
    arc_count = 0
    for operation_index, operation in enumerate(operations):
        demand_coefficients = {
            y_vars[(operation_index, equipment_index)]: 1.0
            for equipment_index in operation["devices"]
        }
        builder.add_eq(demand_coefficients, operation["demand_lots"])
        if (
            operation_index == len(operations) - 1
            or operations[operation_index + 1]["part"] != operation["part"]
        ):
            continue
        next_operation = operations[operation_index + 1]
        source_devices = operation["devices"]
        target_devices = next_operation["devices"]
        transition = {
            "part": operation["part"],
            "route": operation["route"],
            "step_from": operation["step"],
            "step_to": next_operation["step"],
            "source_operation_index": operation_index,
            "target_operation_index": operation_index + 1,
            "arcs": [],
        }
        out_rows: dict[int, dict[int, float]] = defaultdict(dict)
        in_rows: dict[int, dict[int, float]] = defaultdict(dict)
        arc_pairs: set[tuple[int, int]] = set()
        for source in source_devices:
            candidates = [
                target
                for target in target_devices
                if math.isfinite(distances[source, target])
            ]
            candidates.sort(key=lambda target: (distances[source, target], target))
            if top_k > 0:
                candidates = candidates[:top_k]
            arc_pairs.update((source, target) for target in candidates)
        if top_k > 0:
            # A source-side-only truncation can leave some target devices with
            # no incoming arc, which makes the flow-balance equations infeasible.
            # Add each target's nearest source as well.
            for target in target_devices:
                candidates = [
                    source
                    for source in source_devices
                    if math.isfinite(distances[source, target])
                ]
                candidates.sort(key=lambda source: (distances[source, target], source))
                arc_pairs.update((source, target) for source in candidates[:top_k])
        for source, target in sorted(arc_pairs):
            flow_var = builder.variable(float(distances[source, target]))
            out_rows[source][flow_var] = 1.0
            in_rows[target][flow_var] = 1.0
            transition["arcs"].append(
                {
                    "source": source,
                    "target": target,
                    "variable": flow_var,
                    "distance": float(distances[source, target]),
                }
            )
            arc_count += 1
        for source in source_devices:
            coefficients = dict(out_rows[source])
            coefficients[y_vars[(operation_index, source)]] = -1.0
            builder.add_eq(coefficients, 0.0)
        for target in target_devices:
            coefficients = dict(in_rows[target])
            coefficients[y_vars[(operation_index + 1, target)]] = -1.0
            builder.add_eq(coefficients, 0.0)
        transition_records.append(transition)

    capacity_rows = 0
    for equipment_item in equipment:
        coefficients = {}
        for operation in operations:
            variable = y_vars.get((operation["operation_index"], equipment_item["index"]))
            if variable is not None:
                coefficients[variable] = operation["tau_per_lot"]
        if coefficients:
            builder.add_ub(coefficients, horizon_min * utilization)
            capacity_rows += 1

    return builder, y_vars, transition_records, {
        "variable_count": len(builder.objective),
        "equality_count": len(builder.eq_rhs),
        "inequality_count": len(builder.ub_rhs),
        "transport_arc_count": arc_count,
        "capacity_row_count": capacity_rows,
    }


def nonzero(value: float, tolerance: float = 1e-8) -> bool:
    return abs(float(value)) > tolerance


def evaluate_solution(
    result: Any,
    operations: list[dict[str, Any]],
    equipment: list[dict[str, Any]],
    y_vars: dict[tuple[int, int], int],
    transitions: list[dict[str, Any]],
    horizon_min: float,
    utilization: float,
) -> dict[str, Any]:
    values = result.x
    operation_rows = []
    operation_totals: dict[int, float] = {}
    device_load = Counter()
    for operation in operations:
        total = 0.0
        for equipment_index in operation["devices"]:
            value = float(values[y_vars[(operation["operation_index"], equipment_index)]])
            total += value
            if nonzero(value):
                item = equipment[equipment_index]
                machine_time = value * operation["tau_per_lot"]
                operation_rows.append(
                    {
                        "part": operation["part"],
                        "route": operation["route"],
                        "step": operation["step"],
                        "desc": operation["desc"],
                        "stnfam": operation["stnfam"],
                        "equipment_name": item["name"],
                        "bay": item["bay"],
                        "flow_lots": value,
                        "tau_per_lot_min": operation["tau_per_lot"],
                        "machine_time_min": machine_time,
                    }
                )
                device_load[equipment_index] += machine_time
        operation_totals[operation["operation_index"]] = total

    transport_rows = []
    from_to = Counter()
    flow_by_bay = Counter()
    for transition in transitions:
        source_operation = operations[transition["source_operation_index"]]
        target_operation = operations[transition["target_operation_index"]]
        for arc in transition["arcs"]:
            flow = float(values[arc["variable"]])
            if not nonzero(flow):
                continue
            source_item = equipment[arc["source"]]
            target_item = equipment[arc["target"]]
            cost = flow * arc["distance"]
            from_to[(source_item["bay"], target_item["bay"])] += flow
            flow_by_bay[source_item["bay"]] += flow
            transport_rows.append(
                {
                    "part": transition["part"],
                    "route": transition["route"],
                    "step_from": transition["step_from"],
                    "step_to": transition["step_to"],
                    "source_equipment": source_item["name"],
                    "target_equipment": target_item["name"],
                    "source_bay": source_item["bay"],
                    "target_bay": target_item["bay"],
                    "flow_lots": flow,
                    "path_distance": arc["distance"],
                    "transport_cost": cost,
                    "source_desc": source_operation["desc"],
                    "target_desc": target_operation["desc"],
                }
            )

    utilization_rows = []
    for item in equipment:
        load = device_load[item["index"]]
        utilization_rows.append(
            {
                "equipment_name": item["name"],
                "tool_group": item["group"],
                "bay": item["bay"],
                "available_time_min": horizon_min * utilization,
                "load_min": load,
                "utilization": load / (horizon_min * utilization),
            }
        )

    max_operation_residual = max(
        (abs(total - operations[index]["demand_lots"]) for index, total in operation_totals.items()),
        default=0.0,
    )
    max_capacity_excess = max(
        (row["load_min"] - row["available_time_min"] for row in utilization_rows),
        default=0.0,
    )
    return {
        "operation_rows": operation_rows,
        "transport_rows": transport_rows,
        "utilization_rows": utilization_rows,
        "from_to_rows": [
            {"source_bay": source, "target_bay": target, "flow_lots": flow}
            for (source, target), flow in sorted(from_to.items())
        ],
        "bay_flow_rows": [
            {"bay": bay, "outgoing_flow_lots": flow}
            for bay, flow in sorted(flow_by_bay.items())
        ],
        "max_operation_demand_residual": max_operation_residual,
        "max_capacity_excess_min": max_capacity_excess,
        "max_device_utilization": max(
            (row["utilization"] for row in utilization_rows),
            default=0.0,
        ),
        "nonzero_operation_assignments": len(operation_rows),
        "nonzero_transport_arcs": len(transport_rows),
    }


def report_markdown(summary: dict[str, Any]) -> str:
    checks = summary["checks"]
    check_lines = "\n".join(
        f"- [{'x' if value else ' '}] {name}" for name, value in checks.items()
    )
    return f"""# E1 参考布局 LP 报告

生成时间：{summary['generated_at_utc']}

## 运行配置

- 生产模型：`{summary['production_model']}`
- SMAT2022 文件：`{summary['smat_workbook']}`
- 规划周期：{summary['horizon_min']} 分钟
- 需求缩放系数：{summary['demand_scale']}
- 设备有效机时系数：{summary['utilization']}
- 轨道边长度：`{summary['edge_length_mode']}`
- 每个源设备保留的目标设备数：{summary['top_k']}（0 表示全部）

## 求解结果

- 求解状态：`{summary['solver_status']}`
- 求解消息：{summary['solver_message']}
- 目标值：{summary['objective_value']}
- 变量数：{summary['model']['variable_count']}
- 等式约束数：{summary['model']['equality_count']}
- 不等式约束数：{summary['model']['inequality_count']}
- 运输弧数：{summary['model']['transport_arc_count']}

## 可行性检查

{check_lines}

- 最大工序需求守恒残差：{summary['solution']['max_operation_demand_residual']}
- 最大设备产能超限：{summary['solution']['max_capacity_excess_min']}
- 最大设备利用率：{summary['solution']['max_device_utilization']}
- 非零工序设备分配数：{summary['solution']['nonzero_operation_assignments']}
- 非零运输弧数：{summary['solution']['nonzero_transport_arcs']}

## 数据提示

- 路线中的 `Delay_32` 被视为非设备延迟节点，从设备位置和运输弧建模中跳过。
- `per_piece` 按产品的 `PIECES` 转换为每 lot 时间。
- `per_batch` 使用 `(BATCHMN+BATCHMX)/2` 作为代表批量。
- 设备位置使用每台设备选择的 `EQPPort`，若无该类型端口则使用排序后的第一个可用端口。
- `top_k` 会对完整设备对设备运输弧进行稀疏化。若结果不可行，应增加 `top_k` 或在小规模实例使用 `--top-k 0`。
- 本报告中的 LP 只处理确定性聚合流量，不包含故障、换型、排队和车辆冲突。

## 输出文件

- `e1_summary.json`：完整运行配置、求解状态和检查结果；
- `operation_flow.csv`：工序到参考布局设备的加工流量；
- `transport_flow.csv`：相邻工序间的运输流量；
- `from_to_bay.csv`：Bay 间 From-To 流量；
- `bay_flow.csv`：各 Bay 的出发流量；
- `device_utilization.csv`：设备负载和利用率；
- `selected_equipment_ports.csv`：每台设备用于距离计算的代表端口；
- `e1_report.md`：本报告。
"""


def main() -> int:
    args = parse_args()
    data_root = args.data_root.resolve()
    smat_path = args.smat_file.resolve() if args.smat_file else default_smat_file(data_root).resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    smt = load_smt(data_root, args.production_model)
    smat = load_smat(smat_path)
    tool_names = {row.get("STN", "") for row in smt["tools"] if row.get("STN")}
    equipment, group_to_indices, equipment_warnings = equipment_and_ports(smat, tool_names)
    graph, node_index, rail_meta, graph_stats = build_rail_graph(smat, args.edge_length_mode)
    distances, distance_stats = build_equipment_distance_matrix(
        equipment,
        rail_meta,
        node_index,
        graph,
    )
    operations, demands, operation_warnings = build_operations(
        smt,
        group_to_indices,
        args.horizon_min,
        args.demand_scale,
    )
    builder, y_vars, transitions, model_stats = build_lp(
        operations,
        equipment,
        distances,
        args.utilization,
        args.horizon_min,
        args.top_k,
    )
    a_ub, b_ub, a_eq, b_eq = builder.matrices()
    options = {}
    if args.time_limit_sec is not None:
        options["time_limit"] = args.time_limit_sec
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

    checks = {
        "solver_found_feasible_solution": bool(result.success and result.x is not None),
        "all_operations_have_positive_demand": all(
            operation["demand_lots"] > 0 for operation in operations
        ),
        "all_operations_have_eligible_equipment": all(
            bool(operation["devices"]) for operation in operations
        ),
        "all_selected_paths_reachable": distance_stats["unreachable_equipment_pairs"] == 0,
    }
    solution = {
        "operation_rows": [],
        "transport_rows": [],
        "utilization_rows": [],
        "from_to_rows": [],
        "bay_flow_rows": [],
        "max_operation_demand_residual": None,
        "max_capacity_excess_min": None,
        "max_device_utilization": None,
        "nonzero_operation_assignments": 0,
        "nonzero_transport_arcs": 0,
    }
    objective_value = None
    if result.x is not None:
        solution = evaluate_solution(
            result,
            operations,
            equipment,
            y_vars,
            transitions,
            args.horizon_min,
            args.utilization,
        )
        checks["order_and_flow_residuals_within_tolerance"] = (
            solution["max_operation_demand_residual"] <= 1e-5
        )
        checks["capacity_within_tolerance"] = solution["max_capacity_excess_min"] <= 1e-5
        objective_value = float(result.fun)
    else:
        checks["order_and_flow_residuals_within_tolerance"] = False
        checks["capacity_within_tolerance"] = False

    selected_ports = [
        {
            "equipment_name": item["name"],
            "tool_group": item["group"],
            "bay": item["bay"],
            "port_name": item["port_name"],
            "port_type": item["port_type"],
            "rail_name": item["rail_name"],
            "port_distance": item["port_distance"],
            "port_distance_clamped": item.get("port_distance_clamped", ""),
            "port_selection": item["port_selection"],
            "position_x": item["position_x"],
            "position_y": item["position_y"],
        }
        for item in equipment
    ]
    summary = {
        "e1_version": "1.0",
        "generated_at_utc": __import__("datetime").datetime.now(__import__("datetime").timezone.utc).isoformat(),
        "production_model": str(Path(smt["directory"])),
        "smat_workbook": str(smat_path),
        "horizon_min": args.horizon_min,
        "demand_scale": args.demand_scale,
        "utilization": args.utilization,
        "top_k": args.top_k,
        "edge_length_mode": args.edge_length_mode,
        "solver": "scipy.optimize.linprog(method='highs')",
        "solver_status": int(result.status),
        "solver_success": bool(result.success),
        "solver_message": str(result.message),
        "objective_value": objective_value,
        "model": model_stats,
        "equipment_count": len(equipment),
        "operation_count": len(operations),
        "product_demands_lots": demands,
        "warnings": equipment_warnings + operation_warnings,
        "graph": graph_stats,
        "distance": distance_stats,
        "checks": checks,
        "checks_passed": all(checks.values()),
        "solution": solution,
    }

    write_csv(
        output_dir / "operation_flow.csv",
        solution["operation_rows"],
        [
            "part",
            "route",
            "step",
            "desc",
            "stnfam",
            "equipment_name",
            "bay",
            "flow_lots",
            "tau_per_lot_min",
            "machine_time_min",
        ],
    )
    write_csv(
        output_dir / "transport_flow.csv",
        solution["transport_rows"],
        [
            "part",
            "route",
            "step_from",
            "step_to",
            "source_equipment",
            "target_equipment",
            "source_bay",
            "target_bay",
            "flow_lots",
            "path_distance",
            "transport_cost",
            "source_desc",
            "target_desc",
        ],
    )
    write_csv(
        output_dir / "from_to_bay.csv",
        solution["from_to_rows"],
        ["source_bay", "target_bay", "flow_lots"],
    )
    write_csv(
        output_dir / "bay_flow.csv",
        solution["bay_flow_rows"],
        ["bay", "outgoing_flow_lots"],
    )
    write_csv(
        output_dir / "device_utilization.csv",
        solution["utilization_rows"],
        ["equipment_name", "tool_group", "bay", "available_time_min", "load_min", "utilization"],
    )
    write_csv(
        output_dir / "selected_equipment_ports.csv",
        selected_ports,
        [
            "equipment_name",
            "tool_group",
            "bay",
            "port_name",
            "port_type",
            "rail_name",
            "port_distance",
            "port_distance_clamped",
            "port_selection",
            "position_x",
            "position_y",
        ],
    )
    (output_dir / "e1_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "e1_report.md").write_text(
        report_markdown(summary),
        encoding="utf-8",
    )
    print(json.dumps(
        {
            "output_dir": str(output_dir),
            "solver_success": bool(result.success),
            "objective_value": objective_value,
            "checks_passed": summary["checks_passed"],
            "model": model_stats,
        },
        ensure_ascii=False,
        indent=2,
    ))
    return 0 if summary["checks_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
