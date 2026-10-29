"""Local equal-footprint equipment-slot MILP with frozen reference flows.

This is a restricted verification experiment, NOT the full joint layout/flow MILP.
It never changes source data or the member's saved results.
"""
from pathlib import Path
import json, csv, sys, time, copy
import numpy as np
import pandas as pd
from scipy.optimize import milp, Bounds, LinearConstraint, linprog
from scipy.sparse import coo_matrix

ROOT=Path(__file__).resolve().parents[3]
WEEK=ROOT/'week6'; OUT=WEEK/'汇报准备/新增MILP实验_同阶段'
OUT.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as ref
t0=time.perf_counter()
smat={}
for p in (ROOT/'analysis/smat_layout_viz/tables/raw').glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f: smat[p.stem]=list(csv.DictReader(f))
smt=ref.load_smt(WEEK/'data','LVHM')
equipment,groups,_=ref.equipment_and_ports(smat,{r['STN'] for r in smt['tools']})
graph,nodeidx,railmeta,_=ref.build_rail_graph(smat,'manhattan')
D,_=ref.build_equipment_distance_matrix(equipment,railmeta,nodeidx,graph)
n=len(equipment); names={e['name']:e['index'] for e in equipment}
trans=pd.read_csv(WEEK/'output/e1_reference_lp_full/transport_flow.csv',encoding='utf-8-sig')
W=np.zeros((n,n))
for r in trans.itertuples(): W[names[r.source_equipment],names[r.target_equipment]]+=r.flow_lots
base=float(np.sum(W*D))
process={r['STN']:r['STNGRP'] for r in smt['tools']}
pool=[e['index'] for e in equipment if process[e['group']]=='Dry_Etch' and abs(e['width']-2482.66825)<1e-5 and abs(e['height']-3136.002)<1e-5]
swaps=[]
for ii,i in enumerate(pool):
    for j in pool[ii+1:]:
        if equipment[i]['group']==equipment[j]['group']: continue
        if equipment[i]['group'].split('_')[1]!=equipment[j]['group'].split('_')[1]: continue
        k=np.array([a for a in range(n) if a!=i and a!=j])
        delta=float(W[i,k]@(D[j,k]-D[i,k])+W[j,k]@(D[i,k]-D[j,k])+W[k,i]@(D[k,j]-D[k,i])+W[k,j]@(D[k,i]-D[k,j])
                    +W[i,j]*(D[j,i]-D[i,j])+W[j,i]*(D[i,j]-D[j,i]))
        swaps.append((delta,i,j))
swaps.sort()
selected=[]; selection_swaps=[]
for delta,i,j in swaps:
    if i not in selected and j not in selected:
        selected.extend([i,j]);selection_swaps.append({'a':equipment[i]['name'],'b':equipment[j]['name'],'pair_swap_delta':delta})
        if len(selected)>=8: break
M=selected; F=[i for i in range(n) if i not in M]; m=len(M)
external=np.zeros((m,m))
for a,i in enumerate(M):
    for c,k in enumerate(M): external[a,c]=W[i,F]@D[k,F]+W[F,i]@D[F,k]
internal=[(a,b) for a,i in enumerate(M) for b,j in enumerate(M) if a!=b and W[i,j]>1e-10]
c=list(external.ravel()); integrality=[1]*(m*m)
rows=[]; cols=[]; vals=[]; lb=[]; ub=[]
def constraint(coefs,lo,hi):
    r=len(lb)
    for col,value in coefs.items(): rows.append(r);cols.append(col);vals.append(value)
    lb.append(lo);ub.append(hi)
for a in range(m): constraint({a*m+c:1 for c in range(m)},1,1)
for cc in range(m): constraint({a*m+cc:1 for a in range(m)},1,1)
for a,b in internal:
    for cc in range(m):
        for dd in range(m):
            if cc==dd: continue
            v=len(c);c.append(W[M[a],M[b]]*D[M[cc],M[dd]]);integrality.append(0)
            constraint({v:1,a*m+cc:-1},-np.inf,0)
            constraint({v:1,b*m+dd:-1},-np.inf,0)
            constraint({v:1,a*m+cc:-1,b*m+dd:-1},-1,np.inf)
A=coo_matrix((vals,(rows,cols)),shape=(len(lb),len(c))).tocsr()
ts=time.perf_counter()
upper=np.ones(len(c))
allowed=np.ones((m,m),dtype=bool)
for a,i in enumerate(M):
    for cc,k in enumerate(M):
        if equipment[i]['group'].split('_')[1]!=equipment[k]['group'].split('_')[1]:
            upper[a*m+cc]=0; allowed[a,cc]=False
res=milp(np.array(c),integrality=np.array(integrality),bounds=Bounds(np.zeros(len(c)),upper),
         constraints=LinearConstraint(A,lb,ub),options={'time_limit':60,'mip_rel_gap':1e-8})
milptime=time.perf_counter()-ts
if res.x is None: raise RuntimeError(res.message)
z=res.x[:m*m].reshape(m,m); perm=np.arange(n)
assignment=[]
for a,i in enumerate(M):
    cc=int(np.argmax(z[a])); k=M[cc];perm[i]=k
    s,t=equipment[i],equipment[k]
    assignment.append({'equipment_name':s['name'],'group':s['group'],'source_bay':s['bay'],'slot_owner_in_reference':t['name'],
                       'target_bay':t['bay'],'source_x':s['position_x'],'source_y':s['position_y'],
                       'target_x':t['position_x'],'target_y':t['position_y'],'width':s['width'],'height':s['height'],
                       'target_port':t['port_name'],'moved':i!=k})
Dnew=D[np.ix_(perm,perm)]
frozen=float(np.sum(W*Dnew)); constant=float(np.sum(W[np.ix_(F,F)]*D[np.ix_(F,F)]))
assert np.allclose(z.sum(axis=0),1) and np.allclose(z.sum(axis=1),1)
assert abs(frozen-(float(res.fun)+constant))<1e-3
assert frozen<=base+1e-3
for row in assignment:
    s=equipment[names[row['equipment_name']]];t=equipment[names[row['slot_owner_in_reference']]]
    assert s['width']==t['width'] and s['height']==t['height'] and process[s['group']]==process[t['group']]
    assert s['group'].split('_')[1]==t['group'].split('_')[1]
pd.DataFrame(assignment).to_csv(OUT/'layout_assignment.csv',index=False,encoding='utf-8-sig')
summary={'experiment':'restricted local fixed-flow equipment-slot MILP',
         'scope':'8 devices in equal-footprint Dry_Etch slots, with FE/BE stage preserved; all other 1060 production devices fixed; reference operation/transport flows frozen during MILP',
         'selection':'Greedily select four disjoint improving swap pairs from the 127-device same-process equal-footprint pool, then optimize all 8 selected slots jointly.',
         'selection_pairs':selection_swaps,'candidate_pool_count':len(pool),'selected_device_count':m,
         'internal_positive_flow_pairs':len(internal),'binary_count':m*m,'total_variable_count':len(c),'constraint_count':len(lb),
         'solver_status':int(res.status),'solver_message':res.message,'mip_gap':float(res.mip_gap),
         'milp_solve_seconds':milptime,'milp_node_count':int(res.mip_node_count),
         'reference_cost':base,'frozen_flow_milp_cost':frozen,'frozen_flow_improvement':1-frozen/base,
         'restricted_problem_dual_bound':float(res.mip_dual_bound)+constant,
         'moved_device_count':sum(r['moved'] for r in assignment),
         'assumptions':['Equal source/target footprint preserves reference slot occupancy under the same anchor convention.',
                        'Dry_Etch process family and FE/BE stage are preserved; utility/cleanroom compatibility remains unverified.',
                        'A moved equipment uses the target slot port; tracks and ports remain fixed.',
                        'The optimality certificate applies only to this selected frozen-flow subproblem.']}
np.savez_compressed(OUT/'local_model_data.npz',external=external,internal_flow=W[np.ix_(M,M)],slot_distance=D[np.ix_(M,M)],allowed=allowed,constant=constant)
if not internal:
    import itertools
    best=np.inf; checked=0
    for pp in itertools.permutations(range(m)):
        if not all(allowed[a,pp[a]] for a in range(m)): continue
        value=constant+sum(external[a,pp[a]] for a in range(m))
        best=min(best,value);checked+=1
    summary['enumeration_check']={'feasible_permutations':checked,'minimum_cost':best,'absolute_difference_vs_milp':abs(best-frozen)}
    assert abs(best-frozen)<1e-3
(OUT/'milp_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)

# Re-optimize all production/transport flows on this local layout with FULL arcs.
new_eq=copy.deepcopy(equipment)
for i in M:
    slot=equipment[int(perm[i])]
    for key in ['bay','position_x','position_y','port_name','port_type','rail_name','port_distance','port_distance_clamped','port_selection']:
        new_eq[i][key]=slot[key]
ops,demands,_=ref.build_operations(smt,groups,10080,.25)
builder,y,transitions,model_stats=ref.build_lp(ops,new_eq,Dnew,.85,10080,0)
aub,bub,aeq,beq=builder.matrices()
ts=time.perf_counter()
lp=linprog(np.asarray(builder.objective),A_ub=aub,b_ub=bub,A_eq=aeq,b_eq=beq,
           bounds=(0,None),method='highs',options={'time_limit':90})
lptime=time.perf_counter()-ts
summary['lp_evaluation']={'success':bool(lp.success),'status':int(lp.status),'message':lp.message,
                          'solve_seconds':lptime,'model':model_stats}
if lp.x is not None:
    solution=ref.evaluate_solution(lp,ops,new_eq,y,transitions,10080,.85)
    outres=float(np.max(np.abs(aeq@lp.x-beq))); cap=float(max(0,np.max(aub@lp.x-bub)))
    summary['lp_evaluation'].update({'objective':float(lp.fun),'improvement_vs_reference':1-float(lp.fun)/base,
                                    'max_all_equality_residual':outres,'max_capacity_excess_min':cap,
                                    'nonzero_transport_arcs':solution['nonzero_transport_arcs']})
    if lp.success: assert lp.fun<=frozen+1e-2
    for key,filename in [('operation_rows','operation_flow.csv'),('transport_rows','transport_flow.csv'),('utilization_rows','device_utilization.csv')]:
        pd.DataFrame(solution[key]).to_csv(OUT/filename,index=False,encoding='utf-8-sig')
summary['total_preparation_milp_lp_seconds']=time.perf_counter()-t0
(OUT/'milp_summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps({'lp_evaluation':summary['lp_evaluation'],'total_seconds':summary['total_preparation_milp_lp_seconds']},ensure_ascii=False,indent=2),flush=True)
