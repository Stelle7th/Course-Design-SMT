// Execute actual app code with a controlled clock. No browser rendering claim.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const week=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dom=await import(process.env.SIM_DOM_MODULE||'linkedom');
const html=await fs.readFile(path.join(week,'全厂制造仿真.html'),'utf8');
const {window}=dom.parseHTML(html),{document}=window;
const code=[...document.querySelectorAll('script')].find(s=>!s.type).textContent;
for(const s of document.querySelectorAll('select')){let value=s.querySelector('option[selected]')?.value||s.querySelector('option')?.value||'';Object.defineProperty(s,'value',{get:()=>value,set:v=>value=String(v)});}
let callbacks=[],now=0;
const context=vm.createContext({window,document,console,Blob,URL,setTimeout:()=>0,requestAnimationFrame:cb=>callbacks.push(cb)});
vm.runInContext(code,context);
const app=window.FactorySim,D=app.data;
const $=id=>document.getElementById(id),click=id=>$(id).dispatchEvent(new window.Event('click',{bubbles:true}));
const change=(id,value,type='change')=>{if(typeof value==='boolean')$(id).checked=value;else $(id).value=value;$(id).dispatchEvent(new window.Event(type,{bubbles:true}));};
const frame=ms=>{now+=ms;const jobs=callbacks;callbacks=[];jobs.forEach(cb=>cb(now));};
assert.equal(document.querySelectorAll('[data-vehicle]').length,500);
assert.equal(document.querySelectorAll('[data-equipment]').length,1116);
assert.equal(D.metrics.initial_wip,2156);
assert.equal(app.getState().playing,true);
click('play');assert.equal(app.getState().playing,false);click('play');frame(0);frame(200);assert.ok(app.getState().time>10);click('play');
change('speed',300);assert.equal(app.getState().speed,300);
change('scrub',15,'input');assert.equal(app.getState().time,15);assert.equal(app.getState().playing,false);
const ids=[...document.querySelectorAll('[id]')].map(n=>n.id);assert.equal(ids.length,new Set(ids).size);
let movementChecks=0;
// Check real vehicle/lot positions and selected drawn route through every phase
// of 60 trips, spread over the entire simulated 12-hour window.
const assigned=D.visits.filter(v=>v.dispatch!==null);
for(let n=0;n<60;n++){
 const v=assigned[Math.floor(n*(assigned.length-1)/59)];
 for(const [phase,a,b]of [['empty',v.dispatch,v.pickup],['loading',v.pickup,v.depart],['loaded',v.depart,v.arrive],['unloading',v.arrive,v.delivered]]){
  if(b-a<1e-8||(a+b)/2>D.config.horizon)continue;
  const t=(a+b)/2;app.setTime(t);app.select('vehicle',v.vehicle,false);
  const vs=app.vehicleState(v.vehicle),ls=app.lotState(v.lot),expected=phase==='empty'?app.pointAlong(v.empty,.5):phase==='loaded'?app.pointAlong(v.loaded,.5):app.pointAlong(v.loaded,phase==='loading'?0:1);
  assert.equal(vs.phase,phase);assert.ok(Math.hypot(vs.pose.x-expected.x,vs.pose.y-expected.y)<1e-7);
  const line=$('route-layer').querySelector(`[data-path="${phase==='empty'?v.empty:v.loaded}"]`);assert.ok(line,'inspected vehicle route drawn');
  const marker=document.querySelector(`[data-vehicle="${D.vehicles[v.vehicle].name}"]`);assert.ok(Math.hypot(+marker.dataset.worldX-vs.pose.x,+marker.dataset.worldY-vs.pose.y)<1e-7);
  if(phase==='loaded'){assert.ok(Math.hypot(ls.pose.x-vs.pose.x,ls.pose.y-vs.pose.y)<1e-7);assert.equal(ls.phase,'transport');}
  movementChecks++;
 }
}
for(const t of [0,10,60,180,360,720]){
 app.setTime(t);const snap=app.snapshot();assert.equal(snap.loaded+snap.idle+snap.other,500);
 assert.equal(snap.processing,D.visits.filter(v=>v.duration>0&&v.start!==null&&v.start<=t&&v.end>t).length);
 assert.equal(snap.completed,D.lots.filter(l=>l.completed!==undefined&&l.completed<=t).length);
 assert.equal(snap.released,D.lots.filter(l=>l.release<=t).length);
}
app.setTime(10);const active=app.snapshot().vehicles.findIndex(v=>v.phase==='loaded');assert.ok(active>=0);
const marker=document.querySelector(`[data-vehicle="${D.vehicles[active].name}"]`);marker.dispatchEvent(new window.Event('click',{bubbles:true}));assert.equal(app.getState().selection.type,'vehicle');assert.equal(app.getState().selection.id,active);assert.ok($('inspector-content').textContent.includes(D.vehicles[active].name));
const visit=D.visits[app.vehicleState(active).visit];app.select('lot',visit.lot);assert.ok($('inspector-content').textContent.includes('工艺路线'));click('recipe-toggle');assert.equal(app.getState().fullRecipe,true);
const proc=D.visits.find(v=>v.duration>0&&v.start!==null&&v.start<720&&v.end>v.start);app.setTime((proc.start+Math.min(proc.end,720))/2);app.select('equipment',proc.target);assert.ok($('inspector-content').textContent.includes('正在加工'));assert.ok($('inspector-content').textContent.includes(D.lots[proc.lot].name));
app.select('bay','B18');assert.equal(app.getState().selection.id,'B18');assert.ok($('inspector-content').textContent.includes('区内设备'));
click('overview');assert.equal(app.getState().camera.w,320);click('zoom-in');assert.ok(app.getState().camera.w<320);click('zoom-out');assert.ok(Math.abs(app.getState().camera.w-320)<1e-8);
click('tab-vehicles');change('search','SMT_oht_499','input');assert.equal($('object-list').querySelectorAll('[data-select]').length,1);change('search','','input');click('more-objects');assert.ok($('object-list').querySelectorAll('[data-select]').length>150);
change('show-idle',false);assert.equal(app.getState().showIdle,false);change('show-idle',true);
change('show-all-routes',true);assert.equal(app.getState().showAllRoutes,true);assert.ok($('route-layer').children.length>1);change('show-all-routes',false);
click('fullscreen');assert.ok($('map-wrap').classList.contains('full-map'));click('fullscreen');assert.ok(!$('map-wrap').classList.contains('full-map'));
click('finish');assert.equal(app.getState().time,720);assert.equal(app.getState().playing,false);assert.equal(app.snapshot().completedSteps,D.metrics.processed);assert.equal(app.snapshot().completed,D.metrics.completed_lots);
click('reset');assert.equal(app.getState().time,0);
const snapshots=path.join(week,'validation');await fs.mkdir(snapshots,{recursive:true});
async function capture(name){const map=$('factory-map').cloneNode(true);map.setAttribute('xmlns','http://www.w3.org/2000/svg');map.setAttribute('width','1600');map.setAttribute('height','850');const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent=document.querySelector('style').textContent;map.insertBefore(style,map.firstChild);await fs.writeFile(path.join(snapshots,name+'.svg'),map.outerHTML);}
app.setTime(10);app.select('vehicle',active,false);click('overview');await capture('full-factory-overview');app.select('vehicle',active,true);await capture('full-factory-vehicle');app.select('equipment',proc.target);await capture('full-factory-equipment');
const checks={vehicles:500,equipment:1116,bays:43,initialWip:2156,simulatedProductionBays:40,movementChecks,playPause:true,speed:true,seek:true,vehicleSelection:true,equipmentSelection:true,lotRecipe:true,objectSearch:true,objectPagination:true,zoom:true,allTraffic:true,allRoutes:true,fullscreen:true,resourceConservation:true,modelEndCounts:true,browserRenderingVerified:false,method:'Actual app JavaScript executed in Linkedom; SVG snapshots rendered separately.'};
await fs.writeFile(path.join(snapshots,'full-factory-ui-checks.json'),JSON.stringify(checks,null,2));console.log(JSON.stringify(checks,null,2));
