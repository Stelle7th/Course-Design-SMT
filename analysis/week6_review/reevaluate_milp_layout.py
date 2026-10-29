"""Retry only the full-arc LP evaluation of the saved local layout."""
from pathlib import Path
import sys,json,csv,time,copy
import numpy as np
import pandas as pd
from scipy.optimize import linprog
ROOT=Path(__file__).resolve().parents[3]; WEEK=ROOT/'week6'
OUT=WEEK/'汇报准备/新增MILP实验_同阶段'
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as ref
smat={}
for p in (ROOT/'analysis/smat_layout_viz/tables/raw').glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f: smat[p.stem]=list(csv.DictReader(f))
smt=ref.load_smt(WEEK/'data','LVHM')
eq,groups,_=ref.equipment_and_ports(smat,{r['STN'] for r in smt['tools']})
graph,idx,railmeta,_=ref.build_rail_graph(smat,'manhattan')
D,_=ref.build_equipment_distance_matrix(eq,railmeta,idx,graph)
lookup={e['name']:e['index'] for e in eq}; permutation=np.arange(len(eq)); new_eq=copy.deepcopy(eq)
layout=pd.read_csv(OUT/'layout_assignment.csv',encoding='utf-8-sig')
for r in layout.itertuples():
    i,j=lookup[r.equipment_name],lookup[r.slot_owner_in_reference];permutation[i]=j
    for key in ['bay','position_x','position_y','port_name','port_type','rail_name','port_distance','port_distance_clamped','port_selection']:
        new_eq[i][key]=eq[j][key]
newD=D[np.ix_(permutation,permutation)]
ops,demands,_=ref.build_operations(smt,groups,10080,.25)
builder,y,transitions,modelstats=ref.build_lp(ops,new_eq,newD,.85,10080,0)
aub,bub,aeq,beq=builder.matrices()
t=time.perf_counter()
res=linprog(np.asarray(builder.objective),A_ub=aub,b_ub=bub,A_eq=aeq,b_eq=beq,bounds=(0,None),method='highs',options={'time_limit':180})
elapsed=time.perf_counter()-t
summary=json.loads((OUT/'milp_summary.json').read_text(encoding='utf-8'))
summary.setdefault('lp_evaluation_attempts',[]).append(summary['lp_evaluation'])
summary['lp_evaluation']={'success':bool(res.success),'status':int(res.status),'message':res.message,'solve_seconds':elapsed,'time_limit_seconds':180,'model':modelstats}
if res.x is not None:
    solution=ref.evaluate_solution(res,ops,new_eq,y,transitions,10080,.85)
    summary['lp_evaluation'].update({'objective':float(res.fun),'improvement_vs_reference':1-float(res.fun)/summary['reference_cost'],
      'max_all_equality_residual':float(np.max(np.abs(aeq@res.x-beq))),
      'max_capacity_excess_min':float(max(0,np.max(aub@res.x-bub))),
      'nonzero_transport_arcs':solution['nonzero_transport_arcs']})
    for key,name in [('operation_rows','operation_flow.csv'),('transport_rows','transport_flow.csv'),('utilization_rows','device_utilization.csv')]:
        pd.DataFrame(solution[key]).to_csv(OUT/name,index=False,encoding='utf-8-sig')
    if res.success: assert res.fun<=summary['frozen_flow_milp_cost']+1e-2
(OUT/'milp_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary['lp_evaluation'],ensure_ascii=False,indent=2),flush=True)
