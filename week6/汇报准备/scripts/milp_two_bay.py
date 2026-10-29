"""Joint equipment-type placement and regional processing/flow MILP.

Real A2/A3 slots and fixed outside boundary supplies/demands are taken from
the member's full reference solution. Outside production is not discarded.
Boundary and internal regional transitions are both retained.
"""
from pathlib import Path
from collections import defaultdict
import argparse,csv,json,sys,time,copy,hashlib
import numpy as np
import pandas as pd
from scipy.optimize import milp,linprog,Bounds,LinearConstraint
from scipy.sparse import coo_matrix

ROOT=Path(__file__).resolve().parents[3];WEEK=ROOT/'week6'
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as ref
parser=argparse.ArgumentParser()
parser.add_argument('--bays',nargs='+',default=['A2','A3'])
parser.add_argument('--time-limit',type=float,default=90)
parser.add_argument('--gap',type=float,default=.001)
args=parser.parse_args(); bays=args.bays
OUT=WEEK/'汇报准备'/('MILP_'+'_'.join(bays));OUT.mkdir(parents=True,exist_ok=True)
started=time.perf_counter()
smat={}
for p in (ROOT/'analysis/smat_layout_viz/tables/raw').glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f:smat[p.stem]=list(csv.DictReader(f))
smt=ref.load_smt(WEEK/'data','LVHM')
equipment,groups,_=ref.equipment_and_ports(smat,{r['STN'] for r in smt['tools']})
graph,idx,railmeta,_=ref.build_rail_graph(smat,'manhattan')
D,_=ref.build_equipment_distance_matrix(equipment,railmeta,idx,graph)
eqidx={e['name']:e['index'] for e in equipment}
slots=[e for e in equipment if e['bay'] in bays]
local={e['name'] for e in slots};C=len(slots)
all_ops,_,_=ref.build_operations(smt,groups,10080,.25)
master={(o['part'],o['step']):o for o in all_ops}
ops_csv=pd.read_csv(WEEK/'output/e1_reference_lp_full/operation_flow.csv',encoding='utf-8-sig')
flow=pd.read_csv(WEEK/'output/e1_reference_lp_full/transport_flow.csv',encoding='utf-8-sig')
reg_ops=ops_csv[ops_csv.equipment_name.isin(local)].groupby(['part','step']).flow_lots.sum()
O=list(reg_ops.index); oi={k:i for i,k in enumerate(O)}
ospec=[master[k] for k in O];q=np.array([reg_ops[k] for k in O]);tau=np.array([o['tau_per_lot'] for o in ospec])
is_src=flow.source_equipment.isin(local);is_dst=flow.target_equipment.isin(local)
internal_reference=flow[is_src&is_dst].groupby(['part','step_from','step_to']).flow_lots.sum()
incoming=flow[~is_src&is_dst].groupby(['part','step_to','source_equipment']).flow_lots.sum()
outgoing=flow[is_src&~is_dst].groupby(['part','step_from','target_equipment']).flow_lots.sum()
ins=defaultdict(list);outs=defaultdict(list)
for (part,step,external),amount in incoming.items():ins[oi[(part,step)]].append((external,float(amount)))
for (part,step,external),amount in outgoing.items():outs[oi[(part,step)]].append((external,float(amount)))
for r in range(len(O)):
    assert sum(v for _,v in ins[r])<=q[r]+1e-7
    assert sum(v for _,v in outs[r])<=q[r]+1e-7
types=sorted({(e['group'],e['width'],e['height']) for e in slots})
counts={k:sum((e['group'],e['width'],e['height'])==k for e in slots) for k in types}
typeidx={k:i for i,k in enumerate(types)}
# Same footprint, process family and explicit FE/BE token are required for a
# type-slot compatibility arc. Some names, e.g. Litho_REG_FE_64, have 4 tokens.
process={r['STN']:r['STNGRP'] for r in smt['tools']}
def stage(g):return next((token for token in g.split('_') if token in {'FE','BE'}),'UNSPECIFIED')
allowed={}
for k,(g,w,h) in enumerate(types):
    allowed[k]=[c for c,e in enumerate(slots) if w==e['width'] and h==e['height'] and process[g]==process[e['group']] and stage(g)==stage(e['group'])]
xb={};yv={};fv=[];objective=[];integ=[];meta=[]
def variable(cost,integer,record):
    v=len(objective);objective.append(cost);integ.append(integer);meta.append(record);return v
for k in range(len(types)):
    for c in allowed[k]:xb[k,c]=variable(0,1,('x',k,c))
capacity=defaultdict(dict);demand=defaultdict(dict);inbal=defaultdict(dict);outbal=defaultdict(dict)
group_slots=defaultdict(set)
for k,cs in allowed.items():
    for c in cs:group_slots[types[k][0]].add(c)
for r,o in enumerate(ospec):
    for c in sorted(group_slots[o['stnfam']]):
        v=variable(0,0,('y',r,c));yv[r,c]=v;demand[r][v]=1;capacity[o['stnfam'],c][v]=tau[r]
        inbal[r,c][v]=-1;outbal[r,c][v]=-1
        slotindex=slots[c]['index']
        for direction,partners in [('in',ins[r]),('out',outs[r])]:
            for external,amount in partners:
                j=eqidx[external];distance=D[j,slotindex] if direction=='in' else D[slotindex,j]
                f=variable(float(distance)/1000,0,('f',direction,r,c,external))
                fv.append((f,direction,r,c,external,amount,float(distance)))
                (inbal if direction=='in' else outbal)[r,c][f]=1
internal_variables=[]
internal_rows=defaultdict(dict)
for (part,s,t),amount in internal_reference.items():
    r,rr=oi[part,s],oi[part,t]
    for c in sorted(group_slots[ospec[r]['stnfam']]):
        for d in sorted(group_slots[ospec[rr]['stnfam']]):
            dd=float(D[slots[c]['index'],slots[d]['index']])
            v=variable(dd/1000,0,('internal_f',r,rr,c,d))
            internal_variables.append((v,r,rr,c,d,dd))
            outbal[r,c][v]=1;inbal[rr,d][v]=1
            internal_rows[part,s,t][v]=1
rows=[];cols=[];vals=[];lower=[];upper=[];rowmeta=[]
def constraint(coefs,lo,hi,desc):
    rr=len(lower)
    for col,value in coefs.items():
        if value:rows.append(rr);cols.append(col);vals.append(value)
    lower.append(lo);upper.append(hi);rowmeta.append(desc)
for k in range(len(types)):constraint({v:1 for (kk,c),v in xb.items() if kk==k},counts[types[k]],counts[types[k]],('equipment_count',k))
for c in range(C):constraint({v:1 for (k,cc),v in xb.items() if cc==c},1,1,('slot_occupancy',c))
for r in range(len(O)):constraint(demand[r],q[r],q[r],('regional_operation_demand',r))
for key,row in inbal.items():constraint(row,0,0,('incoming_balance',*key))
for key,row in outbal.items():constraint(row,0,0,('outgoing_balance',*key))
bdry=defaultdict(dict);amounts={}
for f,direction,r,c,external,amount,distance in fv:
    bdry[direction,r,external][f]=1;amounts[direction,r,external]=amount
for key,row in bdry.items():constraint(row,amounts[key],amounts[key],('boundary_supply_demand',*key))
for key,row in internal_rows.items():constraint(row,float(internal_reference[key]),float(internal_reference[key]),('internal_transition_volume',*key))
for (g,c),row in capacity.items():
    for (k,cc),v in xb.items():
        if cc==c and types[k][0]==g:row[v]=-10080*.85
    constraint(row,-np.inf,0,('group_slot_capacity',g,c))
A=coo_matrix((vals,(rows,cols)),shape=(len(lower),len(objective))).tocsr()
lo=np.zeros(len(objective));hi=np.full(len(objective),np.inf);hi[:len(xb)]=1
fixedlo=lo.copy();fixedhi=hi.copy()
for (k,c),v in xb.items():
    original=(slots[c]['group'],slots[c]['width'],slots[c]['height'])
    fixedlo[v]=fixedhi[v]=float(types[k]==original)
ae=np.array(lower)==np.array(upper);eq=A[ae];eqb=np.array(upper)[ae];ub=A[~ae];ubb=np.array(upper)[~ae]
tr=time.perf_counter()
baseline=linprog(objective,A_ub=ub,b_ub=ubb,A_eq=eq,b_eq=eqb,bounds=list(zip(fixedlo,fixedhi)),method='highs')
baseline_seconds=time.perf_counter()-tr
assert baseline.success,baseline.message
original_local_cost=float(flow.loc[is_src|is_dst,'transport_cost'].sum())
assert abs(baseline.fun*1000-original_local_cost)<max(.1,1e-8*original_local_cost)
tr=time.perf_counter()
result=milp(np.array(objective),integrality=np.array(integ),bounds=Bounds(lo,hi),constraints=LinearConstraint(A,lower,upper),
            options={'time_limit':args.time_limit,'mip_rel_gap':args.gap})
solve_seconds=time.perf_counter()-tr
primary_result=result
secondary=None
if result.x is not None:
    from scipy.sparse import vstack,csr_matrix
    move_objective=np.zeros(len(objective))
    for (k,c),v in xb.items():move_objective[v]=float(types[k][0]!=slots[c]['group'])
    objective_tolerance=max(1e-7,abs(result.fun)*1e-10)
    AA=vstack([A,csr_matrix(np.array(objective)[None,:])],format='csr')
    secondary_started=time.perf_counter()
    secondary=milp(move_objective,integrality=np.array(integ),bounds=Bounds(lo,hi),
        constraints=LinearConstraint(AA,np.r_[lower,-np.inf],np.r_[upper,result.fun+objective_tolerance]),
        options={'time_limit':min(30,args.time_limit),'mip_rel_gap':0})
    secondary_seconds=time.perf_counter()-secondary_started
    if secondary.x is not None:
        from types import SimpleNamespace
        result=SimpleNamespace(x=secondary.x,fun=float(np.array(objective)@secondary.x),
            status=primary_result.status,message=primary_result.message,mip_gap=primary_result.mip_gap,
            mip_dual_bound=primary_result.mip_dual_bound,mip_node_count=primary_result.mip_node_count)
summary={'scope':'joint regional placement, processing and boundary-flow optimization',
 'bays':bays,'equipment_count':C,'group_count':len({e['group'] for e in slots}),'geometry_type_count':len(types),
 'regional_operation_count':len(O),'positive_internal_reference_transitions':len(internal_reference),
 'binary_variables':len(xb),'processing_variables':len(yv),'flow_variables':len(fv)+len(internal_variables),'internal_flow_variables':len(internal_variables),'total_variables':len(objective),
 'constraints':len(lower),'equalities':int(ae.sum()),'capacity_inequalities':int((~ae).sum()),
 'reference_affected_cost':original_local_cost,'fixed_layout_lp_cost':float(baseline.fun*1000),'fixed_layout_lp_seconds':baseline_seconds,
 'solver_status':int(result.status),'solver_message':str(result.message),'solver_seconds':solve_seconds,
 'time_limit_seconds':args.time_limit,'requested_mip_relative_gap':args.gap,
 'config':{'horizon_min':10080,'demand_scale':.25,'effective_time_fraction':.85,'distance':'same directed representative-port Manhattan rail metric as original E1'},
 'boundary':'Regional operation volume, each outside source supply and each outside target demand are fixed from the original full-arc reference solution; outside-outside flows are unchanged.',
 'assumptions':['Only existing slots are used; equipment group, footprint-class counts and FE/BE stage are preserved.',
 'Coordinates, anchors, representative ports and batch-time approximations are inherited from E1.',
 'No complete cleanroom, utility or maintenance clearance specifications are available.',
 'If present, internal route transitions are retained with reference regional volumes; these are conditional local subproblems rather than full-plant routing optimization.'],
 'source_sha256':{str(p.relative_to(ROOT)):hashlib.sha256(p.read_bytes()).hexdigest() for p in [Path(__file__),WEEK/'output/e1_reference_lp_full/operation_flow.csv',WEEK/'output/e1_reference_lp_full/transport_flow.csv']}}
if result.x is not None:
    xx=result.x;absolute=abs(eq@xx-eqb);excess=ub@xx-ubb
    summary.update({'objective':float(result.fun*1000),'improvement_local':1-float(result.fun*1000)/original_local_cost,
                    'mip_gap':float(result.mip_gap),'dual_bound':float(result.mip_dual_bound*1000),'node_count':int(result.mip_node_count),
                    'max_equality_residual':float(max(absolute,default=0)),'max_capacity_excess':float(max(0,max(excess,default=0))),
                    'max_binary_residual':float(np.max(np.abs(xx[:len(xb)]-np.rint(xx[:len(xb)]))))})
    if secondary is not None:
        summary['secondary_minimum_changed_slots']={'success':bool(secondary.success),'status':int(secondary.status),'objective':float(secondary.fun) if secondary.fun is not None else None,'solve_seconds':secondary_seconds,'primary_cost_tolerance_raw':objective_tolerance*1000}
    layout=[]
    for c,slot in enumerate(slots):
        chosen=[k for (k,cc),v in xb.items() if cc==c and xx[v]>.5]
        assert len(chosen)==1
        k=chosen[0];g,w,h=types[k]
        layout.append({'slot_name':slot['name'],'bay':slot['bay'],'position_x':slot['position_x'],'position_y':slot['position_y'],
                       'width':w,'height':h,'port_name':slot['port_name'],'original_group':slot['group'],'optimized_group':g,'changed_group':g!=slot['group']})
    summary['changed_group_slots']=sum(r['changed_group'] for r in layout)
    pd.DataFrame(layout).to_csv(OUT/'layout_result.csv',index=False,encoding='utf-8-sig')
    processing=[];transport=[]
    for (r,c),v in yv.items():
        if xx[v]>1e-8:processing.append({'part':O[r][0],'step':int(O[r][1]),'group':ospec[r]['stnfam'],'slot':slots[c]['name'],'bay':slots[c]['bay'],'flow_lots':xx[v],'tau_min':tau[r],'machine_time_min':xx[v]*tau[r]})
    for f,direction,r,c,external,amount,dd in fv:
        if xx[f]>1e-8:transport.append({'part':O[r][0],'step':int(O[r][1]),'direction':direction,'slot':slots[c]['name'],'bay':slots[c]['bay'],'external_equipment':external,'flow_lots':xx[f],'distance_raw':dd,'weighted_distance':xx[f]*dd})
    pd.DataFrame(processing).to_csv(OUT/'processing_flow.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(transport).to_csv(OUT/'boundary_flow.csv',index=False,encoding='utf-8-sig')
    internal_export=[]
    for v,r,rr,c,d,dd in internal_variables:
        if xx[v]>1e-8:internal_export.append({'part':O[r][0],'step_from':int(O[r][1]),'step_to':int(O[rr][1]),'source_slot':slots[c]['name'],'target_slot':slots[d]['name'],'source_bay':slots[c]['bay'],'target_bay':slots[d]['bay'],'flow_lots':xx[v],'distance_raw':dd,'weighted_distance':xx[v]*dd})
    pd.DataFrame(internal_export,columns=['part','step_from','step_to','source_slot','target_slot','source_bay','target_bay','flow_lots','distance_raw','weighted_distance']).to_csv(OUT/'internal_flow.csv',index=False,encoding='utf-8-sig')
    # A separate LP with the chosen placement fixed verifies the reported layout.
    eval_lo=lo.copy();eval_hi=hi.copy();eval_lo[:len(xb)]=np.rint(xx[:len(xb)]);eval_hi[:len(xb)]=np.rint(xx[:len(xb)])
    ev=linprog(objective,A_ub=ub,b_ub=ubb,A_eq=eq,b_eq=eqb,bounds=list(zip(eval_lo,eval_hi)),method='highs')
    summary['fixed_milp_layout_lp']={'success':bool(ev.success),'objective':float(ev.fun*1000) if ev.fun is not None else None}
    assert ev.success and ev.fun<=result.fun+1e-3
    summary['milp_incumbent_objective_before_lp_polish']=summary['objective']
    summary['objective']=float(ev.fun*1000)
    summary['improvement_local']=1-summary['objective']/original_local_cost
    summary['max_equality_residual']=float(max(abs(eq@ev.x-eqb),default=0))
    summary['max_capacity_excess']=float(max(0,max(ub@ev.x-ubb,default=0)))
    # Export the numerically polished LP flows for the selected integer layout.
    for row in processing:
        rr=oi[row['part'],row['step']];cc=next(c for c,ss in enumerate(slots) if ss['name']==row['slot'])
        row['flow_lots']=float(ev.x[yv[rr,cc]]);row['machine_time_min']=row['flow_lots']*tau[rr]
    processing=[];transport=[];internal_export=[]
    for (r,c),v in yv.items():
        if ev.x[v]>1e-8:processing.append({'part':O[r][0],'step':int(O[r][1]),'group':ospec[r]['stnfam'],'slot':slots[c]['name'],'bay':slots[c]['bay'],'flow_lots':ev.x[v],'tau_min':tau[r],'machine_time_min':ev.x[v]*tau[r]})
    for f,direction,r,c,external,amount,dd in fv:
        if ev.x[f]>1e-8:transport.append({'part':O[r][0],'step':int(O[r][1]),'direction':direction,'slot':slots[c]['name'],'bay':slots[c]['bay'],'external_equipment':external,'flow_lots':ev.x[f],'distance_raw':dd,'weighted_distance':ev.x[f]*dd})
    for v,r,rr,c,d,dd in internal_variables:
        if ev.x[v]>1e-8:internal_export.append({'part':O[r][0],'step_from':int(O[r][1]),'step_to':int(O[rr][1]),'source_slot':slots[c]['name'],'target_slot':slots[d]['name'],'source_bay':slots[c]['bay'],'target_bay':slots[d]['bay'],'flow_lots':ev.x[v],'distance_raw':dd,'weighted_distance':ev.x[v]*dd})
    pd.DataFrame(processing).to_csv(OUT/'processing_flow.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(transport).to_csv(OUT/'boundary_flow.csv',index=False,encoding='utf-8-sig')
    pd.DataFrame(internal_export,columns=['part','step_from','step_to','source_slot','target_slot','source_bay','target_bay','flow_lots','distance_raw','weighted_distance']).to_csv(OUT/'internal_flow.csv',index=False,encoding='utf-8-sig')
summary['preparation_and_solve_seconds']=time.perf_counter()-started
pd.DataFrame([{'part':p,'step':int(s),'regional_demand_lots':q[r],'group':ospec[r]['stnfam'],'tau_per_lot_min':tau[r]} for r,(p,s) in enumerate(O)]).to_csv(OUT/'regional_operation_demands.csv',index=False,encoding='utf-8-sig')
boundary=[{'direction':d,'part':O[r][0],'step':int(O[r][1]),'external_equipment':e,'flow_lots':v} for (d,r,e),v in amounts.items()]
pd.DataFrame(boundary).to_csv(OUT/'boundary_conditions.csv',index=False,encoding='utf-8-sig')
(OUT/'summary.json').write_text(json.dumps(summary,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(summary,ensure_ascii=False,indent=2),flush=True)
