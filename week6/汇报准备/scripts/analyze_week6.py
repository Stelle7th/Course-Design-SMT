"""Independent CSV review and presentation figures. Does not optimize a layout."""
from pathlib import Path
import sys, json, hashlib, csv
from collections import defaultdict, Counter
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.collections import LineCollection
from matplotlib.colors import Normalize
from scipy.sparse.csgraph import dijkstra, connected_components

ROOT = Path(__file__).resolve().parents[3]
WEEK = ROOT / 'week6'
OUT = WEEK / '汇报准备'
FIG = OUT / 'figures'
TAB = OUT / 'tables'
for p in (FIG,TAB): p.mkdir(parents=True,exist_ok=True)
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as model

plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],
                     'axes.unicode_minus':False,'font.size':12,'axes.spines.top':False,
                     'axes.spines.right':False,'svg.fonttype':'none','savefig.facecolor':'white',
                     'axes.titleweight':'bold','axes.labelcolor':'#393344','text.color':'#272330'})
PURPLE, TEAL, GREY, AMBER = '#783C91','#168E93','#DCD7E2','#D88F31'
def save(fig,name):
    fig.savefig(FIG/(name+'.png'),dpi=190,bbox_inches='tight')
    fig.savefig(FIG/(name+'.svg'),bbox_inches='tight')
    plt.close(fig)
def export(df,name): df.to_csv(TAB/(name+'.csv'),index=False,encoding='utf-8-sig')
def read(name,folder='e1_reference_lp_full'): return pd.read_csv(WEEK/'output'/folder/name,encoding='utf-8-sig')
full = json.loads((WEEK/'output/e1_reference_lp_full/e1_summary.json').read_text(encoding='utf-8'))
sparse = json.loads((WEEK/'output/e1_reference_lp/e1_summary.json').read_text(encoding='utf-8'))
old = json.loads((WEEK/'output/e1_reference_lp_r01/e1_summary.json').read_text(encoding='utf-8'))
transport,operation,util,ports = [read(n) for n in ['transport_flow.csv','operation_flow.csv','device_utilization.csv','selected_equipment_ports.csv']]
rawdir = ROOT/'analysis/smat_layout_viz/tables/raw'
smat = {}
for p in rawdir.glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f: smat[p.stem] = list(csv.DictReader(f))
smt = model.load_smt(WEEK/'data','LVHM')
toolnames = {r['STN'] for r in smt['tools']}
equipment,groups,warnings = model.equipment_and_ports(smat,toolnames)
ops,demands,opwarnings = model.build_operations(smt,groups,10080,.25)
graph,nodeidx,railmeta,graphstats = model.build_rail_graph(smat,'manhattan')
distance,diststats = model.build_equipment_distance_matrix(equipment,railmeta,nodeidx,graph)
eqidx = {r['name']:r['index'] for r in equipment}
eqrows = {r['name']:r for r in equipment}
oplookup = {(o['part'],o['step']):o for o in ops}
assignment = operation.groupby(['part','step','equipment_name']).flow_lots.sum().to_dict()
outflow = transport.groupby(['part','step_from','source_equipment']).flow_lots.sum().to_dict()
inflow = transport.groupby(['part','step_to','target_equipment']).flow_lots.sum().to_dict()
laststep = {o['part']:o['step'] for o in ops}
firststep = {}
for o in ops: firststep.setdefault(o['part'],o['step'])
op_demand_resid = max(abs(operation.groupby(['part','step']).flow_lots.sum().get(k,0)-o['demand_lots']) for k,o in oplookup.items())
outresid, inresid = 0.,0.
for o in ops:
    for d in o['devices']:
        key=(o['part'],o['step'],equipment[d]['name'])
        y=assignment.get(key,0.)
        if o['step'] != laststep[o['part']]: outresid=max(outresid,abs(y-outflow.get(key,0.)))
        if o['step'] != firststep[o['part']]: inresid=max(inresid,abs(y-inflow.get(key,0.)))
recomputed_dist = np.array([distance[eqidx[r.source_equipment],eqidx[r.target_equipment]] for r in transport.itertuples()])
workcheck = operation.assign(expected_time=[oplookup[(r.part,r.step)]['tau_per_lot']*r.flow_lots for r in operation.itertuples()])
loads=workcheck.groupby('equipment_name').expected_time.sum()
maxloaderror=max(abs(loads.get(r.equipment_name,0)-r.load_min) for r in util.itertuples())
cross=transport.source_bay.ne(transport.target_bay)
totalflow=float(transport.flow_lots.sum())
totalcost=float(transport.transport_cost.sum())
group_util=util.groupby('tool_group').agg(device_count=('equipment_name','size'),load_min=('load_min','sum'),available_min=('available_time_min','sum')).reset_index()
group_util['utilization']=group_util.load_min/group_util.available_min
group_util['rho_capacity_bound']=.25/group_util.utilization
group_util=group_util.sort_values('utilization',ascending=False)
export(group_util,'group_utilization')
mapping = pd.read_csv(WEEK/'output/e0_audit/equipment_mapping.csv',encoding='utf-8-sig')
group_to_process = {r['STN']:r.get('STNGRP','') for r in smt['tools']}
mapping['process'] = mapping.mapped_smt_stn.map(group_to_process)
movable = mapping[mapping.mapped_smt_stn.notna()].copy()
slot_classes = movable.groupby(['process','width','height']).agg(device_count=('equipment_name','size'),group_count=('mapped_smt_stn','nunique'),bay_count=('bay','nunique')).reset_index()
slot_classes=slot_classes[slot_classes.group_count.ge(2)].sort_values(['group_count','device_count'],ascending=False)
export(slot_classes,'milp_equal_footprint_classes')
candidate_class=slot_classes.iloc[0]
candidate_pool=movable[(movable.process==candidate_class.process)&(movable.width==candidate_class.width)&(movable.height==candidate_class.height)]
export(candidate_pool,'milp_candidate_pool')
baymatrix=transport.pivot_table(index='source_bay',columns='target_bay',values='flow_lots',aggfunc='sum',fill_value=0.)
baynames=[f'{ab}{i}' for ab in 'AB' for i in range(1,21)]
baymatrix=baymatrix.reindex(index=baynames,columns=baynames,fill_value=0)
baymatrix.to_csv(TAB/'bay_from_to.csv',encoding='utf-8-sig')
pair=transport.groupby(['source_bay','target_bay']).agg(flow_lots=('flow_lots','sum'),transport_cost=('transport_cost','sum')).reset_index().sort_values('transport_cost',ascending=False)
pair['cost_share']=pair.transport_cost/totalcost
export(pair,'bay_pair_costs')
byproduct=transport.groupby('part').agg(flow_lots=('flow_lots','sum'),transport_cost=('transport_cost','sum')).reset_index()
export(byproduct,'product_transport')

# Reconstruct one deterministic shortest rail path per positive equipment-pair flow.
# Partial source/target edges use occupied distance; edge passage loads include them.
edgepairs=defaultdict(list)
for name,m in railmeta.items(): edgepairs[(nodeidx[m['from_node']],nodeidx[m['to_node']])].append(name)
duplicates={str(k):v for k,v in edgepairs.items() if len(v)>1}
if duplicates: raise RuntimeError('Duplicate graph arcs require a distinct-edge path rule')
nodes={r['NAME']:(float(r['POSITION_X']),float(r['POSITION_Y'])) for r in smat['Address']}
railrow={r['NAME']:r for r in smat['Rail']}
flowpairs=transport.groupby(['source_equipment','target_equipment']).agg(flow_lots=('flow_lots','sum'),transport_cost=('transport_cost','sum')).reset_index()
source_exits=sorted({nodeidx[railmeta[eqrows[r.source_equipment]['rail_name']]['to_node']] for r in flowpairs.itertuples()})
dd,pred=dijkstra(graph,directed=True,indices=source_exits,return_predecessors=True)
exitrows={n:i for i,n in enumerate(source_exits)}
edgeload=Counter(); edgedistancecost=Counter(); tracedcost=0.
for row in flowpairs.itertuples():
    s,t=eqrows[row.source_equipment],eqrows[row.target_equipment]
    si,ti=s['index'],t['index']; flow=row.flow_lots
    if distance[si,ti] == 0: continue
    if s['rail_name']==t['rail_name'] and t['port_distance_clamped']>=s['port_distance_clamped'] and np.isclose(distance[si,ti],t['port_distance_clamped']-s['port_distance_clamped']):
        segments=[(s['rail_name'],t['port_distance_clamped']-s['port_distance_clamped'])]
    else:
        sr,tr=railmeta[s['rail_name']],railmeta[t['rail_name']]
        a,b=nodeidx[sr['to_node']],nodeidx[tr['from_node']]
        segments=[(s['rail_name'],sr['length']-s['port_distance_clamped'])]
        reverse=[]; current=b; pr=pred[exitrows[a]]
        while current!=a:
            previous=int(pr[current])
            if previous<0: raise RuntimeError('Unreachable predecessor')
            name=edgepairs[(previous,current)][0]
            reverse.append((name,railmeta[name]['length'])); current=previous
        segments.extend(reversed(reverse))
        segments.append((t['rail_name'],t['port_distance_clamped']))
    route_length=sum(l for _,l in segments)
    if not np.isclose(route_length,distance[si,ti],rtol=1e-10,atol=1e-5): raise RuntimeError('Distance mismatch')
    tracedcost+=route_length*flow
    for name,length in segments:
        if length>1e-8:
            edgeload[name]+=flow
            edgedistancecost[name]+=flow*length
edge_data=[]
for name,m in railmeta.items():
    a,b=nodes[m['from_node']],nodes[m['to_node']]
    edge_data.append({'rail':name,'bay':railrow[name]['BAY_NAME'],'from_node':m['from_node'],'to_node':m['to_node'],
                      'x1':a[0],'y1':a[1],'x2':b[0],'y2':b[1],'length':m['length'],
                      'flow_lots':edgeload[name],'weighted_distance':edgedistancecost[name]})
edges=pd.DataFrame(edge_data).sort_values('flow_lots',ascending=False)
export(edges,'rail_flow_assignment')

comp,nlabels=connected_components(graph,directed=True,connection='strong')
route_rows=[r for rows in smt['routes'].values() for r in rows] if isinstance(smt.get('routes'),dict) else []
# Read raw routes directly for explicit omitted-semantics counts.
route_rows=[]
for p in (WEEK/'data/SMT2020_LVHM').glob('route_*.txt'):
    with p.open(encoding='latin1',newline='') as f: route_rows.extend(csv.DictReader(f,delimiter='\t'))
step_pcts=[float(r['StepPercent']) for r in route_rows if r.get('StepPercent')]
files_a={str(p.relative_to(WEEK)):p for p in WEEK.rglob('*') if p.is_file() and '汇报准备' not in p.parts and '__pycache__' not in p.parts and '.git' not in p.parts}
dup_root=ROOT/'新建文件夹'
same=diff=missing=0
for rel,p in files_a.items():
    q=dup_root/rel
    if not q.exists(): missing+=1
    elif hashlib.sha256(p.read_bytes()).digest()==hashlib.sha256(q.read_bytes()).digest(): same+=1
    else: diff+=1
stats={
 'basis':'e1_reference_lp_full (existing member result); independently recomputed CSV metrics',
 'objective_value':full['objective_value'],'objective_csv_sum':totalcost,
 'demand_lots':sum(demands.values()),'transport_flow_lot_transitions':totalflow,
 'weighted_mean_distance_raw':totalcost/totalflow,
 'cross_bay_flow_share':float(transport.loc[cross,'flow_lots'].sum()/totalflow),
 'cross_bay_distance_cost_share':float(transport.loc[cross,'transport_cost'].sum()/totalcost),
 'same_bay_flow_share':float(transport.loc[~cross,'flow_lots'].sum()/totalflow),
 'zero_distance_flow_share':float(transport.loc[transport.path_distance.eq(0),'flow_lots'].sum()/totalflow),
 'production_operation_count':len(ops),'removed_delay_records':len(route_rows)-len(ops),
 'step_percent_nonempty':len(step_pcts),'step_percent_below_100':sum(p<100 for p in step_pcts),
 'device_count':len(util),'active_device_count':int(util.load_min.gt(1e-7).sum()),
 'at_effective_capacity_device_count':int(np.isclose(util.utilization,1,atol=1e-7).sum()),
 'mean_device_utilization_effective':float(util.utilization.mean()),
 'bottleneck_group':str(group_util.iloc[0].tool_group),
 'bottleneck_group_utilization':float(group_util.iloc[0].utilization),
 'rho_capacity_bound_current_model':float(group_util.rho_capacity_bound.min()),
 'top5_bay_pairs_cost_share':float(pair.head(5).cost_share.sum()),
 'top10_bay_pairs_cost_share':float(pair.head(10).cost_share.sum()),
 'strong_component_count':int(comp),'ports_clamped_count':sum(abs(e['port_distance']-e['port_distance_clamped'])>1e-6 for e in equipment),
 'sparse_full_objective_relative_difference':abs(sparse['objective_value']-full['objective_value'])/full['objective_value'],
 'sparse_variable_reduction':1-sparse['model']['variable_count']/full['model']['variable_count'],
 'sparse_arc_reduction':1-sparse['model']['transport_arc_count']/full['model']['transport_arc_count'],
 'max_demand_residual':float(op_demand_resid),'max_outgoing_flow_residual':float(outresid),'max_incoming_flow_residual':float(inresid),
 'max_distance_recompute_residual':float(np.max(np.abs(recomputed_dist-transport.path_distance.to_numpy()))),
 'max_load_recompute_residual_min':float(maxloaderror),
 'max_tau_export_error_min':float(np.max(np.abs(workcheck.expected_time-workcheck.machine_time_min))),
 'capacity_excess_min':float(max(0,util.load_min.sub(util.available_time_min).max())),
 'rail_path_objective_recomputed':tracedcost,'rail_path_objective_relative_error':abs(tracedcost-totalcost)/totalcost,
 'rail_max_edge_flow_lots':float(edges.flow_lots.max()),'rail_used_count':int(edges.flow_lots.gt(1e-8).sum()),
 'archived_r01':{'status':old['solver_status'],'transport_arc_count':old['model']['transport_arc_count'],'equality_count':old['model']['equality_count']},
 'duplicate_folder':{'same_files':same,'different_files':diff,'missing_files':missing},
 'caveats':['All distance units remain original coordinate units. Divide by 1000 only under an explicit mm assumption.',
            'Rail assignment uses one shortest path among ties, with no capacity/traffic/empty OHT model.',
            'Full and sparse optimal flows can differ despite matching objective values.',
            'No new LP or layout optimization was run by this review script.']}
(OUT/'analysis_metrics.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')

# 01: directed Bay From-To. Natural physical ordering, diagonal retained.
fig,ax=plt.subplots(figsize=(13.6,9))
im=ax.imshow(np.log1p(baymatrix.values),cmap='Purples',interpolation='nearest')
ax.set_xticks(range(40),baynames,rotation=90,fontsize=8)
ax.set_yticks(range(40),baynames,fontsize=8)
ax.set_xlabel('目标 Bay');ax.set_ylabel('源 Bay')
ax.axvline(19.5,color=TEAL,lw=1);ax.axhline(19.5,color=TEAL,lw=1)
fig.suptitle('参考布局中的 Bay 间物流',x=.13,ha='left',fontsize=23,fontweight='bold')
ax.set_title(f'跨 Bay 流量占 {stats["cross_bay_flow_share"]:.1%}，跨 Bay 加权距离占 {stats["cross_bay_distance_cost_share"]:.1%}',loc='left',fontsize=12,pad=17)
cb=fig.colorbar(im,ax=ax,pad=.025,shrink=.8);cb.set_label('ln(1 + 流量 / lot 转移)')
fig.text(.13,.015,'来源：现有全弧 E1 结果；ρ=0.25，η=0.85，T=10080 min。颜色使用对数以显示弱流量。',fontsize=10,color='#6A6270')
fig.subplots_adjust(top=.86,bottom=.15,left=.10,right=.91)
save(fig,'01_bay_from_to')

# 02: show group-level capacity rather than interpreting one saturated device as a system bottleneck.
top=group_util.head(15).iloc[::-1]
fig,ax=plt.subplots(figsize=(13.6,8))
ax.barh(top.tool_group,top.utilization*100,color=[TEAL if v==stats['bottleneck_group'] else PURPLE for v in top.tool_group],height=.65)
for i,r in enumerate(top.itertuples()): ax.text(r.utilization*100+.8,i,f'{r.utilization:.1%}  / {r.device_count} 台',va='center',fontsize=11)
ax.set_xlim(0,115);ax.set_xlabel('设备组总加工机时 / 设备组有效机时 (%)')
ax.xaxis.grid(True,alpha=.15);ax.set_axisbelow(True)
fig.suptitle('设备组的产能利用率',x=.28,ha='left',fontsize=23,fontweight='bold')
fig.text(.28,.90,'按组汇总的前 15 位；逐台满载与整组产能瓶颈需要分别判断。',fontsize=12,color='#6A6270')
fig.text(.28,.025,f'当前线性化生产模型的必要产能上界：ρ ≤ {stats["rho_capacity_bound_current_model"]:.4f}。该值不包含随机故障与排队。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.28,right=.95,top=.82,bottom=.14)
save(fig,'02_group_capacity')

# 03: plot static rail load along actual directed graph geometry.
fig,ax=plt.subplots(figsize=(15.5,8.3))
segments=np.array([[[r.x1/1000,r.y1/1000],[r.x2/1000,r.y2/1000]] for r in edges.itertuples()])
ax.add_collection(LineCollection(segments,colors='#E4DFE8',linewidths=.65,zorder=0))
loaded=edges.flow_lots.to_numpy()>0
norm=Normalize(0,float(np.log1p(edges.flow_lots.max())))
lc=LineCollection(segments[loaded],cmap='magma_r',norm=norm,linewidths=1.1+2*np.sqrt(edges.loc[loaded,'flow_lots'].to_numpy()/edges.flow_lots.max()),zorder=2)
lc.set_array(np.log1p(edges.loc[loaded,'flow_lots'].to_numpy()));ax.add_collection(lc)
ax.autoscale();ax.set_aspect('equal');ax.set_xlabel('X / 1000 原始坐标单位');ax.set_ylabel('Y / 1000 原始坐标单位')
for ab,y in [('A',146),('B',-5)]:
    for i in range(1,21): ax.text(7.5+(i-1)*13.35,y,f'{ab}{i}',fontsize=7,ha='center',color='#6A6270')
fig.suptitle('沿有向轨道回溯的静态物流负载',x=.09,ha='left',fontsize=23,fontweight='bold')
fig.text(.09,.90,'将 LP 的设备间运输量分配到一条最短轨道路径；并列最短路径按固定规则选一条。',fontsize=12,color='#6A6270')
cb=fig.colorbar(lc,ax=ax,pad=.015,shrink=.65);cb.set_label('ln(1 + 边经过量 / lot)')
fig.text(.09,.035,'轨道几何以节点连线表示；曲线长度仍沿用原 E1 的曼哈顿近似。该图反映静态负载，不表示拥堵或车辆运行结果。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.08,right=.94,top=.84,bottom=.14)
save(fig,'03_rail_flow_map')

# 04: separate same-layout model-size reduction from layout-performance improvement.
fig,(a,b)=plt.subplots(1,2,figsize=(13.6,7.4),gridspec_kw={'width_ratios':[1,1]})
labels=['完整运输弧','双向补弧 Top-12']
models=[full,sparse]
a.bar(labels,[r['model']['variable_count']/1e6 for r in models],color=[GREY,PURPLE],width=.5)
for i,r in enumerate(models): a.text(i,r['model']['variable_count']/1e6+.04,f'{r["model"]["variable_count"]:,}',ha='center',fontsize=13)
a.set_ylabel('LP 变量数 / 百万');a.set_ylim(0,2.5)
a.set_title(f'变量减少 {stats["sparse_variable_reduction"]:.1%}',loc='left',fontsize=17)
b.bar(labels,[r['objective_value']/1e9 for r in models],color=[GREY,PURPLE],width=.5)
for i,r in enumerate(models): b.text(i,r['objective_value']/1e9+.10,f'{r["objective_value"]/1e9:.6f}',ha='center',fontsize=13)
b.set_ylim(0,7);b.set_ylabel('总加权距离 / 10^9 原始距离单位·lot')
b.set_title('本实例目标值在数值精度内一致',loc='left',fontsize=17)
fig.suptitle('参考布局 LP 的规模对照',x=.08,ha='left',fontsize=23,fontweight='bold')
fig.text(.08,.89,'相同参考布局与生产参数，仅运输弧集合不同。',fontsize=12,color='#6A6270')
fig.text(.08,.035,'该对照验证了本实例的稀疏化效果。尚无求解计时记录，也不代表新布局优于参考布局。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.08,right=.96,top=.78,bottom=.15,wspace=.32)
save(fig,'04_sparse_full_comparison')

# 05: Pareto identifies where distance cost accumulates.
top=pair.head(12).copy();top['label']=top.source_bay+' → '+top.target_bay
fig,ax=plt.subplots(figsize=(13.6,7.8))
xx=np.arange(len(top));ax.bar(xx,top.cost_share*100,color=PURPLE,width=.62)
ax.set_xticks(xx,top.label,rotation=35,ha='right',fontsize=11)
ax.set_ylabel('占全厂加权距离 (%)');ax.set_ylim(0,max(top.cost_share)*125)
for i,r in enumerate(top.itertuples()):ax.text(i,r.cost_share*100+.25,f'{r.cost_share:.1%}',ha='center',fontsize=10)
fig.suptitle('距离成本集中的 Bay 运输对',x=.09,ha='left',fontsize=23,fontweight='bold')
fig.text(.09,.89,f'前 5 对占总加权距离 {stats["top5_bay_pairs_cost_share"]:.1%}，前 10 对占 {stats["top10_bay_pairs_cost_share"]:.1%}。',fontsize=12,color='#6A6270')
fig.text(.09,.025,'按流量 × 轨道距离排序；优先检查这些连接的工艺关系与替代设备位置。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.09,right=.96,top=.81,bottom=.24)
save(fig,'05_bay_cost_concentration')

# 06: independent analytical capacity envelope, not an LP sensitivity experiment.
rh=np.linspace(.1,.5,100); topg=group_util.head(3)
fig,ax=plt.subplots(figsize=(13.6,7.4))
for r,c in zip(topg.itertuples(),[PURPLE,TEAL,AMBER]):
    yy=r.utilization*rh/.25*100
    ax.plot(rh,yy,lw=2.4,color=c,label=r.tool_group)
ax.axhline(100,lw=1,ls='--',color='#7F7784');ax.axvline(.25,lw=1,ls=':',color='#7F7784')
ax.text(.254,8,'当前基准 ρ=0.25',fontsize=11)
ax.text(.49,103,'有效产能上限',ha='right',fontsize=11)
ax.set_xlim(.1,.5);ax.set_ylim(0,180);ax.set_xlabel('需求缩放系数 ρ');ax.set_ylabel('组总需求机时 / 组总有效机时 (%)')
ax.legend(loc='upper left',frameon=False)
fig.suptitle('当前加工近似下的产能边界',x=.09,ha='left',fontsize=23,fontweight='bold')
fig.text(.09,.89,'根据工序加工机时与设备数量直接计算；此图未重新求解 LP。',fontsize=12,color='#6A6270')
fig.text(.09,.025,'总产能约束提供必要边界。抽检、返工、批处理和级联加工语义改变后，需要重新计算。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.09,right=.96,top=.81,bottom=.16)
save(fig,'06_capacity_envelope')
print(json.dumps(stats,ensure_ascii=False,indent=2))
