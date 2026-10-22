#!/usr/bin/env python3
"""E0 audit for the SMT2020/SMAT2022 layout-study data.

The script is intentionally read-only with respect to the input data. It
creates a compact audit package containing CSV mappings, JSON details and a
human-readable Markdown report.
"""

from __future__ import annotations

import argparse
import csv
import hashlib
import json
import math
import re
from collections import Counter, defaultdict, deque
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable

import openpyxl


FIXED_AMHS_GROUPS = {"STOCKER", "COMMIT", "COMPLETE"}
NON_EQUIPMENT_ROUTE_PREFIXES = ("delay",)
EXPLICIT_ALIASES = {
    "DefMEt_FE_118": "DefMet_FE_118",
}


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Audit SMT2020 and SMAT2022 data mappings.")
    parser.add_argument(
        "--data-root",
        type=Path,
        default=Path("data"),
        help="Root directory containing SMT2020_* and SMAT2022.",
    )
    parser.add_argument(
        "--production-model",
        choices=("LVHM", "HVLM"),
        default="LVHM",
        help="SMT2020 production model to audit.",
    )
    parser.add_argument(
        "--smat-file",
        type=Path,
        default=None,
        help="SMAT2022 workbook. Defaults to the LVHM_E workbook under data/SMAT2022.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=Path("output/e0_audit"),
        help="Directory for audit artifacts.",
    )
    return parser.parse_args()


def read_tsv(path: Path) -> list[dict[str, str]]:
    encodings = ("utf-8-sig", "utf-8", "cp1252", "latin1")
    last_error: Exception | None = None
    for encoding in encodings:
        try:
            with path.open("r", encoding=encoding, newline="") as handle:
                return list(csv.DictReader(handle, delimiter="\t"))
        except UnicodeDecodeError as exc:
            last_error = exc
    raise RuntimeError(f"Could not decode {path}: {last_error}")


def normalize(value: Any) -> str:
    if value is None:
        return ""
    text = str(value).strip()
    if text in {"", ","}:
        return ""
    return re.sub(r"[^a-z0-9]+", "", text.casefold())


def canonical_name(value: Any) -> str:
    text = "" if value is None else str(value).strip()
    return EXPLICIT_ALIASES.get(text, text)


def numeric(value: Any) -> float | None:
    if value in (None, ""):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def write_csv(path: Path, rows: Iterable[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def load_smt(data_root: Path, model: str) -> dict[str, Any]:
    directory = data_root / f"SMT2020_{model}"
    if not directory.is_dir():
        raise FileNotFoundError(f"Missing production directory: {directory}")

    part_rows = read_tsv(directory / "part.txt")
    order_rows = read_tsv(directory / "order.txt")
    tool_rows = read_tsv(directory / "tool.txt.1l")
    wip_rows = read_tsv(directory / "WIP.txt")

    route_rows: list[dict[str, str]] = []
    route_files: list[dict[str, Any]] = []
    for part in part_rows:
        route_file = directory / part["ROUTEFILE"]
        rows = read_tsv(route_file)
        route_rows.extend(
            [{**row, "_PART": part["PART"], "_ROUTEFILE": part["ROUTEFILE"]} for row in rows]
        )
        route_files.append(
            {
                "part": part["PART"],
                "route": part["ROUTE"],
                "file": part["ROUTEFILE"],
                "rows": len(rows),
            }
        )

    optional_files = {
        name: len(read_tsv(directory / name))
        for name in (
            "attach.txt",
            "downcal.txt",
            "fromto.txt",
            "pmcal.txt",
            "setup.txt",
            "setupgrp.txt",
        )
        if (directory / name).exists()
    }

    return {
        "directory": str(directory),
        "parts": part_rows,
        "orders": order_rows,
        "tools": tool_rows,
        "wip": wip_rows,
        "routes": route_rows,
        "route_files": route_files,
        "optional_files": optional_files,
    }


def default_smat_file(data_root: Path) -> Path:
    matches = sorted(
        (data_root / "SMAT2022").glob("General Data/**/*.xlsx"),
        key=lambda path: path.name,
    )
    if not matches:
        raise FileNotFoundError("No SMAT2022 workbook found under data/SMAT2022.")
    return matches[0]


def load_smat(path: Path) -> dict[str, list[dict[str, Any]]]:
    if not path.exists():
        raise FileNotFoundError(f"Missing SMAT2022 workbook: {path}")
    workbook = openpyxl.load_workbook(path, read_only=True, data_only=True)
    result: dict[str, list[dict[str, Any]]] = {}
    for worksheet in workbook.worksheets:
        rows = worksheet.iter_rows(values_only=True)
        headers = [str(value).strip() if value is not None else "" for value in next(rows)]
        records = []
        for values in rows:
            records.append({header: value for header, value in zip(headers, values)})
        result[worksheet.title] = records
    return result


def make_lookup(values: Iterable[str]) -> dict[str, list[str]]:
    lookup: dict[str, list[str]] = defaultdict(list)
    for value in values:
        if value:
            lookup[normalize(value)].append(value)
    return dict(lookup)


def resolve_name(value: str, candidates: Iterable[str]) -> tuple[str, str]:
    raw = "" if value is None else str(value).strip()
    canonical = canonical_name(raw)
    candidate_list = list(candidates)
    exact = {str(candidate): str(candidate) for candidate in candidate_list}
    if canonical in exact:
        reason = "explicit_alias" if canonical != raw else "exact"
        return canonical, reason

    normalized = make_lookup(candidate_list)
    matches = normalized.get(normalize(canonical), [])
    if len(matches) == 1:
        return matches[0], "normalized"
    if len(matches) > 1:
        return "", "ambiguous"
    return "", "unmapped"


def audit_name_mappings(
    smt: dict[str, Any], smat: dict[str, list[dict[str, Any]]]
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    tool_names = [row.get("STN", "") for row in smt["tools"] if row.get("STN")]
    smat_groups = [row.get("TOOL_GROUP", "") for row in smat["Equipment"] if row.get("TOOL_GROUP")]
    tool_set = set(tool_names)
    mapping_rows: list[dict[str, Any]] = []
    for source in sorted(set(tool_names) | set(smat_groups)):
        if source in tool_set:
            target = source
            status = "matched"
            reason = "exact_smt_tool_name"
        else:
            target, reason = resolve_name(source, tool_names)
            status = "matched" if target else "unmapped"
        mapping_rows.append(
            {
                "source_name": source,
                "target_smt_stn": target,
                "source_kind": "SMT_STN" if source in tool_set else "SMAT_TOOL_GROUP",
                "status": status,
                "reason": reason,
                "is_fixed_amhs_group": source in FIXED_AMHS_GROUPS,
                "smt_tool_rows": sum(1 for name in tool_names if name == source),
                "smat_equipment_count": sum(1 for name in smat_groups if name == source),
            }
        )

    route_families = sorted({row.get("STNFAM", "") for row in smt["routes"] if row.get("STNFAM")})
    route_rows: list[dict[str, Any]] = []
    for family in route_families:
        target, reason = resolve_name(family, tool_names)
        family_rows = [row for row in smt["routes"] if row.get("STNFAM") == family]
        is_non_equipment = family.casefold().startswith(NON_EQUIPMENT_ROUTE_PREFIXES) or any(
            "delay" in str(row.get("DESC") or "").casefold()
            for row in family_rows
        )
        if is_non_equipment and not target:
            status = "non_equipment_node"
            reason = "delay_or_waiting_node"
        else:
            status = "matched" if target else "unmapped"
        route_rows.append(
            {
                "route_stnfam": family,
                "target_smt_stn": target,
                "status": status,
                "reason": reason,
                "route_row_count": sum(1 for row in smt["routes"] if row.get("STNFAM") == family),
                "route_file_count": len(
                    {row.get("_ROUTEFILE", "") for row in smt["routes"] if row.get("STNFAM") == family}
                ),
            }
        )
    return mapping_rows, route_rows


def audit_equipment(
    smat: dict[str, list[dict[str, Any]]],
    tool_names: Iterable[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    tool_names = list(tool_names)
    equipment_rows: list[dict[str, Any]] = []
    group_counts = Counter()
    fixed_count = 0
    movable_count = 0
    missing_geometry = 0
    for row in smat["Equipment"]:
        group = str(row.get("TOOL_GROUP") or "").strip()
        target, reason = resolve_name(group, tool_names)
        is_fixed = group in FIXED_AMHS_GROUPS
        if is_fixed:
            fixed_count += 1
        else:
            movable_count += 1
        status = "fixed_amhs" if is_fixed else ("matched" if target else "unmapped")
        group_counts[group] += 1
        geometry_values = (
            numeric(row.get("WIDTH")),
            numeric(row.get("HEIGHT")),
            numeric(row.get("POSITION_X")),
            numeric(row.get("POSITION_Y")),
        )
        if any(value is None for value in geometry_values):
            missing_geometry += 1
        equipment_rows.append(
            {
                "equipment_name": row.get("NAME", ""),
                "tool_group": group,
                "mapped_smt_stn": target,
                "mapping_status": status,
                "mapping_reason": "fixed_infrastructure" if is_fixed else reason,
                "bay": row.get("BAY", ""),
                "width": row.get("WIDTH", ""),
                "height": row.get("HEIGHT", ""),
                "position_x": row.get("POSITION_X", ""),
                "position_y": row.get("POSITION_Y", ""),
            }
        )
    return equipment_rows, {
        "equipment_total": len(equipment_rows),
        "fixed_amhs_total": fixed_count,
        "movable_process_total": movable_count,
        "equipment_missing_geometry": missing_geometry,
        "equipment_group_counts": dict(sorted(group_counts.items())),
    }


def audit_ports(
    smat: dict[str, list[dict[str, Any]]],
    equipment_names: set[str],
    rail_names: set[str],
) -> tuple[list[dict[str, Any]], dict[str, Any]]:
    by_equipment: dict[str, list[dict[str, Any]]] = defaultdict(list)
    audit_rows = []
    empty_equipment = 0
    invalid_equipment = 0
    invalid_rail = 0
    missing_distance = 0
    unknown_port_type = 0
    known_port_types = {
        str(row.get("NAME") or "") for row in smat["PortType"] if row.get("NAME")
    }
    for row in smat["Port"]:
        equipment = str(row.get("EQP_NAME") or "").strip()
        rail = str(row.get("RAILLINE_NAME") or "").strip()
        equipment_status = "empty" if not equipment or equipment == "," else (
            "matched" if equipment in equipment_names else "unmapped"
        )
        rail_status = "matched" if rail in rail_names else "unmapped"
        if numeric(row.get("DISTANCE")) is None:
            missing_distance += 1
        if str(row.get("PORT_TYPE") or "") not in known_port_types:
            unknown_port_type += 1
        if equipment_status == "empty":
            empty_equipment += 1
        elif equipment_status != "matched":
            invalid_equipment += 1
        if rail_status != "matched":
            invalid_rail += 1
        if equipment_status == "matched":
            by_equipment[equipment].append(row)
        audit_rows.append(
            {
                "port_name": row.get("NAME", ""),
                "port_type": row.get("PORT_TYPE", ""),
                "equipment_name": equipment,
                "equipment_status": equipment_status,
                "rail_name": rail,
                "rail_status": rail_status,
                "distance_on_rail": row.get("DISTANCE", ""),
                "distance_numeric": numeric(row.get("DISTANCE")) is not None,
                "port_type_status": (
                    "matched"
                    if str(row.get("PORT_TYPE") or "") in known_port_types
                    else "unmapped"
                ),
            }
        )

    equipment_port_rows = []
    for equipment in sorted(equipment_names):
        ports = by_equipment.get(equipment, [])
        equipment_port_rows.append(
            {
                "equipment_name": equipment,
                "port_count": len(ports),
                "rail_count": len({row.get("RAILLINE_NAME", "") for row in ports}),
                "has_rail_connection": bool(ports),
                "port_types": ",".join(sorted({str(row.get("PORT_TYPE", "")) for row in ports})),
            }
        )
    summary = {
        "port_total": len(smat["Port"]),
        "port_empty_equipment": empty_equipment,
        "port_unmapped_equipment": invalid_equipment,
        "port_unmapped_rail": invalid_rail,
        "port_missing_distance": missing_distance,
        "port_unknown_type": unknown_port_type,
        "equipment_with_at_least_one_port": sum(
            row["has_rail_connection"] for row in equipment_port_rows
        ),
        "equipment_without_port": sum(
            not row["has_rail_connection"] for row in equipment_port_rows
        ),
    }
    return audit_rows, {"summary": summary, "equipment_port_rows": equipment_port_rows}


def weak_components(nodes: set[str], edges: Iterable[tuple[str, str]]) -> list[list[str]]:
    adjacency: dict[str, set[str]] = defaultdict(set)
    for source, target in edges:
        adjacency[source].add(target)
        adjacency[target].add(source)
    remaining = set(nodes)
    components = []
    while remaining:
        start = next(iter(remaining))
        queue = [start]
        remaining.remove(start)
        component = []
        while queue:
            current = queue.pop()
            component.append(current)
            for neighbor in adjacency[current]:
                if neighbor in remaining:
                    remaining.remove(neighbor)
                    queue.append(neighbor)
        components.append(sorted(component))
    return components


def reachable(start: str, adjacency: dict[str, list[str]]) -> set[str]:
    visited = {start}
    queue = deque([start])
    while queue:
        current = queue.popleft()
        for target in adjacency.get(current, []):
            if target not in visited:
                visited.add(target)
                queue.append(target)
    return visited


def audit_rail(smat: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    address = {str(row.get("NAME")): row for row in smat["Address"] if row.get("NAME")}
    edges = []
    adjacency: dict[str, list[str]] = defaultdict(list)
    missing_from = 0
    missing_to = 0
    missing_coordinates = 0
    lengths = []
    curve_count = 0
    for row in smat["Rail"]:
        source = str(row.get("FROM_NODE") or "")
        target = str(row.get("TO_NODE") or "")
        if source not in address:
            missing_from += 1
        if target not in address:
            missing_to += 1
        edges.append((source, target))
        adjacency[source].append(target)
        if row.get("CURVE") in (1, "1", True):
            curve_count += 1
        source_row = address.get(source, {})
        target_row = address.get(target, {})
        x1, y1 = numeric(source_row.get("POSITION_X")), numeric(source_row.get("POSITION_Y"))
        x2, y2 = numeric(target_row.get("POSITION_X")), numeric(target_row.get("POSITION_Y"))
        if None not in (x1, y1, x2, y2):
            lengths.append(math.hypot(x2 - x1, y2 - y1))
        else:
            missing_coordinates += 1

    nodes = set(address)
    components = weak_components(nodes, edges)
    sample_nodes = sorted(nodes)[: min(20, len(nodes))]
    sample_reachability = [
        {"source": source, "reachable_node_count": len(reachable(source, adjacency))}
        for source in sample_nodes
    ]
    bay_edges = Counter(str(row.get("BAY_NAME") or "") for row in smat["Rail"])
    return {
        "address_node_total": len(address),
        "rail_edge_total": len(smat["Rail"]),
        "rail_edges_missing_from_node": missing_from,
        "rail_edges_missing_to_node": missing_to,
        "rail_edges_missing_coordinates": missing_coordinates,
        "curve_edge_total": curve_count,
        "weak_component_count": len(components),
        "largest_weak_component": max((len(component) for component in components), default=0),
        "edge_length_min": min(lengths) if lengths else None,
        "edge_length_max": max(lengths) if lengths else None,
        "edge_length_mean": sum(lengths) / len(lengths) if lengths else None,
        "sample_reachability": sample_reachability,
        "rail_edges_by_bay": dict(sorted(bay_edges.items())),
    }


def audit_bays(smat: dict[str, list[dict[str, Any]]]) -> dict[str, Any]:
    bay_rows = smat["Bay"]
    equipment_bays = Counter(str(row.get("BAY") or "") for row in smat["Equipment"])
    return {
        "bay_total": len(bay_rows),
        "bay_type_counts": dict(
            Counter(str(row.get("TYPE") or "") for row in bay_rows)
        ),
        "bay_names": sorted(str(row.get("NAME") or "") for row in bay_rows),
        "equipment_bays_not_in_bay_table": sorted(
            bay for bay in equipment_bays if bay and bay not in {row.get("NAME") for row in bay_rows}
        ),
        "equipment_count_by_bay": dict(sorted(equipment_bays.items())),
    }


def audit_routes(smt: dict[str, Any], tool_names: set[str]) -> dict[str, Any]:
    routes = smt["routes"]
    route_families = sorted({row.get("STNFAM", "") for row in routes if row.get("STNFAM")})
    non_equipment_nodes = [
        family
        for family in route_families
        if family.casefold().startswith(NON_EQUIPMENT_ROUTE_PREFIXES)
        or any(
            "delay" in str(row.get("DESC") or "").casefold()
            for row in routes
            if row.get("STNFAM") == family
        )
    ]
    return {
        "route_row_total": len(routes),
        "route_file_count": len(smt["route_files"]),
        "route_files": smt["route_files"],
        "route_stnfam_total": len({row.get("STNFAM") for row in routes if row.get("STNFAM")}),
        "route_stnfam_unmapped_to_tool": sorted(
            {
                row.get("STNFAM")
                for row in routes
                if row.get("STNFAM")
                and not resolve_name(row.get("STNFAM", ""), tool_names)[0]
                and row.get("STNFAM") not in non_equipment_nodes
            }
        ),
        "non_equipment_route_nodes": non_equipment_nodes,
        "ptper_counts": dict(Counter(row.get("PTPER", "") for row in routes)),
        "ptunits_counts": dict(Counter(row.get("PTUNITS", "") for row in routes)),
        "rows_with_rework": sum(bool(row.get("REWORK") or row.get("RWKSTEP")) for row in routes),
        "rows_with_batch_limits": sum(bool(row.get("BATCHMN") or row.get("BATCHMX")) for row in routes),
        "missing_ptime": sum(not row.get("PTIME") for row in routes),
    }


def build_summary(
    smt: dict[str, Any],
    smat_path: Path,
    input_files: list[dict[str, str]],
    smat: dict[str, list[dict[str, Any]]],
    mapping_rows: list[dict[str, Any]],
    route_mapping_rows: list[dict[str, Any]],
    equipment_summary: dict[str, Any],
    port_summary: dict[str, Any],
    rail_summary: dict[str, Any],
    bay_summary: dict[str, Any],
    route_summary: dict[str, Any],
) -> dict[str, Any]:
    equipment_unmapped = [
        row for row in mapping_rows
        if row["source_kind"] == "SMAT_TOOL_GROUP" and row["status"] == "unmapped"
        and not row["is_fixed_amhs_group"]
    ]
    route_unmapped = [row for row in route_mapping_rows if row["status"] == "unmapped"]
    critical_checks = {
        "all_route_stnfam_mapped": not route_unmapped,
        "all_movable_equipment_mapped": equipment_summary["movable_process_total"]
        == equipment_summary["equipment_total"] - equipment_summary["fixed_amhs_total"]
        and not equipment_unmapped,
        "all_rail_endpoints_exist": rail_summary["rail_edges_missing_from_node"] == 0
        and rail_summary["rail_edges_missing_to_node"] == 0,
        "all_rail_coordinates_present": rail_summary["rail_edges_missing_coordinates"] == 0,
        "all_equipment_has_port": port_summary["summary"]["equipment_without_port"] == 0,
        "all_equipment_geometry_present": equipment_summary["equipment_missing_geometry"] == 0,
        "all_port_rail_references_exist": port_summary["summary"]["port_unmapped_rail"] == 0,
        "all_port_distances_numeric": port_summary["summary"]["port_missing_distance"] == 0,
        "all_port_types_exist": port_summary["summary"]["port_unknown_type"] == 0,
        "all_equipment_bays_exist": not bay_summary["equipment_bays_not_in_bay_table"],
    }
    return {
        "audit_version": "1.0",
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "production_model": smt["directory"],
        "smat_workbook": str(smat_path),
        "input_files": input_files,
        "critical_checks": critical_checks,
        "critical_check_passed": all(critical_checks.values()),
        "notes": [
            "SMAT2022 Equipment is treated as the source of actual layout equipment instances.",
            "STOCKER, COMMIT and COMPLETE are classified as fixed AMHS infrastructure.",
            "DefMEt_FE_118 is mapped to DefMet_FE_118 by explicit alias.",
            "Rail edge lengths are only audited from endpoint coordinates; route-distance generation is a later step.",
        ],
        "smt_counts": {
            "part_rows": len(smt["parts"]),
            "order_rows": len(smt["orders"]),
            "tool_rows": len(smt["tools"]),
            "wip_rows": len(smt["wip"]),
            "route_rows": len(smt["routes"]),
            "optional_files": smt["optional_files"],
        },
        "smat_counts": {name: len(rows) for name, rows in smat.items()},
        "equipment": equipment_summary,
        "ports": port_summary["summary"],
        "rail": rail_summary,
        "bays": bay_summary,
        "routes": route_summary,
        "unmapped_smat_groups": equipment_unmapped,
        "unmapped_route_families": route_unmapped,
    }


def markdown_report(summary: dict[str, Any], mapping_rows: list[dict[str, Any]]) -> str:
    checks = summary["critical_checks"]
    check_lines = "\n".join(
        f"- [{'x' if passed else ' '}] {name}" for name, passed in checks.items()
    )
    unmapped = [
        row["source_name"]
        for row in mapping_rows
        if row["source_kind"] == "SMAT_TOOL_GROUP"
        and row["status"] == "unmapped"
        and not row["is_fixed_amhs_group"]
    ]
    return f"""# E0 数据审计报告

生成时间（UTC）：{summary['generated_at_utc']}

生产模型：`{summary['production_model']}`  
SMAT2022 文件：`{summary['smat_workbook']}`

## 审计结论

总体状态：**{'通过' if summary['critical_check_passed'] else '需要处理问题'}**

{check_lines}

## 数据规模

| 类别 | 数量 |
|---|---:|
| SMT2020 产品记录 | {summary['smt_counts']['part_rows']} |
| SMT2020 订单记录 | {summary['smt_counts']['order_rows']} |
| SMT2020 工具记录 | {summary['smt_counts']['tool_rows']} |
| SMT2020 WIP 记录 | {summary['smt_counts']['wip_rows']} |
| SMT2020 路线记录 | {summary['smt_counts']['route_rows']} |
| SMAT2022 设备实例 | {summary['equipment']['equipment_total']} |
| 可移动工艺设备 | {summary['equipment']['movable_process_total']} |
| 固定 AMHS 设备 | {summary['equipment']['fixed_amhs_total']} |
| SMAT2022 端口记录 | {summary['ports']['port_total']} |
| SMAT2022 轨道边 | {summary['rail']['rail_edge_total']} |
| SMAT2022 轨道节点 | {summary['rail']['address_node_total']} |
| SMAT2022 Bay | {summary['bays']['bay_total']} |

## 映射结果

SMT2020 路线中的 `STNFAM`、SMT2020 工具表中的 `STN` 与 SMAT2022 的 `TOOL_GROUP` 已进行显式匹配。已知别名 `DefMEt_FE_118 -> DefMet_FE_118` 已应用。

未映射且不属于固定 AMHS 设备的 SMAT2022 设备组：

{', '.join(f'`{name}`' for name in unmapped) if unmapped else '无'}

固定 AMHS 组：`STOCKER`、`COMMIT`、`COMPLETE`。完整结果见 `tool_mapping.csv`、`equipment_mapping.csv` 和 `route_coverage.csv`。

## 路线检查

- 路线文件数：{summary['routes']['route_file_count']}
- 路线记录数：{summary['routes']['route_row_total']}
- `PTPER` 分布：`{summary['routes']['ptper_counts']}`
- 含批处理边界的记录：{summary['routes']['rows_with_batch_limits']}
- 含返工字段的记录：{summary['routes']['rows_with_rework']}
- 缺少 `PTIME` 的记录：{summary['routes']['missing_ptime']}
- 识别为非设备延迟/等待节点：{', '.join(f'`{name}`' for name in summary['routes']['non_equipment_route_nodes']) or '无'}

## 轨道和端口检查

- 轨道端点缺失：起点 {summary['rail']['rail_edges_missing_from_node']}，终点 {summary['rail']['rail_edges_missing_to_node']}
- 轨道边缺少端点坐标：{summary['rail']['rail_edges_missing_coordinates']}
- 轨道弱连通分量：{summary['rail']['weak_component_count']}
- 最大弱连通分量节点数：{summary['rail']['largest_weak_component']}
- 含曲线标记的轨道边：{summary['rail']['curve_edge_total']}
- 没有端口的设备：{summary['ports']['equipment_without_port']}
- 缺少几何字段的设备：{summary['equipment']['equipment_missing_geometry']}
- 端口引用不存在设备：{summary['ports']['port_unmapped_equipment']}
- 端口引用不存在轨道：{summary['ports']['port_unmapped_rail']}
- 端口距离非数值记录：{summary['ports']['port_missing_distance']}
- 未知端口类型记录：{summary['ports']['port_unknown_type']}

`rail_summary.json` 中保存了端点、连通分量、边长度统计和样本可达性结果。边长度仅用于 E0 数据检查，正式路径矩阵仍应根据研究方案定义的轨道长度规则生成。

## 输出文件

- `audit_summary.json`：机器可读的总审计结果和关键检查状态；
- `tool_mapping.csv`：SMT2020 工具族与 SMAT2022 设备组映射；
- `route_coverage.csv`：路线 `STNFAM` 到 SMT2020 工具类型的覆盖情况；
- `equipment_mapping.csv`：每个 SMAT2022 设备实例的映射和固定/可移动分类；
- `port_audit.csv`：端口、设备引用和轨道引用检查；
- `equipment_port_audit.csv`：每个设备实例的端口覆盖情况；
- `rail_summary.json`：轨道图拓扑和坐标检查；
- `audit_report.md`：本报告。
"""


def main() -> int:
    args = parse_args()
    data_root = args.data_root.resolve()
    smat_path = args.smat_file.resolve() if args.smat_file else default_smat_file(data_root).resolve()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)

    smt = load_smt(data_root, args.production_model)
    smat = load_smat(smat_path)
    production_directory = Path(smt["directory"])
    input_paths = sorted(production_directory.glob("*")) + [smat_path]
    input_files = [
        {"path": str(path), "sha256": sha256_file(path)}
        for path in input_paths
        if path.is_file()
    ]
    required_sheets = {
        "Address",
        "Rail",
        "Bay",
        "Equipment",
        "Port",
        "PortType",
        "Vehicle",
        "VehicleType",
        "ZCU",
    }
    missing_sheets = sorted(required_sheets - set(smat))
    if missing_sheets:
        raise RuntimeError(f"Missing SMAT2022 worksheets: {missing_sheets}")

    mapping_rows, route_mapping_rows = audit_name_mappings(smt, smat)
    tool_names = {row.get("STN", "") for row in smt["tools"] if row.get("STN")}
    equipment_mapping, equipment_summary = audit_equipment(smat, tool_names)
    equipment_names = {
        str(row.get("NAME"))
        for row in smat["Equipment"]
        if row.get("NAME")
    }
    rail_names = {
        str(row.get("NAME"))
        for row in smat["Rail"]
        if row.get("NAME")
    }
    port_audit, port_details = audit_ports(smat, equipment_names, rail_names)
    rail_summary = audit_rail(smat)
    bay_summary = audit_bays(smat)
    route_summary = audit_routes(smt, tool_names)
    summary = build_summary(
        smt,
        smat_path,
        input_files,
        smat,
        mapping_rows,
        route_mapping_rows,
        equipment_summary,
        port_details,
        rail_summary,
        bay_summary,
        route_summary,
    )

    write_csv(
        output_dir / "tool_mapping.csv",
        mapping_rows,
        [
            "source_name",
            "target_smt_stn",
            "source_kind",
            "status",
            "reason",
            "is_fixed_amhs_group",
            "smt_tool_rows",
            "smat_equipment_count",
        ],
    )
    write_csv(
        output_dir / "route_coverage.csv",
        route_mapping_rows,
        [
            "route_stnfam",
            "target_smt_stn",
            "status",
            "reason",
            "route_row_count",
            "route_file_count",
        ],
    )
    write_csv(
        output_dir / "equipment_mapping.csv",
        equipment_mapping,
        [
            "equipment_name",
            "tool_group",
            "mapped_smt_stn",
            "mapping_status",
            "mapping_reason",
            "bay",
            "width",
            "height",
            "position_x",
            "position_y",
        ],
    )
    write_csv(
        output_dir / "port_audit.csv",
        port_audit,
        [
            "port_name",
            "port_type",
            "equipment_name",
            "equipment_status",
            "rail_name",
            "rail_status",
            "distance_on_rail",
            "distance_numeric",
            "port_type_status",
        ],
    )
    write_csv(
        output_dir / "equipment_port_audit.csv",
        port_details["equipment_port_rows"],
        ["equipment_name", "port_count", "rail_count", "has_rail_connection", "port_types"],
    )
    (output_dir / "audit_summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "rail_summary.json").write_text(
        json.dumps(rail_summary, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (output_dir / "audit_report.md").write_text(
        markdown_report(summary, mapping_rows),
        encoding="utf-8",
    )

    print(json.dumps({
        "output_dir": str(output_dir),
        "critical_check_passed": summary["critical_check_passed"],
        "critical_checks": summary["critical_checks"],
    }, ensure_ascii=False, indent=2))
    return 0 if summary["critical_check_passed"] else 2


if __name__ == "__main__":
    raise SystemExit(main())
