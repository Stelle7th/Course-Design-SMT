// Offline DOM/JavaScript checks. This is not a browser rendering test.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const here=path.dirname(fileURLToPath(import.meta.url));
const week=path.resolve(here,'..');
const root=path.resolve(week,'..');
const dom=await import(process.env.SIM_DOM_MODULE || 'linkedom');
const html=await fs.readFile(path.join(week,'历史版本/A2_A3局部回放.html'),'utf8');
const {window}=dom.parseHTML(html);
const {document}=window;
const data=JSON.parse(document.getElementById('simulation-data').textContent);
const code=Array.from(document.querySelectorAll('script')).find(s=>!s.type).textContent;
new vm.Script(code);
const ids=Array.from(document.querySelectorAll('[id]')).map(n=>n.id);
assert.equal(new Set(ids).size,ids.length,'unique IDs');
// Linkedom's select.value is getter-only; implement browser-like assignment.
for(const select of document.querySelectorAll('select')) {
  let value=select.querySelector('option[selected]')?.value || select.querySelector('option')?.value || '';
  Object.defineProperty(select,'value',{configurable:true,get:()=>value,set:v=>{value=String(v);}});
}
let rafId=0, scheduled=new Map(), currentTime=0;
const context=vm.createContext({window,document,console,Map,Set,Array,Number,Object,String,Math,Date,JSON,
  Blob,URL:{createObjectURL:()=> 'blob:test',revokeObjectURL(){}},
  setTimeout:()=>0,clearTimeout(){},
  requestAnimationFrame:cb=>{scheduled.set(++rafId,cb);return rafId;},
  cancelAnimationFrame:id=>scheduled.delete(id)});
vm.runInContext(code,context);
for(const match of code.matchAll(/\$\('([^']+)'\)/g)) {
  if(!match[1].endsWith('-')) assert.ok(document.getElementById(match[1]),`DOM element ${match[1]}`);
}
const player=window.SimPlayer;
assert.ok(player);
function click(id){document.getElementById(id).dispatchEvent(new window.Event('click',{bubbles:true}));}
function change(id,value,event='change') {
  document.getElementById(id).value=String(value);
  document.getElementById(id).dispatchEvent(new window.Event(event,{bubbles:true}));
}
function frame(delta){currentTime+=delta;const callbacks=[...scheduled.values()];scheduled.clear();callbacks.forEach(cb=>cb(currentTime));}
function polylinePoints(node) {
  const numbers=(node.getAttribute('d').match(/-?\d+(?:\.\d+)?/g)||[]).map(Number);
  return Array.from({length:numbers.length/2},(_,i)=>[numbers[i*2],numbers[i*2+1]]);
}
function markerCenter(node) {
  return node.localName==='circle' ? [Number(node.getAttribute('cx')),Number(node.getAttribute('cy'))]
    : [Number(node.getAttribute('x'))+Number(node.getAttribute('width'))/2,
       Number(node.getAttribute('y'))+Number(node.getAttribute('height'))/2];
}
function distanceToPolyline(point,points) {
  if(points.length===1)return Math.hypot(point[0]-points[0][0],point[1]-points[0][1]);
  let best=Infinity;
  for(let i=1;i<points.length;i++){
    const a=points[i-1],b=points[i],dx=b[0]-a[0],dy=b[1]-a[1],norm=dx*dx+dy*dy;
    const t=norm?Math.max(0,Math.min(1,((point[0]-a[0])*dx+(point[1]-a[1])*dy)/norm)):0;
    best=Math.min(best,Math.hypot(point[0]-a[0]-t*dx,point[1]-a[1]-t*dy));
  }
  return best;
}
function closePoint(a,b,tolerance=1e-6){assert.ok(Math.hypot(a[0]-b[0],a[1]-b[1])<=tolerance,`${a} vs ${b}`);}
function checkTrackedGeometry(name,task,segment){
  const map=document.getElementById('map-'+name);
  const lot=map.querySelector('[data-role="lot-marker"]');
  assert.ok(lot,'selected material marker exists in every active stage');
  assert.equal(lot.dataset.taskId,task.task_id);
  const incoming=task.timeline.find(s=>s.state==='loaded_in');
  const outgoing=task.timeline.find(s=>s.state==='loaded_out');
  let expected;
  if(segment.state.startsWith('loaded')){
    expected=player.pointAlong(segment.path,.5);
    const line=Array.from(map.querySelectorAll('[data-role="planned-route"]')).find(p=>p.dataset.path===segment.path);
    assert.ok(line,'moving material has its displayed planned line');
    assert.ok(distanceToPolyline(markerCenter(lot),polylinePoints(line))<.025,'material marker lies on displayed planning polyline');
  }else if(['wait_vehicle_in','empty_in','load_in'].includes(segment.state)){
    expected=data.network.paths[incoming.path].points[0];
  }else if(segment.state==='unload_out'){
    expected=data.network.paths[outgoing.path].points.at(-1);
  }else{
    expected=data.network.paths[outgoing.path].points[0];
  }
  closePoint([Number(lot.dataset.worldX),Number(lot.dataset.worldY)],expected);
  const vehicles=Array.from(map.querySelectorAll('[data-role="vehicle-marker"]'));
  assert.ok(vehicles.every(v=>v.dataset.taskId===task.task_id),'default view excludes unrelated task vehicles');
  for(const marker of vehicles){
    if(marker.dataset.moving!=='true')continue;
    const line=Array.from(map.querySelectorAll('[data-role="active-route"]')).find(p=>p.dataset.path===marker.dataset.path);
    assert.ok(line,'moving selected vehicle has a displayed actual path');
    assert.ok(distanceToPolyline(markerCenter(marker),polylinePoints(line))<.025,'vehicle marker lies on its displayed route');
    if(segment.state.startsWith('loaded'))closePoint(markerCenter(marker),markerCenter(lot));
    if(segment.state.startsWith('empty'))assert.equal(line.dataset.loaded,'false','empty pickup route identified separately');
  }
}
assert.equal(player.getState().scenario,'regular');
assert.equal(player.getState().showOtherVehicles,false);
assert.equal(player.getState().view,'factory');
assert.equal(data.factory.counts.equipment,1116);
assert.equal(data.factory.counts.bays,43);
for(const name of ['before','after']){
  const map=document.getElementById('map-'+name);
  const marks=Array.from(map.querySelectorAll('[data-role="factory-equipment"]'));
  assert.equal(marks.length,1116);
  assert.equal(new Set(marks.map(m=>m.dataset.slot)).size,1116);
  assert.equal(marks.filter(m=>m.dataset.simulated==='true').length,48);
  assert.equal(map.querySelectorAll('[data-role="factory-bay"]').length,43);
  assert.equal(map.querySelectorAll('[data-role="factory-bay"][data-bay="InterBay2"]').length,1);
  for(const mark of marks){
    const x=Number(mark.getAttribute('x')),y=Number(mark.getAttribute('y'));
    assert.ok(x>=0&&y>=0&&x+Number(mark.getAttribute('width'))<=700&&y+Number(mark.getAttribute('height'))<=330,'factory view contains every equipment footprint');
    if(mark.querySelector('title').textContent.includes('STOCKER'))assert.equal(mark.dataset.simulated,'false');
  }
}
assert.ok(document.getElementById('factory-summary').textContent.includes('仅 A2/A3'));
const cameraTime=player.getState().time, cameraTask=player.getState().task;
click('zoom-in');assert.ok(player.getState().zoom>1);
assert.equal(document.getElementById('map-before').getAttribute('viewBox'),document.getElementById('map-after').getAttribute('viewBox'));
const cx=player.getState().cameraX;click('pan-right');assert.ok(player.getState().cameraX>cx);
assert.equal(player.getState().time,cameraTime);assert.equal(player.getState().task,cameraTask);
click('reset-camera');assert.equal(player.getState().zoom,1);
document.getElementById('map-before').querySelector('[data-role="factory-bay"][data-bay="A2"]').dispatchEvent(new window.Event('click',{bubbles:true}));
assert.equal(player.getState().view,'local');
click('view-factory');assert.equal(player.getState().view,'factory');
document.getElementById('map-before').querySelector('[data-role="factory-bay"][data-bay="B10"]').dispatchEvent(new window.Event('click',{bubbles:true}));
assert.equal(player.getState().zoom,4);
click('view-local');assert.equal(player.getState().view,'local');
player.setView('factory');
assert.throws(()=>player.setView('invalid'));
assert.throws(()=>player.setZoom(0));
document.getElementById('wide-maps').checked=true;
document.getElementById('wide-maps').dispatchEvent(new window.Event('change',{bubbles:true}));
assert.ok(document.getElementById('map-comparison').classList.contains('wide-maps'));
document.getElementById('wide-maps').checked=false;
document.getElementById('wide-maps').dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(player.getState().taskCount,560);
assert.equal(document.getElementById('task').querySelectorAll('option').length,560);
assert.ok(document.getElementById('task-before').textContent.includes('ECH0163'));
assert.ok(document.getElementById('task-after').textContent.includes('ECH0155'));
const metricInitial=document.getElementById('metrics').textContent;
click('locate');
let st=player.getState();
const regular=data.scenarios.find(s=>s.id==='regular');
const tracked=regular.cases.before.tasks.find(t=>t.task_id===st.task);
assert.equal(st.time,tracked.release);
const incoming=tracked.timeline.find(s=>s.state==='loaded_in');
player.setTime((incoming.t0+incoming.t1)/2);
assert.ok(document.getElementById('task-before').textContent.includes('载货进站'));
assert.equal(document.getElementById('metrics').textContent,metricInitial,'final metrics do not depend on playback');
const processing=tracked.timeline.find(s=>s.state==='processing');
player.setTime((processing.t0+processing.t1)/2);
assert.ok(document.getElementById('task-before').textContent.includes('设备加工'));
assert.ok(player.getState().currentBefore.processing>0);
const beforePause=player.getState().time;
click('play'); frame(0); frame(100);
assert.equal(player.getState().playing,true);
assert.ok(player.getState().time>beforePause);
click('play');
assert.equal(player.getState().playing,false);
assert.equal(scheduled.size,0);
const frozen=player.getState().time;frame(100);assert.equal(player.getState().time,frozen);
change('speed',10);assert.equal(player.getState().speed,10);
click('play');frame(0);const start=player.getState().time;frame(100);
assert.ok(Math.abs(player.getState().time-start-1)<1e-8,'10 min/s advances one minute in 100ms');
player.pause();
change('time',1234.5,'input');assert.equal(player.getState().time,1234.5);
assert.equal(player.getState().playing,false);
click('reset');assert.equal(player.getState().time,0);
click('next-stage');assert.ok(player.getState().time>0);
change('map-view','all');assert.equal(player.getState().view,'all');
change('map-view','focus');assert.equal(player.getState().view,'focus');
assert.throws(()=>player.setSpeed(0));assert.throws(()=>player.selectTask('invalid'));
assert.throws(()=>player.setScenario('invalid'));
let inspected=0;
let routeStages=0;
for(const scenario of data.scenarios) {
  change('scenario',scenario.id);assert.equal(player.getState().scenario,scenario.id);
  assert.equal(player.getState().time,0);
  assert.equal(player.getState().taskCount,560);
  for(const name of ['before','after']){
    const tasks=scenario.cases[name].tasks;
    const representative=[tasks[0],tasks.find(t=>t.part==='part_5'&&t.step===169),tasks.find(t=>t.timeline.some(s=>s.state==='wait_equipment'&&s.t1>s.t0))];
    for(const task of representative.filter(Boolean)) {
      player.selectTask(task.task_id);
      for(const segment of task.timeline) {
        const time=(segment.t0+segment.t1)/2;
        player.setTime(time);
        if(segment.t1-segment.t0>1e-5) assert.equal(player.taskState(task,time).state,segment.state);
        assert.ok(!document.getElementById('task-'+name).textContent.includes('NaN'));
        if(segment.t1-segment.t0>1e-5){checkTrackedGeometry(name,task,segment);routeStages++;}
        inspected++;
      }
    }
  }
  click('jump-end');
  assert.equal(player.getState().currentBefore.completed,560);
  assert.equal(player.getState().currentAfter.completed,560);
  assert.equal(player.getState().currentBefore.processing,0);
  assert.equal(player.getState().currentAfter.equipmentQueue,0);
  player.play();frame(0);assert.equal(player.getState().time,0,'play from end restarts');player.pause();
}
// Other-task traffic is opt-in, and each moving car has its own route overlay.
player.setScenario('regular');
document.getElementById('show-other-vehicles').checked=true;
document.getElementById('show-other-vehicles').dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(player.getState().showOtherVehicles,true);
player.setTime((incoming.t0+incoming.t1)/2);
for(const name of ['before','after']){
  const map=document.getElementById('map-'+name);
  assert.equal(map.querySelectorAll('[data-role="vehicle-marker"]').length,4);
  for(const marker of map.querySelectorAll('[data-role="vehicle-marker"][data-moving="true"]')){
    const line=Array.from(map.querySelectorAll('[data-role="active-route"],[data-role="other-route"]')).find(p=>p.dataset.path===marker.dataset.path&&p.dataset.taskId===marker.dataset.taskId);
    assert.ok(line,'optional traffic also shows its own route');
    assert.ok(distanceToPolyline(markerCenter(marker),polylinePoints(line))<.025);
  }
}
document.getElementById('show-other-vehicles').checked=false;
document.getElementById('show-other-vehicles').dispatchEvent(new window.Event('change',{bubbles:true}));
assert.equal(player.getState().showOtherVehicles,false);
player.setScenario('regular');player.selectTask(tracked.task_id);
player.setTime((incoming.t0+incoming.t1)/2);
const snapshots=path.join(week,'validation');await fs.mkdir(snapshots,{recursive:true});
for(const id of ['map-before','map-after','local-before','local-after']) {
  const svg=document.getElementById(id).cloneNode(true);
  svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  svg.setAttribute('width',id.startsWith('local')?'440':'1050');
  svg.setAttribute('height',id.startsWith('local')?'680':'495');
  await fs.writeFile(path.join(snapshots,id+'.svg'),svg.outerHTML);
}
player.setView('factory');
for(const name of ['before','after']){
  const svg=document.getElementById('map-'+name).cloneNode(true);
  svg.setAttribute('xmlns','http://www.w3.org/2000/svg');
  svg.setAttribute('width','1400');svg.setAttribute('height','660');
  await fs.writeFile(path.join(snapshots,'factory-'+name+'.svg'),svg.outerHTML);
}
const embedded=html.match(/<script id="simulation-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
assert.equal(JSON.parse(embedded).scenarios.length,2);
const old=await fs.readFile(path.join(root,'week6/汇报成稿/MILP交互展示.html'),'utf8');
assert.ok(old.includes('../../week7/全厂制造仿真.html'));
const checks={htmlBytes:Buffer.byteLength(html),scenarioCount:data.scenarios.length,
  tasksPerScenario:560,stagesInspected:inspected,playPause:true,speed:true,seek:true,
  taskTracking:true,scenarioSwitch:true,allTasksCompleteAtEnd:true,metricsStableDuringPlayback:true,
  routeStagesChecked:routeStages,displayedRouteMatchesMovingMarkers:true,
  stationaryMaterialStaysAtPort:true,otherTaskVehiclesOptIn:true,
  fullFactoryEquipment:1116,fullFactoryBays:43,simulatedFactoryEquipment:48,
  fullFactoryBoundsValid:true,synchronizedZoomPan:true,bayNavigation:true,wideMaps:true,
  sourcePageNavigation:true,uniqueIds:true,invalidInputsRejected:true,
  browserRenderingVerified:false,method:'Offline JavaScript execution with Linkedom DOM and controlled animation-frame clock; SVG snapshots inspected separately.'};
await fs.writeFile(path.join(snapshots,'ui-checks.json'),JSON.stringify(checks,null,2)+'\n');
console.log(JSON.stringify(checks,null,2));
