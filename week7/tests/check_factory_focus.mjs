// Focus/category/camera checks against actual app code. Not a browser render test.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const week=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dom=await import(process.env.SIM_DOM_MODULE||'linkedom');
const html=await fs.readFile(path.join(week,'全厂制造仿真.html'),'utf8');
const {window}=dom.parseHTML(html),{document}=window;
for(const select of document.querySelectorAll('select')){
 let value=select.querySelector('option[selected]')?.value||select.querySelector('option')?.value||'';
 Object.defineProperty(select,'value',{get:()=>value,set:v=>value=String(v)});
}
const code=[...document.querySelectorAll('script')].find(s=>!s.type).textContent;
const context=vm.createContext({window,document,console,Blob,URL,setTimeout:()=>0,requestAnimationFrame:()=>0});
vm.runInContext(code,context);
const app=window.FactorySim,D=app.data,$=id=>document.getElementById(id);
for(const name of ['setFilters','scopeSnapshot','setColorMode','setCameraMode','runDemo'])assert.equal(typeof app[name],'function',name+' API');
app.pause();
const clear=()=>app.setFilters({product:-1,process:'',group:'',step:-1,isolate:false});
const sorted=values=>[...values].sort((a,b)=>a-b);
const equalIds=(actual,expected,message)=>assert.deepEqual(sorted(actual),sorted(expected),message);
const category=group=>D.categories.groupToCategory[group];
const equipmentNode=id=>document.querySelector(`[data-equipment="${D.equipment[id].name}"]`);
const vehicleNode=id=>document.querySelector(`[data-vehicle="${D.vehicles[id].name}"]`);
function visible(el){for(let node=el;node&&node!==document;node=node.parentNode)if(node.hidden||node.style?.display==='none'||node.getAttribute?.('visibility')==='hidden')return false;return true;}
function scopeVehiclesMatch(filters,scope){
 for(const id of scope.vehicleIds){const vs=app.vehicleState(id);assert.notEqual(vs.phase,'idle','filtered traffic never includes idle cars');assert.notEqual(vs.visit,null);const v=D.visits[vs.visit],lot=D.lots[v.lot];
  if(filters.product>=0)assert.equal(lot.product,filters.product);
  if(filters.process)assert.equal(category(D.equipment[v.target].group),filters.process);
  if(filters.group)assert.equal(D.equipment[v.target].group,filters.group);
  if(filters.step>=0)assert.equal(v.op,filters.step);
 }
 const matches=new Set(scope.vehicleIds);
 D.vehicles.forEach((v,id)=>assert.equal(vehicleNode(id).dataset.scopeMatch,matches.has(id)?'true':'false','vehicle scope metadata'));
}
const baseline=new Map([10,180,720].map(t=>[t,JSON.stringify(app.snapshot(t))]));
assert.equal(D.categories.definitions.length,12);
assert.equal(Object.keys(D.categories.groupToCategory).length,108);
clear();app.setTime(180);
const product=4,time=app.getState().time;
app.setFilters({product,process:'',group:'',step:-1,isolate:true});
let scope=app.scopeSnapshot();assert.equal(scope.filtered,true);assert.equal(app.getState().time,time,'filtering never advances model time');
equalIds(scope.lotIds,D.lots.flatMap((l,id)=>l.product===product&&l.release<=time?[id]:[]),'product scope includes released lots, including completed');
const visited=new Set();D.visits.forEach(v=>{if(D.lots[v.lot].product===product&&v.request<=time){visited.add(v.source);visited.add(v.target);}});
equalIds(scope.equipmentIds,visited,'product equipment is the actual source/target visit history, not every compatible machine');
assert.ok(scope.equipmentIds.length>0&&scope.equipmentIds.length<1068);
scopeVehiclesMatch({product},scope);
for(let id=0;id<D.vehicles.length;id++)if(!new Set(scope.vehicleIds).has(id))assert.equal(visible(vehicleNode(id)),false,'isolated product hides unrelated cars');
const activeVisit=D.visits.find(v=>D.lots[v.lot].product===4&&category(D.equipment[v.target].group)==='Dry_Etch'&&v.depart!==null&&v.arrive>v.depart&&v.depart<720);
assert.ok(activeVisit,'a part_5 dry etch transfer exists');
const middle=(activeVisit.depart+Math.min(activeVisit.arrive,720))/2;
app.setTime(middle);
const exact={product:4,process:'Dry_Etch',group:D.equipment[activeVisit.target].group,step:activeVisit.op,isolate:true};
app.setFilters(exact);scope=app.scopeSnapshot();assert.ok(scope.vehicleIds.includes(activeVisit.vehicle),'exact operation keeps its executing car');scopeVehiclesMatch(exact,scope);
for(const id of scope.equipmentIds)assert.equal(D.equipment[id].group,exact.group);
for(const id of scope.lotIds){const ls=app.lotState(id);assert.equal(D.lots[id].product,4);assert.equal(ls.op,activeVisit.op);assert.ok(!['complete','unreleased'].includes(ls.phase));}
app.setFilters({product:-1,process:'Dry_Etch',group:'',step:-1,isolate:true});scope=app.scopeSnapshot();
equalIds(scope.equipmentIds,D.equipment.flatMap((e,id)=>e.production&&category(e.group)==='Dry_Etch'?[id]:[]),'a process-only view shows every machine of that class');
scopeVehiclesMatch({product:-1,process:'Dry_Etch'},scope);
app.setFilters({product:4,process:'Dry_Etch',group:'COMMIT',step:-1,isolate:true});scope=app.scopeSnapshot();
assert.equal(scope.lotIds.length,0);assert.equal(scope.vehicleIds.length,0);assert.equal(scope.equipmentIds.length,0);
assert.equal(scope.counts.processing,0);assert.equal(scope.counts.waitingCar,0);assert.equal(scope.counts.waitingMachine,0);
const empty=$('scope-empty')||[...document.querySelectorAll('p,div,span')].find(el=>visible(el)&&/无匹配|没有匹配|没有符合|暂无.*匹配|未找到.*匹配/.test(el.textContent)&&el.children.length===0);
assert.ok(empty&&visible(empty),'a zero-match view explicitly reports no matching objects');
clear();app.setTime(10);app.setColorMode('category');
const palette=new Map(D.categories.definitions.map(d=>[d.id,d.color.toUpperCase()]));
const fills=D.equipment.map((e,id)=>{const el=equipmentNode(id),kind=category(e.group);assert.equal(el.dataset.category,kind);assert.equal(el.getAttribute('fill').toUpperCase(),palette.get(kind));return el.getAttribute('fill');});
app.setTime(360);
D.equipment.forEach((e,id)=>assert.equal(equipmentNode(id).getAttribute('fill'),fills[id],'category colors stay fixed as equipment state changes'));
const current=app.snapshot(),busy=current.machines.findIndex(m=>m.current!==null),idle=current.machines.findIndex((m,id)=>m.current===null&&m.queue.length===0&&D.equipment[id].production);
assert.ok(busy>=0&&idle>=0);assert.notEqual(equipmentNode(busy).getAttribute('stroke'),equipmentNode(idle).getAttribute('stroke'),'category colors retain a visible running-state stroke');
app.setColorMode('status');assert.equal(app.getState().colorMode,'status');assert.equal(equipmentNode(busy).dataset.phase,current.machines[busy].phase);
app.setColorMode('category');
app.setTime(middle);app.select('vehicle',activeVisit.vehicle,false);
let unchanged=app.getState().time;app.setCameraMode('path');assert.equal(app.getState().cameraMode,'path');assert.equal(app.getState().time,unchanged);
let camera=app.getState().camera;
for(const id of [activeVisit.empty,activeVisit.loaded])for(const p of app.pathInfo(id).points){assert.ok(p[0]>=camera.x-1e-6&&p[0]<=camera.x+camera.w+1e-6,'path camera contains route X');assert.ok(p[1]>=camera.y-1e-6&&p[1]<=camera.y+camera.h+1e-6,'path camera contains route Y');}
app.setCameraMode('follow');assert.equal(app.getState().time,unchanged);assert.equal(app.getState().cameraMode,'follow');
let pose=app.vehicleState(activeVisit.vehicle).pose;camera=app.getState().camera;assert.ok(Math.hypot(camera.x+camera.w/2-pose.x,camera.y+camera.h/2-pose.y)<1e-6,'follow centres on selected moving vehicle');
app.setTime(Math.min(activeVisit.arrive-.0001,middle+.01));pose=app.vehicleState(activeVisit.vehicle).pose;camera=app.getState().camera;assert.ok(Math.hypot(camera.x+camera.w/2-pose.x,camera.y+camera.h/2-pose.y)<1e-6,'follow continues as the clock moves');
app.select('equipment',activeVisit.target,false);unchanged=app.getState().time;app.setCameraMode('equipment');camera=app.getState().camera;const e=D.equipment[activeVisit.target];assert.equal(app.getState().cameraMode,'equipment');assert.equal(app.getState().time,unchanged);assert.ok(Math.hypot(camera.x+camera.w/2-e.x,camera.y+camera.h/2-e.y)<1e-6,'equipment view centres on chosen equipment');
app.setCameraMode('free');assert.equal(app.getState().cameraMode,'free');
for(const demo of ['factory','product','process','reentry','queue']){app.runDemo(demo);const s=app.getState();assert.ok(s.time>=0&&s.time<=720);if(demo==='reentry'||demo==='queue'){const name=demo==='reentry'?'Init_Lot_5_20':'Init_Lot_5_12';const selected=s.selection?.type==='lot'?D.lots[s.selection.id].name:'';assert.ok(selected===name||$('inspector-content').textContent.includes(name),demo+' demo exposes its intended batch');}}
app.setTime(180);app.setFilters({product:-1,process:'Delay',group:'',step:-1,isolate:true});scope=app.scopeSnapshot();
const delayLots=D.lots.flatMap((l,i)=>app.lotState(i).phase==='delay'?[i]:[]);equalIds(scope.lotIds,delayLots,'Delay scope retains actual waiting lots');assert.equal(scope.counts.delay,delayLots.length);assert.ok(scope.boundaryIds.length>0);assert.ok(scope.boundaryIds.some(i=>visible(equipmentNode(i))),'Delay keeps source equipment visible as parking context');
app.setFilters({product:4,process:'',group:'',step:-1,isolate:true});
const sharedId=D.equipment.findIndex(e=>e.name==='DIE0111'),shared=app.snapshot().machines[sharedId],other=D.visits[shared.current];assert.notEqual(D.lots[other.lot].product,4);app.select('equipment',sharedId,false);
const relatedPaths=new Set(D.visits.filter(v=>D.lots[v.lot].product===4&&v.target===sharedId&&v.request<=180).flatMap(v=>[v.empty,v.loaded]).filter(i=>i!==null));
for(const line of $('route-layer').querySelectorAll('[data-path]'))assert.ok(relatedPaths.has(Number(line.dataset.path)),'shared equipment route matches selected product');
const otherLink=$('inspector-content').querySelector(`[data-select="lot:${other.lot}"]`);assert.ok(otherLink,'shared queue exposes other-product lot');otherLink.dispatchEvent(new window.Event('click',{bubbles:true}));assert.equal(app.getState().selection.type,'lot');assert.equal(app.getState().selection.id,other.lot);assert.equal(app.getState().product,D.lots[other.lot].product,'cross-product detail explicitly switches filter context');
clear();app.setTime(10);$('clear-selection')?.dispatchEvent(new window.Event('click',{bubbles:true}));
assert.equal(app.scopeSnapshot().filtered,false);
assert.equal([...document.querySelectorAll('[data-vehicle]')].filter(visible).length,500);
assert.equal([...document.querySelectorAll('[data-equipment]')].filter(visible).length,1116);
for(const [t,before]of baseline)assert.equal(JSON.stringify(app.snapshot(t)),before,'view controls do not mutate global simulation results');
const checks={productLineActualHistory:true,processView:true,exactOperation:true,activeFilteredTraffic:true,emptyScopeMessage:true,categoryPalette:true,stateStrokes:true,routeCamera:true,followingCamera:true,equipmentCamera:true,demoExamples:true,delayLocationContext:true,sharedEquipmentRouteFilter:true,crossProductDetailContext:true,globalResultsUnchanged:true,restoreAllResources:true,browserRenderingVerified:false};
for(const [demo,name] of [['factory','factory-by-category'],['product','factory-part5'],['process','factory-dryetch'],['reentry','factory-reentry-route'],['queue','factory-queue-detail']]){
 app.runDemo(demo);const svg=$('factory-map').cloneNode(true);svg.setAttribute('xmlns','http://www.w3.org/2000/svg');svg.setAttribute('width','1600');svg.setAttribute('height','850');const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent=document.querySelector('style').textContent;svg.insertBefore(style,svg.firstChild);await fs.writeFile(path.join(week,'validation',name+'.svg'),svg.outerHTML);
}
await fs.writeFile(path.join(week,'validation/full-factory-focus-checks.json'),JSON.stringify(checks,null,2)+'\n');
console.log(JSON.stringify(checks,null,2));
