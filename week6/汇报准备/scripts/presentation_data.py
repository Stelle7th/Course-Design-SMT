from pathlib import Path
import csv,json,sys
ROOT=Path(__file__).resolve().parents[3];WEEK=ROOT/'week6'
sys.path.insert(0,str(WEEK/'scripts'))
import e1_reference_lp as m
import pandas as pd
folder=WEEK/'汇报准备/MILP_A2_A3'
smat={}
for p in (ROOT/'analysis/smat_layout_viz/tables/raw').glob('*.csv'):
    with p.open(encoding='utf-8-sig',newline='') as f:smat[p.stem]=list(csv.DictReader(f))
smt=m.load_smt(WEEK/'data','LVHM');eq,groups,_=m.equipment_and_ports(smat,{r['STN'] for r in smt['tools']})
graph,idx,rm,_=m.build_rail_graph(smat,'manhattan');D,_=m.build_equipment_distance_matrix(eq,rm,idx,graph)
ix={e['name']:e['index'] for e in eq}
flow=pd.read_csv(folder/'boundary_flow.csv')
examples=[]
for r in flow[flow.slot.eq('ECH0146')&flow.direction.eq('in')].itertuples():
    old=D[ix[r.external_equipment],ix['ECH0155']];new=D[ix[r.external_equipment],ix['ECH0146']]
    examples.append({'external':r.external_equipment,'part':r.part,'step':r.step,'flow':r.flow_lots,'old_distance':old,'new_distance':new,'difference':old-new})
example=max(examples,key=lambda r:r['difference'])
data={'layout':pd.read_csv(folder/'layout_result.csv').to_dict('records'),'summary':json.loads((folder/'summary.json').read_text(encoding='utf-8')),
      'relocation':pd.read_csv(folder/'equipment_relocation.csv').to_dict('records'),'example':example,
      'checks':json.loads((folder/'independent_checks.json').read_text(encoding='utf-8'))}
out=WEEK/'汇报准备/presentation_data.json';out.write_text(json.dumps(data,ensure_ascii=False,indent=2),encoding='utf-8')
print(json.dumps(data,ensure_ascii=False,separators=(',',':')))
