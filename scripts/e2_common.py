#!/usr/bin/env python3
"""Shared helpers for E2 layout optimization (L1 bay ordering + L2 bay layout).

E2 reuses E1's fixed-flow output (``transport_flow.csv``, ``from_to_bay.csv``)
and E0's equipment geometry (``equipment_mapping.csv``). This module only reads
CSV/JSON artifacts produced by E0/E1; it does not parse the original Excel/TSV
sources, keeping E2 decoupled from the raw data loaders.
"""

from __future__ import annotations

import csv
import json
import sys
from collections import defaultdict
from datetime import datetime
from pathlib import Path
from typing import Any


def log(message: str) -> None:
    """Print a timestamped progress line to stderr, flushed for real-time output."""
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {message}", file=sys.stderr, flush=True)


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            writer.writerow({field: row.get(field, "") for field in fields})


def read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def write_json(path: Path, obj: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(obj, ensure_ascii=False, indent=2), encoding="utf-8")


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


DEFAULT_GEOMETRY = 2000.0


def load_equipment(
    selected_ports_csv: Path,
    equipment_mapping_csv: Path | None = None,
) -> list[dict[str, Any]]:
    """Return the movable equipment universe used by E1, augmented with geometry.

    The equipment set is taken from E1's ``selected_equipment_ports.csv`` so that
    flow indices line up with ``transport_flow.csv``. Width/height come from E0's
    ``equipment_mapping.csv`` when available, otherwise a default geometry is used
    so the layout MILP still has finite non-overlap bounds.
    """
    ports = read_csv(selected_ports_csv)
    mapping: dict[str, dict[str, str]] = {}
    if equipment_mapping_csv is not None and Path(equipment_mapping_csv).exists():
        mapping = {row["equipment_name"]: row for row in read_csv(Path(equipment_mapping_csv))}

    equipment: list[dict[str, Any]] = []
    for port in ports:
        name = port.get("equipment_name", "")
        if not name:
            continue
        mapped = mapping.get(name, {})
        width = number(mapped.get("width"), DEFAULT_GEOMETRY)
        height = number(mapped.get("height"), DEFAULT_GEOMETRY)
        if width <= 0:
            width = DEFAULT_GEOMETRY
        if height <= 0:
            height = DEFAULT_GEOMETRY
        equipment.append(
            {
                "name": name,
                "tool_group": port.get("tool_group", ""),
                "bay": port.get("bay", ""),
                "width": width,
                "height": height,
                "x": number(port.get("position_x")),
                "y": number(port.get("position_y")),
            }
        )
    return equipment


def load_transport_flows(transport_flow_csv: Path) -> dict[tuple[str, str], float]:
    """Aggregate directed equipment-pair flows from E1's transport_flow.csv."""
    flows: dict[tuple[str, str], float] = defaultdict(float)
    for row in read_csv(transport_flow_csv):
        src = row.get("source_equipment", "")
        dst = row.get("target_equipment", "")
        if src and dst:
            flows[(src, dst)] += number(row.get("flow_lots"))
    return dict(flows)


def load_bay_flows(from_to_bay_csv: Path) -> dict[tuple[str, str], float]:
    """Aggregate directed bay-pair flows from E1's from_to_bay.csv."""
    flows: dict[tuple[str, str], float] = defaultdict(float)
    for row in read_csv(from_to_bay_csv):
        src = row.get("source_bay", "")
        dst = row.get("target_bay", "")
        if src and dst:
            flows[(src, dst)] += number(row.get("flow_lots"))
    return dict(flows)


def group_by_bay(equipment: list[dict[str, Any]]) -> dict[str, list[dict[str, Any]]]:
    groups: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for item in equipment:
        groups[item["bay"]].append(item)
    return dict(groups)


def bay_bounds(
    by_bay: dict[str, list[dict[str, Any]]],
) -> dict[str, dict[str, float]]:
    """Axis-aligned bounding box (from equipment centers) for each bay."""
    bounds: dict[str, dict[str, float]] = {}
    for bay, items in by_bay.items():
        xs = [item["x"] for item in items]
        ys = [item["y"] for item in items]
        bounds[bay] = {
            "xmin": min(xs),
            "xmax": max(xs),
            "ymin": min(ys),
            "ymax": max(ys),
        }
    return bounds


def manhattan_cost(
    equipment: list[dict[str, Any]],
    flows: dict[tuple[str, str], float],
) -> float:
    """Sum of flow * Manhattan distance between equipment centers (layout proxy)."""
    positions = {item["name"]: (item["x"], item["y"]) for item in equipment}
    total = 0.0
    for (src, dst), flow in flows.items():
        if src in positions and dst in positions:
            (x1, y1) = positions[src]
            (x2, y2) = positions[dst]
            total += flow * (abs(x1 - x2) + abs(y1 - y2))
    return total
