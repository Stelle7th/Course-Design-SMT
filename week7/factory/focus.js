// Included inside the main application closure by build.py. Filters affect
// observation only; shared machines, traffic and the event model keep running.
const categoryDefs=D.categories.definitions,categoryById=new Map(categoryDefs.map(c=>[c.id,c]));
let scope=null;
const productRouteTrips=D.recipes.map((_,product)=>D.visits.filter(v=>D.lots[v.lot].product===product&&v.dispatch!==null).sort((a,b)=>a.dispatch-b.dispatch));
let productRouteCache={signature:'',time:-Infinity,index:0,pathIds:new Set(),segments:new Map(),drawn:false};
function setProductLineVisible(value){state.showProductLine=!!value;$('show-product-line').checked=state.showProductLine;drawProductLine();}
function drawProductLine(){
 const layer=$('product-route-layer'),enabled=state.product>=0&&state.showProductLine;
 layer.setAttribute('data-product',state.product);layer.setAttribute('data-enabled',enabled);
 $('show-product-line').disabled=state.product<0;$('product-line-legend').hidden=!enabled;
 if(!enabled){layer.replaceChildren();layer.setAttribute('data-paths','');layer.setAttribute('data-segment-count','0');productRouteCache.drawn=false;return;}
 const signature=[state.product,state.process,state.group,state.step].join('|');
 if(productRouteCache.signature!==signature||state.time<productRouteCache.time)productRouteCache={signature,time:state.time,index:0,pathIds:new Set(),segments:new Map(),drawn:false};
 const cache=productRouteCache,trips=productRouteTrips[state.product];let changed=false;
 while(cache.index<trips.length&&trips[cache.index].dispatch<=state.time){const v=trips[cache.index++];if(!visitMatches(v)||cache.pathIds.has(v.loaded))continue;cache.pathIds.add(v.loaded);const p=pathInfo(v.loaded).points;for(let i=1;i<p.length;i++){const a=p[i-1],b=p[i];if(Math.abs(a[0]-b[0])+Math.abs(a[1]-b[1])<1e-9)continue;const first=a.map(n=>n.toFixed(8)).join(','),last=b.map(n=>n.toFixed(8)).join(','),key=first<last?first+'>'+last:last+'>'+first;if(!cache.segments.has(key))cache.segments.set(key,`M${a[0].toFixed(5)} ${a[1].toFixed(5)}L${b[0].toFixed(5)} ${b[1].toFixed(5)}`);}changed=true;}
 cache.time=state.time;$('product-line-label').textContent=cache.pathIds.size?`part_${state.product+1} 载货路线（已派车）`:'当前暂无已分配产品路线';
 if(changed||!cache.drawn){layer.replaceChildren();const d=[...cache.segments.values()].join(' ');if(d){svg('path',{d,class:'route-line','data-role':'product-line-halo',stroke:'#fff','stroke-width':7.5,opacity:.9},layer);svg('path',{d,class:'route-line','data-role':'product-line',stroke:'#7c3aed','stroke-width':4.2,opacity:.85},layer);}layer.setAttribute('data-paths',[...cache.pathIds].sort((a,b)=>a-b).join(','));layer.setAttribute('data-segment-count',cache.segments.size);cache.drawn=true;}
}
function equipmentCategory(group){return categoryById.get(D.categories.groupToCategory[group])||{id:'Delay',label:'工艺等待',color:'#7c879d'};}
function hasScope(){return state.product>=0||!!state.process||!!state.group||state.step>=0;}
function operationFor(visit){const l=D.lots[visit.lot];return D.recipes[l.product][visit.op]||{group:'COMPLETE',step:0};}
function operationMatches(op,index){return (!state.process||equipmentCategory(op.group).id===state.process)&&(!state.group||op.group===state.group)&&(state.step<0||index===state.step);}
function visitMatches(v){return (state.product<0||D.lots[v.lot].product===state.product)&&operationMatches(operationFor(v),v.op);}
function buildScope(){
 const filtered=hasScope(),equipmentMask=D.equipment.map(()=>!filtered),boundaryMask=D.equipment.map(()=>false),vehicleMask=D.vehicles.map(()=>!filtered),lotMask=D.lots.map(()=>!filtered);
 const counts={loaded:0,transport:0,processing:0,waitingCar:0,waitingMachine:0,delay:0,completedSteps:0,complete:0,loadedDistance:0};
 if(filtered){
  if(state.product<0)D.equipment.forEach((e,i)=>{equipmentMask[i]=operationMatches({group:e.group},-1);});
  D.visits.forEach(v=>{if(v.request>state.time||!visitMatches(v))return;
   if(state.product>=0){equipmentMask[v.target]=true;if(!state.process&&!state.group&&state.step<0)equipmentMask[v.source]=true;else boundaryMask[v.source]=true;}else boundaryMask[v.source]=true;
   if(v.pickup===null||v.pickup>state.time)counts.waitingCar++;
   if(v.delivered!==null&&v.delivered<=state.time&&(v.start===null||v.start>state.time))counts.waitingMachine++;
   if(v.duration>0&&v.start!==null&&v.start<=state.time){if(v.end>state.time)counts.processing++;else counts.completedSteps++;}
   if(v.loaded!==null&&v.depart<=state.time)counts.loadedDistance+=D.paths[v.loaded][3]*fraction(state.time,v.depart,v.arrive);
  });
  D.vehicles.forEach((v,i)=>{const vs=snap.vehicles[i];vehicleMask[i]=vs.phase!=='idle'&&vs.visit!==null&&visitMatches(D.visits[vs.visit]);if(vehicleMask[i]){counts.transport++;if(vs.phase==='loaded')counts.loaded++;}});
  D.lots.forEach((l,i)=>{if(state.product>=0&&l.product!==state.product)return;if(l.release>state.time)return;const ls=lotState(i);lotMask[i]=!state.process&&!state.group&&state.step<0?true:ls.phase!=='complete'&&operationMatches(D.recipes[l.product][ls.op]||{group:'COMPLETE'},ls.op);if(lotMask[i]&&ls.phase==='complete')counts.complete++;if(lotMask[i]&&ls.phase==='delay'){counts.delay++;boundaryMask[D.delays[ls.delay].source]=true;}});
 }else Object.assign(counts,{loaded:snap.loaded,transport:500-snap.idle,processing:snap.processing,waitingCar:snap.waitingCar,waitingMachine:snap.waitingMachine,completedSteps:snap.completedSteps,complete:snap.completed,loadedDistance:snap.loadedDistance});
 return {filtered,equipmentMask,boundaryMask,vehicleMask,lotMask,counts};
}
function scopeObjectMatches(type,id){if(!scope||!scope.filtered)return true;if(type==='vehicle')return !!scope.vehicleMask[id];if(type==='equipment')return !!scope.equipmentMask[id];if(type==='lot')return !!scope.lotMask[id];if(type==='bay')return bays.get(id)?.equipment.some(i=>scope.equipmentMask[i]||scope.boundaryMask[i]);return false;}
function scopeSnapshot(){const s=scope||buildScope(),ids=mask=>mask.flatMap((yes,i)=>yes?[i]:[]);return {filtered:s.filtered,lotIds:ids(s.lotMask),vehicleIds:ids(s.vehicleMask),equipmentIds:ids(s.equipmentMask),boundaryIds:ids(s.boundaryMask),counts:{...s.counts}};}
function setFilters(patch={}){
 if('product'in patch&&Number.isInteger(patch.product)&&patch.product>=-1&&patch.product<10){state.product=patch.product;state.step=-1;}
 if('process'in patch&&(patch.process===''||categoryById.has(patch.process)||patch.process==='Delay'))state.process=patch.process;
 if('group'in patch&&(patch.group===''||Object.hasOwn(D.categories.groupToCategory,patch.group)))state.group=patch.group;
 if('step'in patch&&Number.isInteger(patch.step)&&patch.step>=-1&&(patch.step===-1||state.product>=0&&patch.step<D.recipes[state.product].length))state.step=patch.step;
 if('isolate'in patch)state.isolate=!!patch.isolate;
 state.listLimit=150;state.search='';$('search').value='';state.recipePage=state.step>=0?Math.floor(state.step/8):0;
 if(state.product>=0&&state.step<0){const frequencies=new Map();D.lots.forEach((l,i)=>{if(l.product===state.product){const s=lotState(i);if(!['complete','unreleased'].includes(s.phase))frequencies.set(s.op,(frequencies.get(s.op)||0)+1);}});const busiest=[...frequencies.entries()].sort((a,b)=>b[1]-a[1]||a[0]-b[0])[0];if(busiest)state.recipePage=Math.floor(busiest[0]/8);}
 syncFocusControls();refresh(true);
}
function syncFocusControls(){
 $('product-filter').value=String(state.product);$('process-filter').value=state.process;$('isolate-filter').checked=state.isolate;
 $('show-product-line').disabled=state.product<0;$('show-product-line').checked=state.showProductLine;
 const groups=Object.keys(D.categories.groupToCategory).filter(g=>D.categories.groupToCategory[g]!=='Fixed_AMHS'&&(!state.process||equipmentCategory(g).id===state.process));
 $('group-filter').innerHTML='<option value="">全部设备组</option>'+groups.map(g=>`<option value="${esc(g)}">${esc(g)}</option>`).join('');$('group-filter').value=state.group;
 $('step-filter').disabled=state.product<0;$('step-filter').innerHTML='<option value="-1">全部步骤</option>'+(state.product<0?'':D.recipes[state.product].map((r,i)=>`<option value="${i}">第 ${r.step} 步 · ${esc(r.name.replace(/^\d+_/,''))} · ${esc(r.group)}</option>`).join(''));$('step-filter').value=String(state.step);
}
function scopeTitle(){return [state.product<0?'':`part_${state.product+1}`,state.process?(state.process==='Delay'?'工艺等待':categoryById.get(state.process).label):'',state.group,state.step<0?'':`第 ${D.recipes[state.product][state.step].step} 步`].filter(Boolean).join(' · ')||'全厂视图';}
function renderScope(){
 if(!scope)return;const s=scopeSnapshot();$('scope-title').textContent=scopeTitle();$('scope-summary').textContent=s.filtered?`${s.lotIds.length} 批当前相关物料 · ${s.vehicleIds.length} 辆执行搬运 · ${state.process==='Delay'?s.boundaryIds.length+' 个停留端点':s.equipmentIds.length+' 个设备/设施'} · ${s.counts.processing} 批加工 · ${s.counts.waitingCar+s.counts.waitingMachine} 批等资源${s.counts.delay?' · '+s.counts.delay+' 批工艺等待':''}`:'所有产品共享设备和车队 · 上方指标始终统计全厂';$('scope-empty').hidden=!s.filtered||s.lotIds.length>0||s.vehicleIds.length>0;
 $('recipe-view').hidden=state.product<0;
 if(state.product>=0){const recipe=D.recipes[state.product],at=state.recipePage*8,counts=new Map();D.lots.forEach((l,i)=>{if(l.product===state.product){const st=lotState(i);if(!['unreleased','complete'].includes(st.phase))counts.set(st.op,(counts.get(st.op)||0)+1);}});$('recipe-caption').textContent=`part_${state.product+1} 工艺顺序 · ${recipe.length} 步，存在回流`;$('recipe-prev').disabled=at===0;$('recipe-next').disabled=at+8>=recipe.length;$('recipe-page').textContent=`${at+1}–${Math.min(at+8,recipe.length)} / ${recipe.length}`;$('recipe-strip').innerHTML=recipe.slice(at,at+8).map((r,i)=>`<button class="recipe-step ${state.step===at+i?'selected':''}" data-filter-step="${at+i}" style="--category-color:${equipmentCategory(r.group).color}"><span>第 ${r.step} 步</span><strong>${esc(equipmentCategory(r.group).label)}</strong><small>${counts.get(at+i)||0} 批当前在此</small></button>`).join('');}
 $('camera-mode').value=state.cameraMode;
}
function setColorMode(mode){if(!['status','category'].includes(mode))return;state.colorMode=mode;$('equipment-color').value=mode;renderColorLegend();updateEquipment();}
function renderColorLegend(){
 $('category-legend').hidden=state.colorMode!=='category';$('status-equipment-legend').hidden=state.colorMode==='category';
 $('category-legend').innerHTML=categoryDefs.map(c=>`<span><i style="background:${c.color}"></i>${esc(c.label)}</span>`).join('')+'<span class="category-state-note">填色＝种类；绿边＝加工，橙边＝排队</span>';
}
function scopeInspector(){const s=scopeSnapshot(),c=s.counts,product=state.product<0?'':`<p>该产品使用共享设备网络，工艺会跨 Bay 并返回同类设备。</p>`,sample=s.lotIds.find(i=>!['complete','unreleased'].includes(lotState(i).phase));return `<div class="empty-detail"><div class="detail-type">FILTERED VIEW · 不改变全厂运行</div><h2>${esc(scopeTitle())}</h2><p>地图突出当前筛选范围，其他产品仍参与资源竞争。</p>${product}<div class="mini-stats"><div><b>${s.vehicleIds.length}</b>执行相关任务的车</div><div><b>${c.processing}</b>加工中的相关批次</div><div><b>${c.waitingCar}</b>等候车辆 / 接货</div><div><b>${c.waitingMachine}</b>等候加工</div><div><b>${c.delay}</b>工艺等待（不占设备）</div><div><b>${c.completedSteps}</b>已完成相关工序</div><div><b>${num(c.loadedDistance/1000,2)}</b>相关载货距离 / km</div></div>${sample!==undefined?link('lot',sample,'查看一批相关物料 →'):'<p>当前时刻没有符合条件的物料，可调整筛选或时间。</p>'}${section('显示口径','<p>产品视图按本次已经请求的真实搬运和设备位置展示。工艺视图保留该类全部设备；灰色端点是接货来源。设备详情保留共享队列，包含其他产品。</p>')}</div>`;}
function scopeEventMatches(e){if(!hasScope())return true;if(state.product>=0&&D.lots[e[2]].product!==state.product)return false;if(!state.process&&!state.group&&state.step<0)return true;
 if(e[1]==='delay'){const d=D.lots[e[2]].delays.map(i=>D.delays[i]).find(d=>d.start===e[0]);return !!d&&operationMatches({group:'Delay'},d.op);}
 const key={request:'request',dispatch:'dispatch',delivered:'delivered',process:'start',processed:'end',complete:'delivered'}[e[1]];
 const v=D.lots[e[2]].visits.map(i=>D.visits[i]).find(v=>v[key]===e[0]&&(e[1]!=='dispatch'||v.vehicle===e[3]));return !!v&&visitMatches(v);
}
function releaseCamera(){state.follow=false;state.cameraMode='free';$('camera-mode').value='free';}
function fitPoints(points){if(!points.length)return;const x0=Math.min(...points.map(p=>p[0])),x1=Math.max(...points.map(p=>p[0])),y0=Math.min(...points.map(p=>p[1])),y1=Math.max(...points.map(p=>p[1]));cameraAt((x0+x1)/2,(y0+y1)/2,Math.max(16,(x1-x0)*1.14+5,(y1-y0)*320/170*1.14+5));}
function applyCameraMode(){
 const s=state.selection;if(!s)return;
 if(state.cameraMode==='path'){const i=selectedVisit();if(i!==null){const v=D.visits[i],points=[];for(const p of [v.empty,v.loaded])if(p!==null)points.push(...pathInfo(p).points);fitPoints(points);$('view-label').textContent='所选任务 · 路径全景';}}
 else if(state.cameraMode==='equipment'){let i=s.type==='equipment'?s.id:null;const visit=selectedVisit();if(i===null&&visit!==null)i=D.visits[visit].target;if(i===null&&s.type==='lot')i=lotState(s.id).equipment??D.lots[s.id].origin;if(i!==null){const e=D.equipment[i];cameraAt(e.x,e.y,20);$('view-label').textContent=e.name+' · 加工特写';}}
}
function setCameraMode(mode){if(!['free','path','follow','equipment'].includes(mode))return;if(mode!=='free'&&!state.selection){const id=snap.vehicles.findIndex((v,i)=>v.phase==='loaded'&&scopeObjectMatches('vehicle',i));if(id>=0)state.selection={type:'vehicle',id};}
 state.cameraMode=mode;state.follow=mode==='follow'&&['vehicle','lot'].includes(state.selection?.type);if(mode==='follow'&&!state.follow)state.cameraMode='free';
 if(state.follow){const s=state.selection,p=s.type==='vehicle'?vehicleState(s.id).pose:lotState(s.id).pose;cameraAt(p.x,p.y,28);$('view-label').textContent='跟随 · '+(s.type==='vehicle'?D.vehicles[s.id].name:D.lots[s.id].name);}else applyCameraMode();$('camera-mode').value=state.cameraMode;drawDynamic();renderInspector();
}
function runDemo(name){
 if(!['factory','product','process','reentry','queue'].includes(name))return;
 pause();state.selection=null;releaseCamera();state.fullRecipe=false;state.showAllRoutes=false;$('show-all-routes').checked=false;
 setFilters({product:-1,process:'',group:'',step:-1,isolate:true});setColorMode('category');state.camera={x:-8,y:-14,w:320,h:170};updateCamera();state.speed=120;$('speed').value='120';setTab('bays');
 let caption='全厂运行：按设备种类观察布局，再开始播放查看物流和加工。';
 if(name==='factory'){setTime(10);$('view-label').textContent='全厂总览';}
 if(name==='product'){setTime(109);setFilters({product:4});state.showAllRoutes=true;$('show-all-routes').checked=true;setTab('lots');caption='产品工艺：只看 part_5 的当前物料、真实涉及设备和搬运；上方工艺条保留原始顺序。';}
 if(name==='process'){setTime(109);setFilters({process:'Dry_Etch'});setTab('equipment');caption='干刻资源：看同类设备分布和共享队列；设备组还可细选 DE_BE_13 等。';}
 if(name==='reentry'){setTime(109.2);setFilters({product:4});const id=D.lots.findIndex(l=>l.name==='Init_Lot_5_20');select('lot',id,false);setCameraMode('path');state.speed=60;$('speed').value='60';caption='回流批次：第 210–212 步依次经过 A3 干刻 → B16 湿刻 → A2 干刻。可切跟随镜头并播放。';}
 if(name==='queue'){setTime(160.3);setFilters({product:4});const lot=D.lots.find(l=>l.name==='Init_Lot_5_12'),v=lot.visits.map(i=>D.visits[i]).find(v=>D.recipes[lot.product][v.op]?.step===213);select('equipment',v.target);setCameraMode('equipment');caption='排队特写：Init_Lot_5_12 已到 ECH0499，等待至约 177.03 分钟才开始加工。队列包含共享此设备的其他批次。';}
 $('demo-caption').textContent=caption;refresh(true);
}
function setupFocus(){
 $('show-product-line').addEventListener('change',e=>setProductLineVisible(e.target.checked));
 $('product-filter').innerHTML='<option value="-1">全部产品</option>'+D.recipes.map((r,i)=>`<option value="${i}">part_${i+1}</option>`).join('');
 $('process-filter').innerHTML='<option value="">全部工艺</option>'+categoryDefs.filter(c=>c.id!=='Fixed_AMHS').map(c=>`<option value="${c.id}">${esc(c.label)}</option>`).join('')+'<option value="Delay">工艺等待（Delay）</option>';
 $('product-filter').addEventListener('change',e=>setFilters({product:Number(e.target.value),step:-1}));$('process-filter').addEventListener('change',e=>setFilters({process:e.target.value,group:''}));$('group-filter').addEventListener('change',e=>setFilters({group:e.target.value}));$('step-filter').addEventListener('change',e=>setFilters({step:Number(e.target.value)}));$('isolate-filter').addEventListener('change',e=>setFilters({isolate:e.target.checked}));$('equipment-color').addEventListener('change',e=>setColorMode(e.target.value));$('clear-filters').addEventListener('click',()=>setFilters({product:-1,process:'',group:'',step:-1}));
 $('recipe-strip').addEventListener('click',e=>{const b=e.target.closest('[data-filter-step]');if(b)setFilters({step:Number(b.dataset.filterStep),process:'',group:''});});$('recipe-prev').addEventListener('click',()=>{state.recipePage=Math.max(0,state.recipePage-1);renderScope();});$('recipe-next').addEventListener('click',()=>{state.recipePage=Math.min(Math.ceil(D.recipes[state.product].length/8)-1,state.recipePage+1);renderScope();});
 $('camera-mode').addEventListener('change',e=>setCameraMode(e.target.value));document.querySelectorAll('[data-demo]').forEach(b=>b.addEventListener('click',()=>runDemo(b.dataset.demo)));
 syncFocusControls();renderColorLegend();
}
