#!/usr/bin/env python3
"""Create a self-contained HTML visualization for E1 reference-layout results."""

from __future__ import annotations

import argparse
import csv
import html
import json
from pathlib import Path
from typing import Any


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build an HTML visualization of E1 results.")
    parser.add_argument(
        "--e1-dir",
        type=Path,
        default=Path("output/e1_reference_lp"),
        help="Directory containing E1 output CSV/JSON files.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        default=None,
        help="HTML output path. Defaults to <e1-dir>/e1_visualization.html.",
    )
    return parser.parse_args()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def number(value: str | None, default: float = 0.0) -> float:
    try:
        return float(value) if value not in (None, "") else default
    except (TypeError, ValueError):
        return default


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def build_payload(e1_dir: Path) -> dict[str, Any]:
    summary = json.loads((e1_dir / "e1_summary.json").read_text(encoding="utf-8"))
    equipment_rows = read_csv(e1_dir / "selected_equipment_ports.csv")
    all_equipment_path = e1_dir.parent / "e0_audit" / "equipment_mapping.csv"
    if all_equipment_path.exists():
        equipment_rows = read_csv(all_equipment_path)
        selected_ports = {
            row["equipment_name"]: row
            for row in read_csv(e1_dir / "selected_equipment_ports.csv")
        }
    else:
        selected_ports = {
            row["equipment_name"]: row
            for row in equipment_rows
        }

    utilization = {
        row["equipment_name"]: number(row.get("utilization"))
        for row in read_csv(e1_dir / "device_utilization.csv")
    }
    equipment = []
    for row in equipment_rows:
        name = row.get("equipment_name", "")
        selected = selected_ports.get(name, {})
        equipment.append(
            {
                "name": name,
                "group": row.get("tool_group") or row.get("mapped_smt_stn") or "",
                "status": row.get("mapping_status", "reference"),
                "bay": row.get("bay", ""),
                "x": number(row.get("position_x")),
                "y": number(row.get("position_y")),
                "width": number(row.get("width")),
                "height": number(row.get("height")),
                "utilization": utilization.get(name, None),
                "port": selected.get("port_name", ""),
                "rail": selected.get("rail_name", ""),
            }
        )

    equipment_by_name = {row["name"]: row for row in equipment}
    transport = []
    for row in read_csv(e1_dir / "transport_flow.csv"):
        source = equipment_by_name.get(row.get("source_equipment", ""))
        target = equipment_by_name.get(row.get("target_equipment", ""))
        if not source or not target:
            continue
        transport.append(
            {
                "source": row["source_equipment"],
                "target": row["target_equipment"],
                "sx": source["x"],
                "sy": source["y"],
                "tx": target["x"],
                "ty": target["y"],
                "sourceBay": row.get("source_bay", ""),
                "targetBay": row.get("target_bay", ""),
                "flow": number(row.get("flow_lots")),
                "distance": number(row.get("path_distance")),
                "cost": number(row.get("transport_cost")),
                "part": row.get("part", ""),
                "stepFrom": row.get("step_from", ""),
                "stepTo": row.get("step_to", ""),
            }
        )

    return {
        "summary": summary,
        "equipment": equipment,
        "transport": transport,
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E1 参考布局 LP 可视化</title>
<style>
:root {
  --bg: #101820;
  --panel: #17232d;
  --panel-2: #1d2c38;
  --line: #304554;
  --text: #edf4f7;
  --muted: #9db0ba;
  --accent: #53c7b4;
  --warning: #f2b84b;
}
* { box-sizing: border-box; }
body {
  margin: 0;
  background: var(--bg);
  color: var(--text);
  font: 14px/1.45 Segoe UI, Microsoft YaHei, sans-serif;
}
header {
  padding: 22px 28px 16px;
  border-bottom: 1px solid var(--line);
}
h1 { margin: 0 0 6px; font-size: 22px; font-weight: 650; }
.subtitle { color: var(--muted); }
.layout {
  display: grid;
  grid-template-columns: minmax(0, 1fr) 320px;
  gap: 16px;
  padding: 16px;
}
.stage {
  min-height: 680px;
  border: 1px solid var(--line);
  background: #0b131a;
  position: relative;
  overflow: hidden;
}
canvas { width: 100%; height: 680px; display: block; cursor: crosshair; }
.panel {
  background: var(--panel);
  border: 1px solid var(--line);
  padding: 16px;
}
.panel h2 { margin: 0 0 12px; font-size: 15px; }
.control { margin: 0 0 16px; }
label { display: block; margin-bottom: 6px; color: var(--muted); }
select, input[type="text"] {
  width: 100%;
  border: 1px solid #45606f;
  background: var(--panel-2);
  color: var(--text);
  padding: 8px 9px;
  border-radius: 4px;
}
input[type="range"] { width: 100%; }
.inline { display: flex; align-items: center; gap: 8px; }
.inline label { margin: 0; }
.stats {
  display: grid;
  grid-template-columns: 1fr 1fr;
  gap: 8px;
  margin-bottom: 16px;
}
.stat {
  background: var(--panel-2);
  padding: 9px;
  border: 1px solid #2a414f;
}
.stat strong { display: block; font-size: 16px; color: var(--accent); }
.stat span { color: var(--muted); font-size: 12px; }
#legend {
  max-height: 220px;
  overflow: auto;
  display: grid;
  gap: 5px;
}
.legend-row { display: flex; align-items: center; gap: 7px; color: var(--muted); }
.swatch { width: 11px; height: 11px; border-radius: 2px; flex: 0 0 auto; }
.note {
  color: var(--muted);
  font-size: 12px;
  border-top: 1px solid var(--line);
  padding-top: 12px;
}
#tooltip {
  position: fixed;
  display: none;
  pointer-events: none;
  background: #071016;
  border: 1px solid #527383;
  padding: 8px 10px;
  max-width: 290px;
  color: var(--text);
  box-shadow: 0 6px 20px #0008;
  z-index: 4;
}
@media (max-width: 900px) {
  .layout { grid-template-columns: 1fr; }
  .stage { min-height: 520px; }
  canvas { height: 520px; }
}
</style>
</head>
<body>
<header>
  <h1>E1 参考布局 LP 可视化</h1>
  <div class="subtitle">固定 SMAT2022 参考布局，展示设备分布、LP 工序分配和运输流量</div>
</header>
<main class="layout">
  <section class="stage"><canvas id="canvas"></canvas></section>
  <aside class="panel">
    <h2>结果概览</h2>
    <div class="stats">
      <div class="stat"><strong id="objective">-</strong><span>LP 目标值</span></div>
      <div class="stat"><strong id="equipmentCount">-</strong><span>设备实例</span></div>
      <div class="stat"><strong id="flowCount">-</strong><span>非零运输弧</span></div>
      <div class="stat"><strong id="maxUtil">-</strong><span>最大设备利用率</span></div>
    </div>
    <h2>显示控制</h2>
    <div class="control">
      <label for="colorMode">设备着色</label>
      <select id="colorMode">
        <option value="group">按设备组</option>
        <option value="bay">按 Bay</option>
        <option value="utilization">按利用率</option>
      </select>
    </div>
    <div class="control">
      <label for="search">搜索设备</label>
      <input id="search" type="text" placeholder="输入设备名或设备组">
    </div>
    <div class="control">
      <div class="inline">
        <input id="showFlow" type="checkbox" checked>
        <label for="showFlow">显示运输流</label>
      </div>
    </div>
    <div class="control">
      <label for="flowThreshold">流量阈值：<span id="thresholdValue">0</span> lot</label>
      <input id="flowThreshold" type="range" min="0" max="1" step="0.01" value="0">
    </div>
    <h2>图例</h2>
    <div id="legend"></div>
    <p class="note">运输线是设备间流量的可视化弦线；LP 成本使用端口映射后的有向轨道最短路径。固定 AMHS 设备以灰色显示，鼠标悬停可查看设备、端口和利用率。</p>
  </aside>
</main>
<div id="tooltip"></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const data = JSON.parse(document.getElementById("payload").textContent);
const canvas = document.getElementById("canvas");
const ctx = canvas.getContext("2d");
const tooltip = document.getElementById("tooltip");
const state = { mode: "group", showFlow: true, threshold: 0, search: "" };
const equipment = data.equipment;
const transport = data.transport;
const maxFlow = Math.max(...transport.map(x => x.flow), 1);
const groups = [...new Set(equipment.map(x => x.group || "UNKNOWN"))].sort();
const bays = [...new Set(equipment.map(x => x.bay || "UNKNOWN"))].sort();
const palette = new Map();
function hashColor(text, saturation=58, lightness=58) {
  let h = 0;
  for (let i = 0; i < text.length; i++) h = (h * 31 + text.charCodeAt(i)) >>> 0;
  return `hsl(${h % 360} ${saturation}% ${lightness}%)`;
}
groups.forEach((x, i) => palette.set("g:" + x, hashColor(x)));
bays.forEach((x, i) => palette.set("b:" + x, hashColor(x, 52, 62)));
function fmt(value) {
  if (value === null || value === undefined || Number.isNaN(value)) return "-";
  if (Math.abs(value) >= 1e7) return value.toExponential(3);
  return Number(value).toLocaleString("en-US", { maximumFractionDigits: 3 });
}
function sizeCanvas() {
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  draw();
}
function bounds() {
  const xs = equipment.map(x => x.x), ys = equipment.map(x => x.y);
  return {
    minX: Math.min(...xs), maxX: Math.max(...xs),
    minY: Math.min(...ys), maxY: Math.max(...ys)
  };
}
const box = bounds();
function transform() {
  const rect = canvas.getBoundingClientRect();
  const pad = 34;
  const scale = Math.min(
    (rect.width - pad * 2) / Math.max(1, box.maxX - box.minX),
    (rect.height - pad * 2) / Math.max(1, box.maxY - box.minY)
  );
  return {
    scale,
    x: x => pad + (x - box.minX) * scale,
    y: y => rect.height - pad - (y - box.minY) * scale
  };
}
function colorFor(item) {
  if (state.mode === "bay") return palette.get("b:" + item.bay) || "#82939a";
  if (state.mode === "utilization") {
    if (item.utilization === null || item.utilization === undefined) return "#67757c";
    const v = Math.max(0, Math.min(1, item.utilization));
    const hue = 120 - v * 120;
    return `hsl(${hue} 68% 54%)`;
  }
  return palette.get("g:" + item.group) || "#82939a";
}
function isMatch(item) {
  if (!state.search) return true;
  const q = state.search.toLowerCase();
  return [item.name, item.group, item.bay].some(x => (x || "").toLowerCase().includes(q));
}
function draw() {
  const rect = canvas.getBoundingClientRect();
  ctx.clearRect(0, 0, rect.width, rect.height);
  ctx.fillStyle = "#0b131a";
  ctx.fillRect(0, 0, rect.width, rect.height);
  const t = transform();
  const bayBounds = new Map();
  for (const item of equipment) {
    if (!bayBounds.has(item.bay)) bayBounds.set(item.bay, {minX:item.x,maxX:item.x,minY:item.y,maxY:item.y});
    const b = bayBounds.get(item.bay);
    b.minX = Math.min(b.minX, item.x); b.maxX = Math.max(b.maxX, item.x);
    b.minY = Math.min(b.minY, item.y); b.maxY = Math.max(b.maxY, item.y);
  }
  for (const [bay, b] of bayBounds) {
    ctx.strokeStyle = "#263d49";
    ctx.lineWidth = 1;
    ctx.strokeRect(t.x(b.minX)-5, t.y(b.maxY)-5, (b.maxX-b.minX)*t.scale+10, (b.maxY-b.minY)*t.scale+10);
    ctx.fillStyle = "#78909c";
    ctx.font = "10px Segoe UI, Microsoft YaHei, sans-serif";
    ctx.fillText(bay, t.x(b.minX)-3, t.y(b.maxY)-9);
  }
  if (state.showFlow) {
    for (const flow of transport) {
      if (flow.flow < state.threshold) continue;
      const alpha = Math.min(0.65, 0.08 + 0.32 * flow.flow / maxFlow);
      ctx.strokeStyle = `rgba(242,184,75,${alpha})`;
      ctx.lineWidth = Math.max(0.35, Math.min(3.2, 0.35 + 3 * Math.sqrt(flow.flow / maxFlow)));
      ctx.beginPath();
      ctx.moveTo(t.x(flow.sx), t.y(flow.sy));
      ctx.lineTo(t.x(flow.tx), t.y(flow.ty));
      ctx.stroke();
    }
  }
  for (const item of equipment) {
    const match = isMatch(item);
    ctx.fillStyle = item.status === "fixed_amhs" ? "#66747b" : colorFor(item);
    ctx.globalAlpha = match ? 0.9 : 0.12;
    const w = Math.max(2.2, (item.width || 1200) * t.scale);
    const h = Math.max(2.2, (item.height || 1200) * t.scale);
    ctx.fillRect(t.x(item.x) - w/2, t.y(item.y) - h/2, w, h);
    ctx.globalAlpha = 1;
    if (state.search && match) {
      ctx.strokeStyle = "#ffffff";
      ctx.lineWidth = 1.5;
      ctx.strokeRect(t.x(item.x)-w/2-2, t.y(item.y)-h/2-2, w+4, h+4);
    }
  }
  renderLegend();
}
function renderLegend() {
  const legend = document.getElementById("legend");
  if (state.mode === "utilization") {
    legend.innerHTML = '<div class="legend-row"><span class="swatch" style="background:hsl(120 68% 54%)"></span>低利用率</div>' +
      '<div class="legend-row"><span class="swatch" style="background:hsl(60 68% 54%)"></span>中等利用率</div>' +
      '<div class="legend-row"><span class="swatch" style="background:hsl(0 68% 54%)"></span>高利用率</div>';
    return;
  }
  const values = state.mode === "bay" ? bays : groups;
  legend.innerHTML = values.slice(0, 60).map(x => {
    const color = palette.get((state.mode === "bay" ? "b:" : "g:") + x) || "#82939a";
    return `<div class="legend-row"><span class="swatch" style="background:${color}"></span>${x}</div>`;
  }).join("") + (values.length > 60 ? `<div class="legend-row">其余 ${values.length-60} 项未列出</div>` : "");
}
function hitTest(event) {
  const rect = canvas.getBoundingClientRect();
  const t = transform();
  const px = event.clientX - rect.left, py = event.clientY - rect.top;
  let found = null, best = 12;
  for (const item of equipment) {
    const dx = px - t.x(item.x), dy = py - t.y(item.y);
    const distance = Math.sqrt(dx*dx + dy*dy);
    if (distance < best) { best = distance; found = item; }
  }
  return found;
}
canvas.addEventListener("mousemove", event => {
  const item = hitTest(event);
  if (!item) { tooltip.style.display = "none"; return; }
  tooltip.innerHTML = `<strong>${item.name}</strong><br>设备组：${item.group}<br>Bay：${item.bay}<br>坐标：${fmt(item.x)}, ${fmt(item.y)}<br>利用率：${item.utilization === null ? "固定基础设施" : fmt(item.utilization)}<br>端口：${item.port || "-"}<br>轨道：${item.rail || "-"}`;
  tooltip.style.display = "block";
  tooltip.style.left = `${event.clientX + 14}px`;
  tooltip.style.top = `${event.clientY + 14}px`;
});
canvas.addEventListener("mouseleave", () => tooltip.style.display = "none");
document.getElementById("colorMode").addEventListener("change", event => { state.mode = event.target.value; draw(); });
document.getElementById("showFlow").addEventListener("change", event => { state.showFlow = event.target.checked; draw(); });
document.getElementById("search").addEventListener("input", event => { state.search = event.target.value.trim(); draw(); });
document.getElementById("flowThreshold").addEventListener("input", event => {
  state.threshold = Number(event.target.value) * maxFlow;
  document.getElementById("thresholdValue").textContent = fmt(state.threshold);
  draw();
});
document.getElementById("objective").textContent = fmt(data.summary.objective_value);
document.getElementById("equipmentCount").textContent = fmt(equipment.length);
document.getElementById("flowCount").textContent = fmt(data.summary.solution.nonzero_transport_arcs);
document.getElementById("maxUtil").textContent = `${(data.summary.solution.max_device_utilization * 100).toFixed(1)}%`;
window.addEventListener("resize", sizeCanvas);
sizeCanvas();
</script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    e1_dir = args.e1_dir.resolve()
    output = (args.output or e1_dir / "e1_visualization.html").resolve()
    payload = build_payload(e1_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        HTML_TEMPLATE.replace("__PAYLOAD__", safe_json(payload)),
        encoding="utf-8",
    )
    print(f"wrote {output}")
    print(f"equipment={len(payload['equipment'])} transport_flows={len(payload['transport'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
