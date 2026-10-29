"""Read existing MILP results; create an offline explanation page, no re-solving."""
from pathlib import Path
from collections import defaultdict
import csv,json,sys,hashlib
import numpy as np
import pandas as pd
from scipy.sparse.csgraph import dijkstra
ROOT=Path(__file__).resolve().parents[3];WEEK=ROOT/'week6';REG=WEEK/'汇报准备/MILP_A2_A3'
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as ref
layout=pd.read_csv(REG/'layout_result.csv');local=set(layout.slot_name)
summary=json.loads((REG/'summary.json').read_text(encoding='utf-8'))
orig=pd.read_csv(WEEK/'output/e1_reference_lp_full/transport_flow.csv')
before=[]
for r in orig[orig.source_equipment.isin(local)|orig.target_equipment.isin(local)].itertuples():
    inbound=r.target_equipment in local
    before.append({'part':r.part,'step':int(r.step_to if inbound else r.step_from),'direction':'in' if inbound else 'out',
                   'slot':r.target_equipment if inbound else r.source_equipment,'external_equipment':r.source_equipment if inbound else r.target_equipment,
                   'flow_lots':float(r.flow_lots),'distance_raw':float(r.path_distance),'weighted_distance':float(r.transport_cost)})
after=pd.read_csv(REG/'boundary_flow.csv').to_dict('records')
byop={}
for state,rows in [('before',before),('after',after)]:
    for row in rows:
        key=f"{row['part']}:{int(row['step'])}"
        byop.setdefault(key,{'key':key,'part':row['part'],'step':int(row['step']),'before':[],'after':[]})[state].append(row)
q=pd.read_csv(REG/'regional_operation_demands.csv')
for row in q.itertuples():
    o=byop[f'{row.part}:{row.step}'];o.update(group=row.group,demand=float(row.regional_demand_lots),tau=float(row.tau_per_lot_min))
for o in byop.values():
    o['old_cost']=sum(f['weighted_distance'] for f in o['before']);o['new_cost']=sum(f['weighted_distance'] for f in o['after']);o['saving']=o['old_cost']-o['new_cost']
    if abs(o['saving'])<1e-4:o['saving']=0.
    o['saving_pct']=o['saving']/o['old_cost']*100
ops=sorted(byop.values(),key=lambda r:r['saving'],reverse=True)
assert abs(sum(o['old_cost'] for o in ops)-summary['reference_affected_cost'])<1e-4
assert abs(sum(o['new_cost'] for o in ops)-summary['objective'])<1e-4
counts={'improved':sum(o['saving']>1e-4 for o in ops),'worsened':sum(o['saving']<-1e-4 for o in ops),'same':sum(abs(o['saving'])<=1e-4 for o in ops)}
relocations=pd.read_csv(REG/'equipment_relocation.csv').to_dict('records')
oldy=pd.read_csv(WEEK/'output/e1_reference_lp_full/operation_flow.csv');oldy=oldy[oldy.equipment_name.isin(local)].rename(columns={'equipment_name':'slot'})
newy=pd.read_csv(REG/'processing_flow.csv')
load={}
for label,df in [('before',oldy),('after',newy)]:
    load[label]=df.groupby('slot').machine_time_min.sum().to_dict()
    for slot in layout.slot_name:load[label].setdefault(slot,0.)
slots=layout.to_dict('records')
newoccupant={r['target_slot'].replace('S','ECH'):r['equipment_name'] for r in relocations}
for row in slots:
    row['id']='S'+row['slot_name'].removeprefix('ECH');row['old_equipment']=row['slot_name'];row['new_equipment']=newoccupant.get(row['slot_name'],row['slot_name'])
    row['old_load']=float(load['before'][row['slot_name']]);row['new_load']=float(load['after'][row['slot_name']])
    row['old_util']=row['old_load']/8568;row['new_util']=row['new_load']/8568

# True directed shortest rail paths for every displayed boundary-flow row.
smat={}
for p in (ROOT/'analysis/smat_layout_viz/tables/raw').glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f:smat[p.stem]=list(csv.DictReader(f))
smt=ref.load_smt(WEEK/'data','LVHM');eq,_,_=ref.equipment_and_ports(smat,{r['STN'] for r in smt['tools']})
graph,ni,rm,_=ref.build_rail_graph(smat,'manhattan');dist,diststats=ref.build_equipment_distance_matrix(eq,rm,ni,graph)
ename={e['name']:e for e in eq}
nodes=[None]*len(ni)
for row in smat['Address']:nodes[ni[row['NAME']]]=[round(float(row['POSITION_X'])/1000,5),round(float(row['POSITION_Y'])/1000,5)]
pairrail={(ni[r['from_node']],ni[r['to_node']]):name for name,r in rm.items()}
allrows=before+after
sources=sorted({ni[rm[ename[r['external_equipment'] if r['direction']=='in' else r['slot']]['rail_name']]['to_node']] for r in allrows})
_,pred=dijkstra(graph,directed=True,indices=sources,return_predecessors=True);pidx={v:i for i,v in enumerate(sources)}
def port(e):
    rail=rm[e['rail_name']];a=np.array(nodes[ni[rail['from_node']]]);b=np.array(nodes[ni[rail['to_node']]])
    ratio=e['port_distance_clamped']/rail['length'];return [round(float(x),5) for x in a+(b-a)*ratio]
paths={};maxerr=0
for row in allrows:
    sn,tn=(row['external_equipment'],row['slot']) if row['direction']=='in' else (row['slot'],row['external_equipment'])
    key=sn+'>'+tn
    maxerr=max(maxerr,abs(dist[ename[sn]['index'],ename[tn]['index']]-row['distance_raw']))
    row['path']=key
    if key in paths:continue
    se,te=ename[sn],ename[tn];sr,tr=rm[se['rail_name']],rm[te['rail_name']]
    direct=se['rail_name']==te['rail_name'] and te['port_distance_clamped']>=se['port_distance_clamped'] and np.isclose(dist[se['index'],te['index']],te['port_distance_clamped']-se['port_distance_clamped'])
    if direct:seq=[]
    else:
        a,b=ni[sr['to_node']],ni[tr['from_node']];seq=[b];c=b
        while c!=a:
            c=int(pred[pidx[a],c]);assert c>=0;seq.append(c)
        seq.reverse()
    paths[key]={'start':port(se),'nodes':seq,'end':port(te)}
assert maxerr<1e-5
rails=[[ni[r['FROM_NODE']],ni[r['TO_NODE']]] for r in smat['Rail']]
groups=[]
for group,sub in layout.groupby('original_group'):
    matched=[o for o in ops if o['group']==group]
    groups.append({'group':group,'count':len(sub),'old_cost':sum(o['old_cost'] for o in matched),'new_cost':sum(o['new_cost'] for o in matched),
                    'old_bays':sub.groupby('bay').size().to_dict(),'new_bays':layout[layout.optimized_group.eq(group)].groupby('bay').size().to_dict()})
payload={'summary':summary,'slots':slots,'moves':relocations,'operations':ops,'counts':counts,'groups':groups,'network':{'nodes':nodes,'rails':rails,'paths':paths},
         'default_operation':'part_5:169','source_files':['MILP_A2_A3/summary.json','MILP_A2_A3/layout_result.csv','MILP_A2_A3/boundary_flow.csv','MILP_A2_A3/processing_flow.csv','e1_reference_lp_full/transport_flow.csv'],
         'verification':{'before_cost_sum':sum(o['old_cost'] for o in ops),'after_cost_sum':sum(o['new_cost'] for o in ops),'max_distance_reconstruction_error':maxerr}}
build=WEEK/'交互展示';build.mkdir(exist_ok=True)
(build/'milp-data.json').write_text(json.dumps(payload,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
template=(build/'index.template.html').read_text(encoding='utf-8')
output=WEEK/'汇报成稿/MILP交互展示.html'
output.write_text(template.replace('__MILP_DATA__',json.dumps(payload,ensure_ascii=False,separators=(',',':')).replace('</','<\\/')),encoding='utf-8')
print(json.dumps({'output':str(output),'bytes':output.stat().st_size,'counts':counts,'gain':summary['reference_affected_cost']-summary['objective'],
                  'best_operation':ops[0]['key'],'best_saving':ops[0]['saving'],'worst_operation':ops[-1]['key'],'worst_saving':ops[-1]['saving'],
                  'example':{k:v for k,v in byop['part_5:169'].items() if k not in ['before','after']},'distance_error':maxerr},ensure_ascii=False,indent=2))
