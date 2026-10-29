// Product-route overlay checks using actual app JavaScript, not browser rendering.
import fs from 'node:fs/promises';
import path from 'node:path';
import vm from 'node:vm';
import assert from 'node:assert/strict';
import {fileURLToPath} from 'node:url';
const week=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'..');
const dom=await import(process.env.SIM_DOM_MODULE||'linkedom');
const {window}=dom.parseHTML(await fs.readFile(path.join(week,'全厂制造仿真.html'),'utf8'));
const {document}=window;
for(const select of document.querySelectorAll('select')){
 let value=select.querySelector('option[selected]')?.value||select.querySelector('option')?.value||'';
 Object.defineProperty(select,'value',{get:()=>value,set:v=>value=String(v)});
}
const code=[...document.querySelectorAll('script')].find(s=>!s.type).textContent;
vm.runInContext(code,vm.createContext({window,document,console,Blob,URL,setTimeout:()=>0,requestAnimationFrame:()=>0}));
const app=window.FactorySim,D=app.data,$=id=>document.getElementById(id);
assert.equal(typeof app.setProductLineVisible,'function');
assert.ok($('show-product-line'));assert.ok($('product-route-layer'));
app.pause();
const layer=$('product-route-layer'),toggle=$('show-product-line');
const baseline=JSON.stringify(app.snapshot(180));
function expectedIds(){const s=app.getState(),ids=new Set();if(s.product<0)return [];
 for(const v of D.visits){if(v.dispatch===null||v.dispatch>s.time||v.loaded===null||D.lots[v.lot].product!==s.product)continue;
  const op=D.recipes[D.lots[v.lot].product][v.op]||{group:'COMPLETE'};
  if(s.process&&D.categories.groupToCategory[op.group]!==s.process)continue;
  if(s.group&&op.group!==s.group)continue;
  if(s.step>=0&&v.op!==s.step)continue;
  ids.add(v.loaded);
 }return [...ids].sort((a,b)=>a-b);
}
function drawnIds(){return (layer.getAttribute('data-paths')||'').split(',').filter(s=>s.trim()!=='').map(Number).sort((a,b)=>a-b);}
function segments(d){const tokens=(d||'').match(/[MLml]|[-+]?(?:\d*\.\d+|\d+\.?\d*)(?:[eE][-+]?\d+)?/g)||[];let command=null,last=null,out=[];
 for(let i=0;i<tokens.length;){if(/[MLml]/.test(tokens[i]))command=tokens[i++];assert.ok(command==='M'||command==='L','overlay uses explicit source-polyline segments');const p=[Number(tokens[i++]),Number(tokens[i++])];assert.ok(p.every(Number.isFinite));if(command==='L'&&last&&Math.hypot(p[0]-last[0],p[1]-last[1])>1e-8)out.push([last,p]);last=p;command='L';}return out;
}
function expectedSegments(ids){return ids.flatMap(id=>{const p=app.pathInfo(id).points;return p.slice(1).flatMap((b,i)=>Math.hypot(b[0]-p[i][0],b[1]-p[i][1])>1e-8?[[p[i],b]]:[]);});}
// A segment is covered only when collinear source intervals span its whole
// length. Endpoints/midpoints alone would miss invented bridges over gaps.
function covered(segment,others){const [a,b]=segment,dx=b[0]-a[0],dy=b[1]-a[1],norm=dx*dx+dy*dy,length=Math.sqrt(norm),tol=2e-4;
 const intervals=[];for(const [p,q]of others){if(Math.abs(dx*(p[1]-a[1])-dy*(p[0]-a[0]))/length>tol||Math.abs(dx*(q[1]-a[1])-dy*(q[0]-a[0]))/length>tol)continue;let s=((p[0]-a[0])*dx+(p[1]-a[1])*dy)/norm,t=((q[0]-a[0])*dx+(q[1]-a[1])*dy)/norm;if(s>t)[s,t]=[t,s];s=Math.max(0,s);t=Math.min(1,t);if(t>=s)intervals.push([s,t]);}
 intervals.sort((a,b)=>a[0]-b[0]);let end=0;for(const [s,t]of intervals){if(s>end+tol/length)return false;end=Math.max(end,t);if(end>=1-tol/length)return true;}return false;
}
function assertOverlay({geometry=false}={}){const ids=expectedIds();assert.deepEqual(drawnIds(),ids,'overlay includes exactly dispatched matching loaded paths');
 if(!ids.length){assert.equal(layer.children.length,0);return 0;}
 assert.ok([String(app.getState().product),'part_'+(app.getState().product+1)].includes(layer.getAttribute('data-product')));
 const halo=layer.querySelector('[data-role="product-line-halo"]'),line=layer.querySelector('[data-role="product-line"]');assert.ok(halo&&line,'bold product line has a contrasting halo');assert.equal(layer.querySelectorAll('path').length,2);
 const css=document.querySelector('style').textContent;assert.ok(line.getAttribute('vector-effect')==='non-scaling-stroke'||line.classList.contains('route-line')&&/\.route-line\s*\{[^}]*vector-effect\s*:\s*non-scaling-stroke/.test(css),'product stroke remains bold at every zoom');assert.ok(Number(line.getAttribute('stroke-width'))>=4);assert.ok(Number(halo.getAttribute('stroke-width'))>Number(line.getAttribute('stroke-width')));
 assert.equal(halo.getAttribute('d'),line.getAttribute('d'));assert.ok(layer.getAttribute('pointer-events')==='none'||[line,halo].every(el=>el.getAttribute('pointer-events')==='none'),'overlay never blocks object clicks');
 const actual=segments(line.getAttribute('d'));assert.equal(Number(layer.getAttribute('data-segment-count')),actual.length);
 const keys=actual.map(([a,b])=>[a.map(n=>n.toFixed(4)).join(','),b.map(n=>n.toFixed(4)).join(',')].sort().join('|'));assert.equal(new Set(keys).size,keys.length,'shared segments are deduplicated');
 if(geometry){const expected=expectedSegments(ids);for(const s of actual)assert.ok(covered(s,expected),'drawn segment belongs entirely to real paths');for(const s of expected)assert.ok(covered(s,actual),'no assigned loaded path is omitted');}
 return actual.length;
}
app.setFilters({product:-1,process:'',group:'',step:-1,isolate:true});app.setProductLineVisible(true);assert.equal(toggle.disabled,true);assert.equal(layer.children.length,0);
const svgChildren=[...$('factory-map').children];assert.ok(svgChildren.indexOf(layer)<svgChildren.indexOf($('equipment-layer')),'equipment stays clickable above product routes');
app.setTime(180);app.setFilters({product:4});assert.equal(toggle.disabled,false);assert.equal(app.getState().showProductLine,true);const segmentCount=assertOverlay({geometry:true});assert.ok(segmentCount>0);
// Planned routes are allowed once a car has been assigned, even before pickup.
assert.ok(D.visits.some(v=>v.dispatch!==null&&v.dispatch<=180&&v.depart>180&&D.lots[v.lot].product===4),'fixture has an assigned but not-yet-loaded task');
const planned=D.visits.find(v=>v.dispatch!==null&&v.dispatch<=180&&v.depart>180&&D.lots[v.lot].product===4);assert.ok(drawnIds().includes(planned.loaded));
// Timestamp zero is a valid dispatch, unlike null or future timestamps.
app.setTime(0);const initial=D.visits.find(v=>v.dispatch===0&&v.loaded!==null);assert.ok(initial);app.setFilters({product:D.lots[initial.lot].product,process:'',group:'',step:-1});assertOverlay();assert.ok(drawnIds().includes(initial.loaded));
app.setTime(180);app.setFilters({product:2});assertOverlay();app.setFilters({product:4,process:'Dry_Etch',group:'',step:-1});assertOverlay();
const exact=D.visits.find(v=>D.lots[v.lot].product===4&&v.dispatch!==null&&v.dispatch<=180&&D.categories.groupToCategory[D.equipment[v.target].group]==='Dry_Etch');assert.ok(exact);
app.setFilters({group:D.equipment[exact.target].group,step:exact.op});assertOverlay({geometry:true});
app.setFilters({product:4,process:'Dry_Etch',group:'COMMIT',step:-1});assert.equal(expectedIds().length,0);assertOverlay();
app.setFilters({product:4,process:'',group:'',step:-1});const trip=D.visits.find(v=>D.lots[v.lot].product===4&&v.depart!==null&&v.arrive>v.depart&&v.arrive<=720);assert.ok(trip);app.setTime((trip.depart+trip.arrive)/2);app.select('vehicle',trip.vehicle,false);
const time=app.getState().time,selected=JSON.stringify(app.getState().selection),pose=document.querySelector(`[data-vehicle="${D.vehicles[trip.vehicle].name}"]`).getAttribute('transform'),route=$('route-layer').innerHTML;
assert.ok($('route-layer').querySelector('[data-role="selected-loaded-route"]'));
app.setProductLineVisible(false);assert.equal(layer.children.length,0);assert.equal(app.getState().showProductLine,false);assert.equal(toggle.checked,false);
assert.equal(app.getState().time,time);assert.equal(JSON.stringify(app.getState().selection),selected);assert.equal($('route-layer').innerHTML,route,'hiding product routes preserves individual task route');assert.equal(document.querySelector(`[data-vehicle="${D.vehicles[trip.vehicle].name}"]`).getAttribute('transform'),pose,'hiding line does not move vehicles');
toggle.checked=true;toggle.dispatchEvent(new window.Event('change',{bubbles:true}));assert.equal(app.getState().showProductLine,true);assertOverlay();assert.equal(app.getState().time,time);assert.equal(JSON.stringify(app.snapshot(180)),baseline,'overlay does not alter simulation results');
const folder=path.join(week,'validation');await fs.mkdir(folder,{recursive:true});
async function capture(name){const map=$('factory-map').cloneNode(true);map.setAttribute('xmlns','http://www.w3.org/2000/svg');map.setAttribute('width','1600');map.setAttribute('height','850');const style=document.createElementNS('http://www.w3.org/2000/svg','style');style.textContent=document.querySelector('style').textContent;map.insertBefore(style,map.firstChild);await fs.writeFile(path.join(folder,name+'.svg'),map.outerHTML);}
app.setTime(180);app.setFilters({product:4,process:'',group:'',step:-1});$('clear-selection')?.dispatchEvent(new window.Event('click',{bubbles:true}));$('overview')?.dispatchEvent(new window.Event('click',{bubbles:true}));app.setProductLineVisible(true);await capture('product-line-visible');app.setProductLineVisible(false);await capture('product-line-hidden');
const checks={productRouteToggle:true,boldOverlay:true,sharedSegmentsDeduplicated:true,geometryMatchesAssignedLoadedPaths:true,noEmptyTravel:true,noFutureOrUnassignedLookahead:true,zeroTimestampIncluded:true,productSwitch:true,processGroupStepFilters:true,overlayBehindEquipment:true,individualRoutePreserved:true,vehiclesAndTimeUnchanged:true,globalResultsUnchanged:true,part5SegmentsAt180:segmentCount,browserRenderingVerified:false};
await fs.writeFile(path.join(folder,'product-line-checks.json'),JSON.stringify(checks,null,2)+'\n');console.log(JSON.stringify(checks,null,2));
