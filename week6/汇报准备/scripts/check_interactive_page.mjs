// Non-browser unit checks of authored JavaScript with a minimal in-memory DOM.
// This does not claim browser rendering or browser automation verification.
import fs from 'node:fs';
import vm from 'node:vm';
import path from 'node:path';
import {fileURLToPath} from 'node:url';
const root=path.resolve(path.dirname(fileURLToPath(import.meta.url)),'../../..');
const html=fs.readFileSync(path.join(root,'week6/汇报成稿/MILP交互展示.html'),'utf8');
const payload=html.match(/<script id="milp-data" type="application\/json">([\s\S]*?)<\/script>/)[1];
const data=JSON.parse(payload),js=html.match(/<script>\s*([\s\S]*?)<\/script>/)[1];
new vm.Script(js);
class Element{
  constructor(tag='div',id=''){this.tag=tag;this.id=id;this.attrs={};this.dataset={};this.children=[];this.events={};this._html='';this._text='';this.value='';this.checked=false;this.hidden=false;}
  setAttribute(k,v){this.attrs[k]=String(v);if(k.startsWith('data-'))this.dataset[k.slice(5).replace(/-([a-z])/g,(_,x)=>x.toUpperCase())]=String(v);}
  getAttribute(k){return this.attrs[k];}
  append(...nodes){this.children.push(...nodes);}
  replaceChildren(...nodes){this.children=[...nodes];}
  addEventListener(name,fn){this.events[name]=fn;}
  set textContent(v){this._text=String(v);}
  get textContent(){return this._text;}
  set innerHTML(v){this._html=String(v);this.children=[];for(const match of this._html.matchAll(/<button\b([^>]*)>/g)){const b=new Element('button');for(const a of match[1].matchAll(/([\w-]+)="([^"]*)"/g))b.setAttribute(a[1],a[2]);this.children.push(b);}}
  get innerHTML(){return this._html;}
  querySelectorAll(selector){const name=selector.match(/^\[([^\]]+)\]$/)?.[1];return name?this.children.filter(c=>c.attrs[name]!==undefined):[];}
  click(){this.events.click?.({target:this,preventDefault(){}});}
}
const elements=new Map([...html.matchAll(/\bid="([^"]+)"/g)].map(m=>[m[1],new Element('div',m[1])]));
elements.get('milp-data').textContent=payload;
for(const [id,value]of [['product-filter','all'],['sign-filter','all'],['sort-ops','saving'],['color-mode','group']])elements.get(id).value=value;
for(const id of ['show-before','show-after'])elements.get(id).checked=true;
const tabs=['layout','operations','path'].map(t=>{const e=elements.get('tab-'+t);e.setAttribute('data-tab',t);return e;});
const document={getElementById:id=>elements.get(id)||null,createElement:tag=>new Element(tag),createElementNS:(_,tag)=>new Element(tag),querySelectorAll:s=>s==='[data-tab]'?tabs:[]};
const context=vm.createContext({document,console,Blob,URL,setTimeout,clearTimeout});
vm.runInContext(js,context);
const assert=(b,message)=>{if(!b)throw new Error(message);};
assert(elements.get('map-before').children.filter(n=>n.tag==='g').length===48,'48 reference slots');
assert(elements.get('map-after').children.filter(n=>n.tag==='g').length===48,'48 optimized slots');
assert(elements.get('ops-body').querySelectorAll('[data-show]').length===59,'59 operation rows');
elements.get('mode-equipment').click();elements.get('pick').value='ECH0155';elements.get('pick').events.change({target:elements.get('pick')});
assert(elements.get('detail').innerHTML.includes('S0155')&&elements.get('detail').innerHTML.includes('S0146'),'follow equipment maps old and new slots');
elements.get('mode-slot').click();elements.get('pick').value='S0146';elements.get('pick').events.change({target:elements.get('pick')});
assert(elements.get('detail').innerHTML.includes('ECH0146')&&elements.get('detail').innerHTML.includes('ECH0155'),'slot occupancy identity comparison');
elements.get('color-mode').value='load';elements.get('color-mode').events.change({target:elements.get('color-mode')});
assert(elements.get('map-after').children.filter(n=>n.tag==='g').every(g=>g.children.some(r=>r.attrs.fill?.startsWith('rgb('))),'load color mode');
elements.get('changes-only').checked=true;elements.get('changes-only').events.change({target:elements.get('changes-only')});
assert(elements.get('map-after').children.filter(n=>n.tag==='g'&&n.attrs.opacity==='0.18').length===42,'42 unchanged slots deemphasized');
elements.get('sign-filter').value='negative';elements.get('sign-filter').events.change({target:elements.get('sign-filter')});
assert(elements.get('ops-body').innerHTML.includes('没有工序'),'no worsening operations in this result');
elements.get('sign-filter').value='positive';elements.get('sign-filter').events.change({target:elements.get('sign-filter')});
assert(elements.get('ops-body').querySelectorAll('[data-show]').length===18,'18 improved operations');
for(const op of data.operations){vm.runInContext(`chooseOp(${JSON.stringify(op.key)})`,context);assert(elements.get('network').children.some(e=>e.tag==='path'),'path created '+op.key);}
vm.runInContext(`chooseOp(${JSON.stringify(data.default_operation)})`,context);
assert(elements.get('path-detail').innerHTML.includes('172.418')&&elements.get('path-detail').innerHTML.includes('179.535'),'real incoming distances');
assert(elements.get('path-detail').innerHTML.includes('286.202')&&elements.get('path-detail').innerHTML.includes('269.243'),'real outgoing distances');
assert(elements.get('path-detail').innerHTML.includes('ECH0163')&&elements.get('path-detail').innerHTML.includes('ECH0155'),'real assignment difference stated');
const idList=[...html.matchAll(/\bid="([^"]+)"/g)].map(m=>m[1]);assert(new Set(idList).size===idList.length,'no duplicate static IDs');
const checks={htmlBytes:Buffer.byteLength(html),javascriptSyntax:true,staticIdsUnique:true,referenceSlots:48,optimizedSlots:48,
  equipmentFollow:true,fixedSlotCompare:true,loadColorMode:true,deemphasizedUnchangedSlots:42,improvedOperations:18,worsenedOperations:0,
  pathViewsChecked:data.operations.length,defaultActualIncomingAndOutgoingDistances:true,
  boundaryDataCostTotalsMatch:Math.abs(data.verification.before_cost_sum-data.summary.reference_affected_cost)<1e-4&&Math.abs(data.verification.after_cost_sum-data.summary.objective)<1e-4,
  browserRenderingVerified:false,verificationMethod:'Non-browser JavaScript unit checks with an in-memory DOM stub; no browser or UI automation.'};
fs.writeFileSync(path.join(root,'week6/交互展示/logic-checks.json'),JSON.stringify(checks,null,2));
console.log(JSON.stringify(checks,null,2));
