#!/usr/bin/env python3
"""Build a self-contained HTML comparing the E1 reference and E2 optimized layout."""

from __future__ import annotations

import argparse
import json
from pathlib import Path
from typing import Any

from e2_common import read_csv, read_json


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Visualize E2 before/after layouts.")
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--e2-dir", type=Path, default=Path("output/e2_layout"))
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


def build_payload(e1_dir: Path, e2_dir: Path) -> dict[str, Any]:
    reference = [
        {
            "name": row["equipment_name"],
            "bay": row.get("bay", ""),
            "x": float(row.get("position_x") or 0),
            "y": float(row.get("position_y") or 0),
        }
        for row in read_csv(e1_dir / "selected_equipment_ports.csv")
    ]
    optimized = [
        {
            "name": row["equipment_name"],
            "bay": row.get("bay", ""),
            "x": float(row.get("x") or 0),
            "y": float(row.get("y") or 0),
        }
        for row in read_csv(e2_dir / "new_layout.csv")
    ]
    summary = read_json(e2_dir / "e2_summary.json")
    return {
        "reference": reference,
        "optimized": optimized,
        "baseline_cost": summary.get("baseline_cost_manhattan"),
        "optimized_cost": summary.get("optimized_cost_manhattan"),
        "cost_reduction_pct": summary.get("cost_reduction_pct"),
    }


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E2 布局优化前后对比</title>
<style>
:root { --bg:#101820; --panel:#17232d; --line:#304554; --text:#edf4f7; --muted:#9db0ba; --accent:#53c7b4; }
* { box-sizing: border-box; }
body { margin:0; background:var(--bg); color:var(--text); font:14px/1.45 Segoe UI, Microsoft YaHei, sans-serif; }
header { padding:22px 28px 16px; border-bottom:1px solid var(--line); }
h1 { margin:0 0 6px; font-size:22px; font-weight:650; }
.subtitle { color:var(--muted); }
.stats { display:flex; gap:16px; padding:16px 28px 0; flex-wrap:wrap; }
.stat { background:var(--panel); border:1px solid var(--line); padding:12px 16px; }
.stat strong { display:block; font-size:18px; color:var(--accent); }
.stat span { color:var(--muted); font-size:12px; }
.layout { display:grid; grid-template-columns:1fr 1fr; gap:16px; padding:16px 28px; }
.stage { border:1px solid var(--line); background:#0b131a; }
.stage h2 { margin:0; padding:10px 12px; font-size:14px; border-bottom:1px solid var(--line); }
canvas { width:100%; height:640px; display:block; }
@media (max-width:900px) { .layout { grid-template-columns:1fr; } }
</style>
</head>
<body>
<header>
  <h1>E2 布局优化前后对比</h1>
  <div class="subtitle">左：E1 参考布局；右：E2 优化布局（Bay 内重排）</div>
</header>
<div class="stats">
  <div class="stat"><strong id="baseline">-</strong><span>参考成本（流量×曼哈顿）</span></div>
  <div class="stat"><strong id="optimized">-</strong><span>优化成本</span></div>
  <div class="stat"><strong id="reduction">-</strong><span>下降比例</span></div>
</div>
<main class="layout">
  <section class="stage"><h2>参考布局</h2><canvas id="ref"></canvas></section>
  <section class="stage"><h2>优化布局</h2><canvas id="opt"></canvas></section>
</main>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
const data = JSON.parse(document.getElementById("payload").textContent);
const bays = [...new Set([...data.reference, ...data.optimized].map(x => x.bay || "UNKNOWN"))].sort();
const palette = new Map();
function hashColor(t){let h=0;for(let i=0;i<t.length;i++)h=(h*31+t.charCodeAt(i))>>>0;return `hsl(${h%360} 55% 58%)`;}
bays.forEach(x=>palette.set(x,hashColor(x)));
function bounds(items){
  return { minX:Math.min(...items.map(x=>x.x)), maxX:Math.max(...items.map(x=>x.x)),
           minY:Math.min(...items.map(x=>x.y)), maxY:Math.max(...items.map(x=>x.y)) };
}
function draw(canvas, items){
  const ctx = canvas.getContext("2d");
  const dpr = window.devicePixelRatio || 1;
  const rect = canvas.getBoundingClientRect();
  canvas.width = Math.max(1, Math.round(rect.width * dpr));
  canvas.height = Math.max(1, Math.round(rect.height * dpr));
  ctx.setTransform(dpr,0,0,dpr,0,0);
  ctx.fillStyle = "#0b131a";
  ctx.fillRect(0,0,rect.width,rect.height);
  const b = bounds(items);
  const pad = 30;
  const scale = Math.min((rect.width-pad*2)/Math.max(1,b.maxX-b.minX),(rect.height-pad*2)/Math.max(1,b.maxY-b.minY));
  const tx = x => pad + (x-b.minX)*scale;
  const ty = y => rect.height - pad - (y-b.minY)*scale;
  for(const item of items){
    ctx.fillStyle = palette.get(item.bay) || "#82939a";
    ctx.fillRect(tx(item.x)-2, ty(item.y)-2, 4, 4);
  }
}
function fmt(v){ return v===null||v===undefined?"-":Number(v).toLocaleString("en-US",{maximumFractionDigits:1}); }
draw(document.getElementById("ref"), data.reference);
draw(document.getElementById("opt"), data.optimized);
document.getElementById("baseline").textContent = fmt(data.baseline_cost);
document.getElementById("optimized").textContent = fmt(data.optimized_cost);
document.getElementById("reduction").textContent = (data.cost_reduction_pct==null?"-":data.cost_reduction_pct.toFixed(2)+"%");
window.addEventListener("resize", () => { draw(document.getElementById("ref"), data.reference); draw(document.getElementById("opt"), data.optimized); });
</script>
</body>
</html>
"""


def main() -> int:
    args = parse_args()
    e1_dir = args.e1_dir.resolve()
    e2_dir = args.e2_dir.resolve()
    output = (args.output or e2_dir / "e2_visualization.html").resolve()
    payload = build_payload(e1_dir, e2_dir)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(
        HTML_TEMPLATE.replace("__PAYLOAD__", safe_json(payload)),
        encoding="utf-8",
    )
    print(f"wrote {output}")
    print(f"reference={len(payload['reference'])} optimized={len(payload['optimized'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
