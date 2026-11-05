#!/usr/bin/env python3
"""Build a self-contained interactive HTML for the E3 global heuristic results.

Reads ``output/e3_global/layout.csv`` and ``output/e3_global/e3_summary.json``,
reconstructs each equipment's original vs. optimized slot position (slots are
fixed; equipment swap among same-footprint slots), and embeds everything into a
single offline HTML page under ``交互展示/``. No backend / network / runtime
dependencies are required to open the generated page.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from collections import defaultdict
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e2_common import read_csv, read_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build interactive HTML for E3 results.")
    parser.add_argument("--e3-dir", type=Path, default=Path("output/e3_global"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("交互展示/e3_layout_interactive.html"),
        help="Output HTML path (defaults to 交互展示/e3_layout_interactive.html).",
    )
    return parser.parse_args()


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_payload(e3_dir: Path) -> dict[str, Any]:
    rows = read_csv(e3_dir / "layout.csv")
    summary = read_json(e3_dir / "e3_summary.json")

    # Slots are fixed; ``new_slot`` is a permutation of 0..n-1, so a slot's
    # fixed position is the (x, y, bay) of the row whose ``new_slot`` equals it.
    slot_pos: dict[int, tuple[float, float, str]] = {}
    for r in rows:
        slot_pos[int(number(r.get("new_slot")))] = (
            number(r.get("x")),
            number(r.get("y")),
            r.get("bay", ""),
        )

    equipment: list[dict[str, Any]] = []
    group_stats: dict[str, dict[str, Any]] = defaultdict(
        lambda: {"count": 0, "moved": 0, "dist_sum": 0.0, "dist_max": 0.0}
    )
    moved = 0
    for r in rows:
        name = r.get("equipment_name", "")
        group = r.get("tool_group", "")
        orig_slot = int(number(r.get("original_slot")))
        x0, y0, bay0 = slot_pos[orig_slot]
        x1, y1 = number(r.get("x")), number(r.get("y"))
        bay1 = r.get("bay", "")
        w = number(r.get("width"), 2000.0) or 2000.0
        h = number(r.get("height"), 2000.0) or 2000.0
        dx, dy = x1 - x0, y1 - y0
        dist = math.hypot(dx, dy)
        is_moved = orig_slot != int(number(r.get("new_slot")))
        if is_moved:
            moved += 1

        equipment.append(
            {
                "name": name,
                "group": group,
                "bay0": bay0,
                "bay1": bay1,
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "w": w,
                "h": h,
                "dx": dx,
                "dy": dy,
                "dist": dist,
                "moved": is_moved,
            }
        )

        gs = group_stats[group]
        gs["count"] += 1
        if is_moved:
            gs["moved"] += 1
            gs["dist_sum"] += dist
            gs["dist_max"] = max(gs["dist_max"], dist)

    groups = [
        {
            "group": g,
            "count": s["count"],
            "moved": s["moved"],
            "avg_dist": (s["dist_sum"] / s["moved"]) if s["moved"] else 0.0,
            "max_dist": s["dist_max"],
        }
        for g, s in sorted(group_stats.items())
    ]

    top_movers = sorted(equipment, key=lambda e: -e["dist"])[:15]

    return {
        "generated_at": summary.get("generated_at_utc", ""),
        "equipment_count": len(equipment),
        "moved": moved,
        "reference_cost": summary.get("reference_cost"),
        "optimized_cost": summary.get("optimized_cost"),
        "cost_reduction": summary.get("cost_reduction"),
        "cost_reduction_pct": summary.get("cost_reduction_pct"),
        "lp_count": summary.get("lp_count"),
        "elapsed_sec": summary.get("elapsed_sec"),
        "groups": groups,
        "top_movers": top_movers,
        "equipment": equipment,
    }


def safe_json(value: Any) -> str:
    return json.dumps(value, ensure_ascii=False, separators=(",", ":")).replace(
        "<", "\\u003c"
    )


HTML_TEMPLATE = r"""<!doctype html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>E3 全局布局-流量联合优化交互展示</title>
<style>
::root{color-scheme:light;--ink:#26232e;--muted:#736d7b;--purple:#783c91;--teal:#168e93;--line:#e6e0e9;--paper:#fff;--bg:#f6f4f8;--red:#b94846;--amber:#d88f31}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}button,select,input{font:inherit}button,select{cursor:pointer}button{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:8px;padding:8px 14px}button:hover{background:#f5f0f8}button[aria-pressed=true]{background:var(--purple);color:#fff;border-color:var(--purple)}select,input[type=text]{max-width:100%;border:1px solid #d6cedd;border-radius:8px;padding:8px 10px;background:#fff;color:var(--ink)}input[type=checkbox]{accent-color:var(--purple);width:16px;height:16px;vertical-align:middle}h1{font-size:clamp(24px,3vw,34px);line-height:1.3;margin:6px 0 10px}h2{font-size:20px;margin:0 0 10px}h3{font-size:16px;margin:0 0 8px}.wrap{max-width:1500px;margin:auto;padding:28px 34px 50px}.eyebrow{color:var(--purple);font-size:13px;font-weight:700;letter-spacing:1.2px}.sub{color:var(--muted);max-width:1150px}.topline{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}.offline{white-space:nowrap;color:var(--muted);font-size:13px;padding-top:10px}.numbers{display:flex;flex-wrap:wrap;gap:16px 44px;margin:22px 0;padding:18px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.number{font-size:28px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}.number small{font-size:14px;font-weight:400;color:var(--muted)}.number.loss{color:var(--red)}.number.saving{color:var(--teal)}.stat-label{font-size:13px;color:var(--muted);margin-top:4px}.panel{background:var(--paper);border:1px solid var(--line);padding:22px;border-radius:12px;margin-bottom:20px}.toolbar{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:center;margin:14px 0}.toolbar label{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}.legend{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:6px 0 12px;min-height:22px}.legend .leg{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);margin-right:10px}.legend .swatch{width:12px;height:12px;display:inline-block;border-radius:2px}.layout-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px}.maps{display:grid;grid-template-columns:1fr 1fr;gap:14px}.mapbox{min-width:0}.map-head{display:flex;justify-content:space-between;align-items:center;padding:2px 6px}.map-head h3{margin:0;font-size:17px}.map-head span{font-size:12px;color:var(--muted)}.map-svg{width:100%;height:560px;display:block;background:#fcfbfd;border-radius:8px}.map-svg text{font-family:inherit}.detail{padding-left:20px;border-left:1px solid var(--line);min-width:0}.detail h3{font-size:19px;line-height:1.4}.kicker{font-size:12px;color:var(--purple);font-weight:700}.detail dl{display:grid;grid-template-columns:118px 1fr;gap:5px 10px;font-size:13px;margin:12px 0}.detail dt{color:var(--muted)}.detail dd{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.dim{color:var(--muted);font-size:13px}.notice{padding:12px 15px;background:#f5f1f8;border-left:3px solid var(--purple);margin:14px 0;font-size:14px}.table-wrap{overflow:auto;margin-top:12px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-size:12px;font-weight:500;white-space:nowrap;background:#faf8fc}td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.ok{color:var(--teal)}.loss{color:var(--red)}.hint{font-size:13px;color:var(--muted)}.two-col{display:grid;grid-template-columns:1fr 1fr;gap:20px}.section-footer{display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:18px}[hidden]{display:none!important}
@media(max-width:1100px){.layout-grid{grid-template-columns:1fr}.detail{border-left:0;border-top:1px solid var(--line);padding:16px 0 0}.maps{grid-template-columns:1fr}.map-svg{height:500px}.two-col{grid-template-columns:1fr}}
@media(max-width:650px){.wrap{padding:20px 14px 40px}.panel{padding:16px}.numbers{gap:14px 22px}.number{font-size:23px}.topline{display:block}.offline{padding-top:0}.toolbar{gap:10px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="topline"><div><div class="eyebrow">WEEK 6 · E3 全局启发式</div><h1>全局布局-流量联合优化交互展示</h1></div><div class="offline">离线展示 · 全部数据已内嵌</div></div>
    <p class="sub">E3 在 E1 固定流量基准上，用「模拟退火（SA）+ 大邻域搜索（LNS）」在固定槽位间重新分配设备，内层周期性重解流量 LP，实现布局与流量的联合优化。下图对比参考布局与 E3 优化布局，设备只能在同尺寸（宽×高）槽位间交换。</p>
    <div class="numbers">
      <div><div class="number" id="n-equipment">-</div><div class="stat-label">可移动设备</div></div>
      <div><div class="number" id="n-moved">-</div><div class="stat-label">位置变化设备</div></div>
      <div><div class="number" id="cost-base">-</div><div class="stat-label">参考成本（流量 × 轨道距离）</div></div>
      <div><div class="number" id="cost-opt">-</div><div class="stat-label">优化成本（流量 × 轨道距离）</div></div>
      <div><div class="number saving" id="cost-delta">-</div><div class="stat-label">成本降幅</div></div>
      <div><div class="number" id="n-lp">-</div><div class="stat-label">内层 LP 求解次数</div></div>
    </div>
  </header>

  <section class="panel">
    <h2>布局对比：参考布局 vs E3 优化布局</h2>
    <div class="toolbar">
      <label>着色<select id="color-mode"><option value="bay">按 Bay</option><option value="group">按设备组</option><option value="dist">按位移量</option></select></label>
      <label><input type="text" id="search" placeholder="搜索设备名 / 设备组 / Bay"></label>
      <label><input type="checkbox" id="moved-only">强调位置变化的设备</label>
    </div>
    <div id="legend" class="legend"></div>
    <div class="layout-grid">
      <div class="maps">
        <div class="mapbox"><div class="map-head"><h3>参考布局</h3><span>设备原始槽位</span></div><svg id="map-before" class="map-svg" viewBox="0 0 1000 560" role="img" aria-label="参考布局"></svg></div>
        <div class="mapbox"><div class="map-head"><h3>E3 优化布局</h3><span>重新分配后的槽位</span></div><svg id="map-after" class="map-svg" viewBox="0 0 1000 560" role="img" aria-label="E3优化布局"></svg></div>
      </div>
      <aside class="detail" id="detail" aria-live="polite"><div class="kicker">设备详情</div><p class="dim">点击图中任一设备查看原始/新槽位与位移。</p></aside>
    </div>
    <p class="hint">设备矩形按最小可见尺寸绘制，仅示意相对位置；坐标轴单位为原始单位 / 1000。位移着色中浅灰表示未移动，深红表示移动距离大。</p>
  </section>

  <section class="panel">
    <h2>设备组移动概览</h2>
    <div class="table-wrap">
      <table><thead><tr><th>设备组</th><th class="num">设备数</th><th class="num">移动数</th><th class="num">平均位移 /1000</th><th class="num">最大位移 /1000</th></tr></thead><tbody id="group-body"></tbody></table>
    </div>
  </section>

  <section class="panel">
    <h2>位移最大的设备</h2>
    <div class="table-wrap">
      <table><thead><tr><th>设备</th><th>设备组</th><th>Bay 变化</th><th class="num">位移 /1000</th></tr></thead><tbody id="movers-body"></tbody></table>
    </div>
  </section>

  <footer class="section-footer"><span>A2 组 · Week 6 · E3 全局布局-流量联合优化</span><span>成本为流量 × 有向轨道最短距离；距离矩阵与内层 LP 均按 E1 口径</span></footer>
</div>
<div id="tooltip" style="position:fixed;display:none;pointer-events:none;background:#fff;border:1px solid #d6cedd;border-radius:8px;padding:9px 12px;font-size:13px;box-shadow:0 6px 20px rgba(0,0,0,.12);z-index:5;max-width:340px"></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
"use strict";
const DATA=JSON.parse(document.getElementById('payload').textContent);
const $=id=>document.getElementById(id);
const tooltip=document.getElementById('tooltip');
const equipment=DATA.equipment;
const bays=[...new Set(equipment.flatMap(e=>[e.bay0,e.bay1]).filter(Boolean))].sort();
const groups=[...new Set(equipment.map(e=>e.group).filter(Boolean))].sort();
const fmt=(n,d=2)=>n==null||n===undefined||Number.isNaN(n)?'-':Number(n).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtInt=n=>Number(n).toLocaleString('zh-CN');
function hashColor(text,s,l){let h=0;for(let i=0;i<text.length;i++)h=(h*31+text.charCodeAt(i))>>>0;return`hsl(${h%360} ${s}% ${l}%)`;}
const bayColor=new Map(bays.map(b=>[b,hashColor(b,52,60)]));
const groupColor=new Map(groups.map(g=>[g,hashColor(g,55,52)]));
const maxDist=Math.max(...equipment.map(e=>e.dist),1);
let B={minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity};
for(const e of equipment){for(const xy of [[e.x0,e.y0],[e.x1,e.y1]]){B.minX=Math.min(B.minX,xy[0]);B.maxX=Math.max(B.maxX,xy[0]);B.minY=Math.min(B.minY,xy[1]);B.maxY=Math.max(B.maxY,xy[1]);}}
const SW=1000,SH=560,PAD=44;
const scale=Math.min((SW-2*PAD)/(B.maxX-B.minX),(SH-2*PAD)/(B.maxY-B.minY));
const X=x=>PAD+(x-B.minX)*scale;
const Y=y=>SH-PAD-(y-B.minY)*scale;
const state={color:'bay',search:'',movedOnly:false,selected:null};
function distColor(e){const t=Math.min(1,e.dist/maxDist);const r=Math.round(205+50*t),g=Math.round(205-180*t),b=Math.round(205-180*t);return`rgb(${r},${g},${b})`;}
function colorFor(e){if(state.color==='group')return groupColor.get(e.group)||'#9aa3ab';if(state.color==='dist')return distColor(e);return bayColor.get(e.bay1)||'#9aa3ab';}
function match(e){if(!state.search)return true;const q=state.search.toLowerCase();return(e.name+' '+e.group+' '+e.bay0+' '+e.bay1).toLowerCase().includes(q);}
function buildSvg(which){
  const opt=which==='after';
  const parts=[];
  for(let i=0;i<equipment.length;i++){
    const e=equipment[i];
    const x=opt?e.x1:e.x0,y=opt?e.y1:e.y0;
    let opacity=1;
    if(state.movedOnly&&!e.moved)opacity=0.10;
    if(!match(e))opacity=0.07;
    if(state.selected===i)opacity=1;
    const px=X(x),py=Y(y);
    const rw=Math.max(e.w*scale,1.8),rh=Math.max(e.h*scale,1.8);
    const sel=state.selected===i;
    parts.push('<rect data-i="'+i+'" x="'+(px-rw/2).toFixed(2)+'" y="'+(py-rh/2).toFixed(2)+'" width="'+rw.toFixed(2)+'" height="'+rh.toFixed(2)+'" fill="'+colorFor(e)+'" stroke="'+(sel?'#6c2b87':'#fff')+'" stroke-width="'+(sel?1.6:0.4)+'" opacity="'+opacity.toFixed(3)+'"/>');
  }
  return parts.join('');
}
function renderMaps(){$('map-before').innerHTML=buildSvg('before');$('map-after').innerHTML=buildSvg('after');}
function renderLegend(){
  const lg=$('legend');
  if(state.color==='dist'){lg.innerHTML='<span class="leg"><span class="swatch" style="background:rgb(205,205,205)"></span>未移动</span><span class="leg"><span class="swatch" style="background:rgb(255,25,25)"></span>移动距离大</span>';return;}
  const map=state.color==='bay'?bayColor:groupColor;
  const items=state.color==='bay'?bays:groups;
  lg.innerHTML=items.slice(0,60).map(x=>'<span class="leg"><span class="swatch" style="background:'+map.get(x)+'"></span>'+x+'</span>').join('')+(items.length>60?'<span class="leg">其余 '+(items.length-60)+' 项未列出</span>':'');
}
function renderDetail(){
  const d=$('detail');
  if(state.selected===null){d.innerHTML='<div class="kicker">设备详情</div><p class="dim">点击图中任一设备查看原始/新槽位与位移。</p>';return;}
  const e=equipment[state.selected];
  d.innerHTML='<div class="kicker">设备详情</div><h3>'+e.name+'</h3>'
    +'<dl><dt>设备组</dt><dd>'+(e.group||'-')+'</dd>'
    +'<dt>Bay</dt><dd>'+(e.bay0===e.bay1?e.bay0:(e.bay0+' → '+e.bay1))+'</dd>'
    +'<dt>原始槽位 /1000</dt><dd>'+fmt(e.x0/1000)+', '+fmt(e.y0/1000)+'</dd>'
    +'<dt>新槽位 /1000</dt><dd>'+fmt(e.x1/1000)+', '+fmt(e.y1/1000)+'</dd>'
    +'<dt>位移 /1000</dt><dd>'+fmt(e.dist/1000,3)+'</dd>'
    +'<dt>占地尺寸 /1000</dt><dd>'+fmt(e.w/1000)+' × '+fmt(e.h/1000)+'</dd></dl>'
    +'<div class="notice">'+(e.moved?'该设备从原始槽位移动到了新槽位。':'该设备保持在原始槽位（同尺寸槽位间未发生交换）。')+'</div>';
}
function wire(svgId){
  const svg=$(svgId);
  svg.addEventListener('mousemove',ev=>{
    const rect=ev.target.closest('rect[data-i]');
    if(!rect){tooltip.style.display='none';return;}
    const e=equipment[+rect.dataset.i];
    tooltip.innerHTML='<b>'+e.name+'</b><br>设备组：'+e.group+'<br>Bay：'+e.bay0+(e.bay0!==e.bay1?' → '+e.bay1:'')+'<br>位移：'+fmt(e.dist/1000,3)+' 千单位';
    tooltip.style.display='block';
    tooltip.style.left=(ev.clientX+14)+'px';
    tooltip.style.top=(ev.clientY+14)+'px';
  });
  svg.addEventListener('mouseleave',()=>{tooltip.style.display='none';});
  svg.addEventListener('click',ev=>{
    const rect=ev.target.closest('rect[data-i]');
    if(!rect)return;
    state.selected=+rect.dataset.i;
    renderDetail();renderMaps();
  });
}
function renderAll(){renderMaps();renderLegend();renderDetail();}
$('n-equipment').textContent=fmtInt(DATA.equipment_count);
$('n-moved').textContent=fmtInt(DATA.moved);
$('cost-base').textContent=fmt(DATA.reference_cost/1e8)+' 亿';
$('cost-opt').textContent=fmt(DATA.optimized_cost/1e8)+' 亿';
const pct=DATA.cost_reduction_pct;
$('cost-delta').textContent=fmt(pct,2)+'%';
$('n-lp').textContent=fmtInt(DATA.lp_count);
$('color-mode').addEventListener('change',e=>{state.color=e.target.value;renderAll();});
$('search').addEventListener('input',e=>{state.search=e.target.value.trim();renderMaps();});
$('moved-only').addEventListener('change',e=>{state.movedOnly=e.target.checked;renderMaps();});
$('group-body').innerHTML=DATA.groups.map(g=>'<tr><td>'+g.group+'</td><td class="num">'+g.count+'</td><td class="num">'+g.moved+'</td><td class="num">'+fmt(g.avg_dist/1000,2)+'</td><td class="num">'+fmt(g.max_dist/1000,2)+'</td></tr>').join('');
$('movers-body').innerHTML=DATA.top_movers.map(e=>'<tr><td><b>'+e.name+'</b></td><td>'+e.group+'</td><td>'+(e.bay0===e.bay1?e.bay0:(e.bay0+' → '+e.bay1))+'</td><td class="num">'+fmt(e.dist/1000,2)+'</td></tr>').join('');
wire('map-before');wire('map-after');
renderAll();
</script>
</body></html>
"""


def main() -> int:
    args = parse_args()
    e3_dir = args.e3_dir.resolve()
    output = args.output.resolve()

    payload = load_payload(e3_dir)
    html_text = HTML_TEMPLATE.replace("__PAYLOAD__", safe_json(payload))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")

    print(f"wrote {output}")
    print(
        f"equipment={payload['equipment_count']} moved={payload['moved']} "
        f"reduction={payload['cost_reduction_pct']:.2f}% groups={len(payload['groups'])}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
