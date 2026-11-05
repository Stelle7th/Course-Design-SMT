#!/usr/bin/env python3
"""Build a self-contained interactive HTML for the E2 full-fab layout results.

Reads E1's reference layout (``selected_equipment_ports.csv``), E1's fixed flows
(``transport_flow.csv``) and E2's optimized layout (``new_layout.csv``,
``e2_summary.json``, ``bay_order.json``), then embeds everything into a single
offline HTML page under ``交互展示/``. No backend, network or dependencies are
required to open the generated page.
"""

from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path
from typing import Any

SCRIPT_DIR = Path(__file__).resolve().parent
if str(SCRIPT_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPT_DIR))

from e2_common import read_csv, read_json  # noqa: E402


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Build interactive HTML for E2 layout results.")
    parser.add_argument("--e1-dir", type=Path, default=Path("output/e1_reference_lp"))
    parser.add_argument("--e2-dir", type=Path, default=Path("output/e2_layout"))
    parser.add_argument(
        "--output",
        type=Path,
        default=Path("交互展示/e2_layout_interactive.html"),
        help="Output HTML path (defaults to 交互展示/e2_layout_interactive.html).",
    )
    return parser.parse_args()


def number(value: Any, default: float = 0.0) -> float:
    try:
        return float(value)
    except (TypeError, ValueError):
        return default


def load_payload(e1_dir: Path, e2_dir: Path) -> dict[str, Any]:
    ref_rows = {r["equipment_name"]: r for r in read_csv(e1_dir / "selected_equipment_ports.csv")}
    opt_rows = {r["equipment_name"]: r for r in read_csv(e2_dir / "new_layout.csv")}
    summary = read_json(e2_dir / "e2_summary.json")

    bay_order_path = e2_dir / "bay_order.json"
    ranked_bays: list[str] = []
    if bay_order_path.exists():
        ranked_bays = read_json(bay_order_path).get("ranked_bays", [])

    equipment: list[dict[str, Any]] = []
    for name, opt in opt_rows.items():
        ref = ref_rows.get(name, {})
        x0 = number(ref.get("position_x"))
        y0 = number(ref.get("position_y"))
        x1 = number(opt.get("x"))
        y1 = number(opt.get("y"))
        w = number(opt.get("width"), 2000.0) or 2000.0
        h = number(opt.get("height"), 2000.0) or 2000.0
        dx = x1 - x0
        dy = y1 - y0
        equipment.append(
            {
                "name": name,
                "group": ref.get("tool_group", ""),
                "bay": opt.get("bay", ref.get("bay", "")),
                "x0": x0,
                "y0": y0,
                "x1": x1,
                "y1": y1,
                "w": w,
                "h": h,
                "dx": dx,
                "dy": dy,
                "dist": math.hypot(dx, dy),
            }
        )

    flows: list[dict[str, Any]] = []
    for r in read_csv(e1_dir / "transport_flow.csv"):
        s = r.get("source_equipment", "")
        t = r.get("target_equipment", "")
        f = number(r.get("flow_lots"))
        if s and t and f > 0:
            flows.append({"s": s, "t": t, "f": f})

    moved = sum(1 for e in equipment if e["dist"] > 1.0)

    return {
        "generated_at": summary.get("generated_at_utc", ""),
        "equipment_count": len(equipment),
        "bay_count": summary.get("bay_count", 0),
        "baseline_cost": summary.get("baseline_cost_manhattan"),
        "optimized_cost": summary.get("optimized_cost_manhattan"),
        "cost_reduction": summary.get("cost_reduction"),
        "cost_reduction_pct": summary.get("cost_reduction_pct"),
        "moved": moved,
        "ranked_bays": ranked_bays,
        "equipment": equipment,
        "flows": flows,
        "bay_infos": summary.get("bay_infos", {}),
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
<title>E2 全厂布局优化交互展示</title>
<style>
:root{color-scheme:light;--ink:#26232e;--muted:#736d7b;--purple:#783c91;--teal:#168e93;--line:#e6e0e9;--paper:#fff;--bg:#f6f4f8;--red:#b94846;--amber:#d88f31}
*{box-sizing:border-box}body{margin:0;background:var(--bg);color:var(--ink);font:15px/1.6 "Microsoft YaHei","PingFang SC",system-ui,sans-serif}button,select,input{font:inherit}button,select{cursor:pointer}button{border:1px solid var(--line);background:#fff;color:var(--ink);border-radius:8px;padding:8px 14px}button:hover{background:#f5f0f8}button[aria-pressed=true]{background:var(--purple);color:#fff;border-color:var(--purple)}select,input[type=text]{max-width:100%;border:1px solid #d6cedd;border-radius:8px;padding:8px 10px;background:#fff;color:var(--ink)}input[type=checkbox]{accent-color:var(--purple);width:16px;height:16px;vertical-align:middle}input[type=range]{vertical-align:middle}h1{font-size:clamp(24px,3vw,34px);line-height:1.3;margin:6px 0 10px}h2{font-size:20px;margin:0 0 10px}h3{font-size:16px;margin:0 0 8px}.wrap{max-width:1480px;margin:auto;padding:28px 34px 50px}.eyebrow{color:var(--purple);font-size:13px;font-weight:700;letter-spacing:1.2px}.sub{color:var(--muted);max-width:1100px}.topline{display:flex;justify-content:space-between;gap:24px;align-items:flex-start}.offline{white-space:nowrap;color:var(--muted);font-size:13px;padding-top:10px}.numbers{display:flex;flex-wrap:wrap;gap:16px 44px;margin:22px 0;padding:18px 0;border-top:1px solid var(--line);border-bottom:1px solid var(--line)}.number{font-size:28px;font-weight:700;line-height:1.2;font-variant-numeric:tabular-nums}.number small{font-size:14px;font-weight:400;color:var(--muted)}.number.loss{color:var(--red)}.number.saving{color:var(--teal)}.stat-label{font-size:13px;color:var(--muted);margin-top:4px}.panel{background:var(--paper);border:1px solid var(--line);padding:22px;border-radius:12px;margin-bottom:20px}.toolbar{display:flex;flex-wrap:wrap;gap:14px 22px;align-items:center;margin:14px 0}.toolbar label{display:flex;align-items:center;gap:8px;color:var(--muted);font-size:14px}.legend{display:flex;gap:7px;flex-wrap:wrap;align-items:center;margin:6px 0 12px;min-height:22px}.legend .leg{display:inline-flex;align-items:center;gap:5px;font-size:12px;color:var(--muted);margin-right:10px}.legend .swatch{width:12px;height:12px;display:inline-block;border-radius:2px}.layout-grid{display:grid;grid-template-columns:minmax(0,1fr) 320px;gap:20px}.maps{display:grid;grid-template-columns:1fr 1fr;gap:14px}.mapbox{min-width:0}.map-head{display:flex;justify-content:space-between;align-items:center;padding:2px 6px}.map-head h3{margin:0;font-size:17px}.map-head span{font-size:12px;color:var(--muted)}.map-svg{width:100%;height:540px;display:block;background:#fcfbfd;border-radius:8px}.map-svg text{font-family:inherit}.detail{padding-left:20px;border-left:1px solid var(--line);min-width:0}.detail h3{font-size:19px;line-height:1.4}.kicker{font-size:12px;color:var(--purple);font-weight:700}.detail dl{display:grid;grid-template-columns:110px 1fr;gap:5px 10px;font-size:13px;margin:12px 0}.detail dt{color:var(--muted)}.detail dd{margin:0;overflow-wrap:anywhere;font-variant-numeric:tabular-nums}.dim{color:var(--muted);font-size:13px}.notice{padding:12px 15px;background:#f5f1f8;border-left:3px solid var(--purple);margin:14px 0;font-size:14px}.bay-order{display:flex;flex-wrap:wrap;gap:8px;margin:10px 0}.bay-chip{font-size:13px;padding:7px 12px;border:1px solid var(--line);border-radius:8px;background:#fff}.bay-chip b{color:var(--purple);margin-right:5px}.table-wrap{overflow:auto;margin-top:12px}table{border-collapse:collapse;width:100%;font-size:13px}th,td{padding:9px 11px;border-bottom:1px solid var(--line);text-align:left}th{color:var(--muted);font-size:12px;font-weight:500;white-space:nowrap;background:#faf8fc}td.num{text-align:right;font-variant-numeric:tabular-nums;white-space:nowrap}.ok{color:var(--teal)}.warn{color:var(--amber)}.loss{color:var(--red)}.hint{font-size:13px;color:var(--muted)}.section-footer{display:flex;gap:20px;justify-content:space-between;flex-wrap:wrap;color:var(--muted);font-size:12px;margin-top:18px}[hidden]{display:none!important}
@media(max-width:1100px){.layout-grid{grid-template-columns:1fr}.detail{border-left:0;border-top:1px solid var(--line);padding:16px 0 0}.maps{grid-template-columns:1fr}.map-svg{height:480px}}
@media(max-width:650px){.wrap{padding:20px 14px 40px}.panel{padding:16px}.numbers{gap:14px 22px}.number{font-size:23px}.topline{display:block}.offline{padding-top:0}.toolbar{gap:10px}}
</style>
</head>
<body>
<div class="wrap">
  <header>
    <div class="topline"><div><div class="eyebrow">WEEK 6 · E2 布局优化</div><h1>全厂设备布局优化交互展示</h1></div><div class="offline">离线展示 · 全部数据已内嵌</div></div>
    <p class="sub">对比 E1 参考布局与 E2 优化布局。E2 在固定 E1 流量的前提下，把每个 Bay 内的设备在原有包围盒内重新排布，并给出 Bay 沿主干道的排序建议。距离为设备中心的曼哈顿坐标距离（布局代理）。</p>
    <div class="numbers">
      <div><div class="number" id="n-equipment">-</div><div class="stat-label">可移动设备</div></div>
      <div><div class="number" id="n-bay">-</div><div class="stat-label">Intrabay 数量</div></div>
      <div><div class="number" id="n-moved">-</div><div class="stat-label">位置变化设备</div></div>
      <div><div class="number" id="cost-base">-</div><div class="stat-label">参考成本（流量 × 曼哈顿）</div></div>
      <div><div class="number" id="cost-opt">-</div><div class="stat-label">优化成本（流量 × 曼哈顿）</div></div>
      <div><div class="number" id="cost-delta">-</div><div class="stat-label">成本变化</div></div>
    </div>
  </header>

  <section class="panel">
    <h2>布局对比：优化前 vs 优化后</h2>
    <div class="toolbar">
      <label>着色<select id="color-mode"><option value="bay">按 Bay</option><option value="group">按设备组</option><option value="dist">按位移量</option></select></label>
      <label><input type="text" id="search" placeholder="搜索设备名 / 设备组 / Bay"></label>
      <label><input type="checkbox" id="moved-only">强调位置变化的设备</label>
      <label><input type="checkbox" id="show-flow">显示运输流</label>
      <label id="flow-threshold-wrap" hidden>流量阈值 <span id="flow-threshold-val"></span><input type="range" id="flow-threshold" min="0" max="1" step="0.01" value="0"></label>
    </div>
    <div id="legend" class="legend"></div>
    <div class="layout-grid">
      <div class="maps">
        <div class="mapbox"><div class="map-head"><h3>优化前（E1 参考布局）</h3><span>设备中心坐标</span></div><svg id="map-before" class="map-svg" viewBox="0 0 1000 560" role="img" aria-label="优化前布局"></svg></div>
        <div class="mapbox"><div class="map-head"><h3>优化后（E2 布局）</h3><span>Bay 内重排后的设备中心坐标</span></div><svg id="map-after" class="map-svg" viewBox="0 0 1000 560" role="img" aria-label="优化后布局"></svg></div>
      </div>
      <aside class="detail" id="detail" aria-live="polite"><div class="kicker">设备详情</div><p class="dim">点击图中任一设备查看原位置、新位置与位移。</p></aside>
    </div>
    <p class="hint">设备矩形按最小可见尺寸绘制，仅示意相对位置；坐标轴单位为原始单位 / 1000。位移着色中浅灰表示未移动，深红表示移动距离大。</p>
  </section>

  <section class="panel">
    <h2>Bay 排序建议（L1 · 沿 Interbay 主干道）</h2>
    <p class="hint">按 Bay 间流量最小化「流量 × |位置差|」得到的 1D 排序建议（单位间距，仅用于排序参考，未计入上方的曼哈顿成本）。</p>
    <div class="bay-order" id="bay-order"></div>
  </section>

  <section class="panel">
    <h2>各 Bay 求解状态（L2 · Bay 内布局 MILP）</h2>
    <div class="table-wrap">
      <table><thead><tr><th>Bay</th><th class="num">设备数</th><th>求解状态</th><th class="num">目标值</th><th class="num">原始 Bay 成本</th><th>结果</th></tr></thead><tbody id="bay-status-body"></tbody></table>
    </div>
    <p class="hint">状态「最优」表示达到最优解；「时间上限」表示达到求解时限（可能保留参考布局或采用当前最优整数解）。目标值为该 Bay 内的「流量 × 曼哈顿距离」。</p>
  </section>

  <footer class="section-footer"><span>A2 组 · Week 6 · E2 全厂布局优化</span><span>曼哈顿距离为布局代理，真实搬运距离以 E1 有向轨道图最短路径为准</span></footer>
</div>
<div id="tooltip" style="position:fixed;display:none;pointer-events:none;background:#fff;border:1px solid #d6cedd;border-radius:8px;padding:9px 12px;font-size:13px;box-shadow:0 6px 20px rgba(0,0,0,.12);z-index:5;max-width:340px"></div>
<script id="payload" type="application/json">__PAYLOAD__</script>
<script>
"use strict";
const DATA=JSON.parse(document.getElementById('payload').textContent);
const $=id=>document.getElementById(id);
const tooltip=document.getElementById('tooltip');
const equipment=DATA.equipment,flows=DATA.flows;
const equipIndex=new Map(equipment.map((e,i)=>[e.name,i]));
const bays=[...new Set(equipment.map(e=>e.bay))].sort();
const groups=[...new Set(equipment.map(e=>e.group).filter(Boolean))].sort();
const fmt=(n,d=2)=>n==null||n===undefined||Number.isNaN(n)?'-':Number(n).toLocaleString('zh-CN',{minimumFractionDigits:d,maximumFractionDigits:d});
const fmtInt=n=>Number(n).toLocaleString('zh-CN');
function hashColor(text,s,l){let h=0;for(let i=0;i<text.length;i++)h=(h*31+text.charCodeAt(i))>>>0;return`hsl(${h%360} ${s}% ${l}%)`;}
const bayColor=new Map(bays.map(b=>[b,hashColor(b,52,60)]));
const groupColor=new Map(groups.map(g=>[g,hashColor(g,55,52)]));
const maxFlow=Math.max(...flows.map(f=>f.f),1);
const maxDist=Math.max(...equipment.map(e=>e.dist),1);
let B={minX:Infinity,maxX:-Infinity,minY:Infinity,maxY:-Infinity};
for(const e of equipment){for(const xy of [[e.x0,e.y0],[e.x1,e.y1]]){B.minX=Math.min(B.minX,xy[0]);B.maxX=Math.max(B.maxX,xy[0]);B.minY=Math.min(B.minY,xy[1]);B.maxY=Math.max(B.maxY,xy[1]);}}
const SW=1000,SH=560,PAD=46;
const scale=Math.min((SW-2*PAD)/(B.maxX-B.minX),(SH-2*PAD)/(B.maxY-B.minY));
const X=x=>PAD+(x-B.minX)*scale;
const Y=y=>SH-PAD-(y-B.minY)*scale;
const state={color:'bay',search:'',movedOnly:false,showFlow:false,flowThresh:0,selected:null};
function distColor(e){const t=Math.min(1,e.dist/maxDist);const r=Math.round(205+50*t),g=Math.round(205-180*t),b=Math.round(205-180*t);return`rgb(${r},${g},${b})`;}
function colorFor(e){if(state.color==='group')return groupColor.get(e.group)||'#9aa3ab';if(state.color==='dist')return distColor(e);return bayColor.get(e.bay)||'#9aa3ab';}
function match(e){if(!state.search)return true;const q=state.search.toLowerCase();return(e.name+' '+e.group+' '+e.bay).toLowerCase().includes(q);}
function buildSvg(which){
  const opt=which==='after';
  const parts=[];
  for(let i=0;i<equipment.length;i++){
    const e=equipment[i];
    const x=opt?e.x1:e.x0,y=opt?e.y1:e.y0;
    let opacity=1;
    if(state.movedOnly&&e.dist<=1)opacity=0.10;
    if(!match(e))opacity=0.08;
    if(state.selected===i)opacity=1;
    const px=X(x),py=Y(y);
    const rw=Math.max(e.w*scale,1.8),rh=Math.max(e.h*scale,1.8);
    const sel=state.selected===i;
    parts.push('<rect data-i="'+i+'" x="'+(px-rw/2).toFixed(2)+'" y="'+(py-rh/2).toFixed(2)+'" width="'+rw.toFixed(2)+'" height="'+rh.toFixed(2)+'" fill="'+colorFor(e)+'" stroke="'+(sel?'#6c2b87':'#fff')+'" stroke-width="'+(sel?1.6:0.4)+'" opacity="'+opacity.toFixed(3)+'"/>');
  }
  if(opt&&state.showFlow){
    const thresh=state.flowThresh*maxFlow;
    for(const fl of flows){
      if(fl.f<thresh)continue;
      const a=equipIndex.get(fl.s),b=equipIndex.get(fl.t);
      if(a===undefined||b===undefined)continue;
      const ea=equipment[a],eb=equipment[b];
      const alpha=Math.min(0.6,0.05+0.5*fl.f/maxFlow);
      const lw=Math.max(0.3,Math.min(3,0.3+2.5*Math.sqrt(fl.f/maxFlow)));
      parts.push('<line x1="'+X(ea.x1).toFixed(2)+'" y1="'+Y(ea.y1).toFixed(2)+'" x2="'+X(eb.x1).toFixed(2)+'" y2="'+Y(eb.y1).toFixed(2)+'" stroke="rgba(120,60,145,'+alpha.toFixed(3)+')" stroke-width="'+lw.toFixed(2)+'"/>');
    }
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
  if(state.selected===null){d.innerHTML='<div class="kicker">设备详情</div><p class="dim">点击图中任一设备查看原位置、新位置与位移。</p>';return;}
  const e=equipment[state.selected];
  d.innerHTML='<div class="kicker">设备详情</div><h3>'+e.name+'</h3>'
    +'<dl><dt>设备组</dt><dd>'+(e.group||'-')+'</dd><dt>Bay</dt><dd>'+e.bay+'</dd>'
    +'<dt>原位置 /1000</dt><dd>'+fmt(e.x0/1000)+', '+fmt(e.y0/1000)+'</dd>'
    +'<dt>新位置 /1000</dt><dd>'+fmt(e.x1/1000)+', '+fmt(e.y1/1000)+'</dd>'
    +'<dt>位移 /1000</dt><dd>'+fmt(e.dist/1000,3)+'</dd>'
    +'<dt>占地尺寸 /1000</dt><dd>'+fmt(e.w/1000)+' × '+fmt(e.h/1000)+'</dd></dl>'
    +'<div class="notice">'+(e.dist>1?'该设备位置发生了变化。':'该设备位置保持不变（可能因所在 Bay 未收敛而保留参考布局）。')+'</div>';
}
function wire(svgId){
  const svg=$(svgId);
  svg.addEventListener('mousemove',ev=>{
    const rect=ev.target.closest('rect[data-i]');
    if(!rect){tooltip.style.display='none';return;}
    const e=equipment[+rect.dataset.i];
    tooltip.innerHTML='<b>'+e.name+'</b><br>设备组：'+e.group+'<br>Bay：'+e.bay+'<br>位移：'+fmt(e.dist/1000,3)+' 千单位';
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
// header metrics
$('n-equipment').textContent=fmtInt(DATA.equipment_count);
$('n-bay').textContent=fmtInt(DATA.bay_count);
$('n-moved').textContent=fmtInt(DATA.moved);
$('cost-base').textContent=fmt(DATA.baseline_cost/1e8)+' 亿';
$('cost-opt').textContent=fmt(DATA.optimized_cost/1e8)+' 亿';
const deltaEl=$('cost-delta'),pct=DATA.cost_reduction_pct;
deltaEl.textContent=(pct>0?'+':'')+fmt(pct,3)+'%';
deltaEl.classList.add(pct<0?'loss':'saving');
// controls
$('color-mode').addEventListener('change',e=>{state.color=e.target.value;renderAll();});
$('search').addEventListener('input',e=>{state.search=e.target.value.trim();renderMaps();});
$('moved-only').addEventListener('change',e=>{state.movedOnly=e.target.checked;renderMaps();});
$('show-flow').addEventListener('change',e=>{state.showFlow=e.target.checked;$('flow-threshold-wrap').hidden=!e.target.checked;renderMaps();});
$('flow-threshold').addEventListener('input',e=>{state.flowThresh=Number(e.target.value);$('flow-threshold-val').textContent=fmt(state.flowThresh*maxFlow,1);renderMaps();});
// bay order
$('bay-order').innerHTML=DATA.ranked_bays.length
  ?DATA.ranked_bays.map((b,i)=>'<span class="bay-chip"><b>'+(i+1)+'</b>'+b+'</span>').join('')
  :'<span class="dim">未生成排序结果（L1 未运行或未收敛）。</span>';
// bay status table
const infos=DATA.bay_infos;
const bayNames=Object.keys(infos).sort((a,b)=>a.localeCompare(b,undefined,{numeric:true}));
$('bay-status-body').innerHTML=bayNames.map(b=>{
  const info=infos[b];
  const status=info.status===0?'<span class="ok">最优</span>':(info.status===1?'<span class="warn">时间上限</span>':'<span class="loss">未求解</span>');
  const obj=info.objective==null?'-':fmt(info.objective,1);
  const orig=info.original_bay_cost==null?'-':fmt(info.original_bay_cost,1);
  const kept=info.kept_reference?'保留参考':'已更新';
  return '<tr><td>'+b+'</td><td class="num">'+info.equipment_count+'</td><td>'+status+'</td><td class="num">'+obj+'</td><td class="num">'+orig+'</td><td>'+kept+'</td></tr>';
}).join('');
wire('map-before');wire('map-after');
renderAll();
</script>
</body></html>
"""


def main() -> int:
    args = parse_args()
    e1_dir = args.e1_dir.resolve()
    e2_dir = args.e2_dir.resolve()
    output = args.output.resolve()

    payload = load_payload(e1_dir, e2_dir)
    html_text = HTML_TEMPLATE.replace("__PAYLOAD__", safe_json(payload))
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(html_text, encoding="utf-8")

    print(f"wrote {output}")
    print(
        f"equipment={payload['equipment_count']} flows={len(payload['flows'])} "
        f"moved={payload['moved']} bays={payload['bay_count']}"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
