from pathlib import Path
import json,csv,collections,math
ROOT=Path(__file__).resolve().parent
data=json.loads((ROOT/'smat2022/tables.json').read_text(encoding='utf-8'))
def records(name):
    rows=data[name];return [dict(zip(rows[0],r+['']*(len(rows[0])-len(r)))) for r in rows[1:]]
eq=records('Equipment');bays=records('Bay');ports=records('Port');rails=records('Rail');nodes=records('Address');vehs=records('Vehicle')
eq_by_name={r['NAME']:r for r in eq};r_by_name={r['NAME']:r for r in rails};n_by_name={r['NAME']:r for r in nodes}
aliases={'DefMet_FE_118':'DefMEt_FE_118'}
def canonical(g):return aliases.get(g,g)
counts=collections.Counter(canonical(r['TOOL_GROUP']) for r in eq)
group_bays=collections.defaultdict(set)
for r in eq:group_bays[canonical(r['TOOL_GROUP'])].add(r['BAY'])
inventory={}
for dataset in ['SMT2020_LVHM','SMT2020_HVLM']:
    with (ROOT/(dataset+'_group_inventory.csv')).open(encoding='utf-8-sig') as f:inventory[dataset]=list(csv.DictReader(f))
lvhm={r['family']:r for r in inventory['SMT2020_LVHM'] if r['location']=='Fab'}
extra_groups={k:v for k,v in counts.items() if k not in lvhm}
mapping=[]
for g,r in sorted(lvhm.items()):
    c=counts.get(g,0)
    mapping.append({'group':g,'area':r['area'],'A2_LVHM_qty':int(float(r['machine_qty'])),'SMAT_equipment_qty':c,'difference':c-int(float(r['machine_qty'])),'SMAT_bays':'|'.join(sorted(group_bays[g])),'bay_count':len(group_bays[g])})
with (ROOT/'smat2022/A2_SMAT_group_mapping.csv').open('w',encoding='utf-8-sig',newline='') as f:
    w=csv.DictWriter(f,fieldnames=list(mapping[0]));w.writeheader();w.writerows(mapping)

adj={n:[] for n in n_by_name};rev={n:[] for n in n_by_name}
for r in rails:
    if r['FROM_NODE'] in adj and r['TO_NODE'] in adj:
        adj[r['FROM_NODE']].append(r['TO_NODE']);rev[r['TO_NODE']].append(r['FROM_NODE'])
seen=set();order=[]
def postorder(start):
    stack=[(start,False)]
    while stack:
        node,exitflag=stack.pop()
        if exitflag:order.append(node);continue
        if node in seen:continue
        seen.add(node);stack.append((node,True))
        stack.extend((v,False) for v in adj[node] if v not in seen)
for n in adj:
    if n not in seen:postorder(n)
seen=set();scc=[]
for start in reversed(order):
    if start in seen:continue
    stack=[start];size=0;seen.add(start)
    while stack:
        n=stack.pop();size+=1
        for v in rev[n]:
            if v not in seen:seen.add(v);stack.append(v)
    scc.append(size)

bad_ports=[r for r in ports if r['RAILLINE_NAME'] not in r_by_name]
nonblank_eq=[r for r in ports if r['EQP_NAME'] not in ('',',')]
unknown_eq=[r for r in nonblank_eq if r['EQP_NAME'] not in eq_by_name]
port_eq_counts=collections.Counter(r['EQP_NAME'] for r in nonblank_eq)
rail_speeds=collections.Counter(r['MAX_SPEED'] for r in rails)
length_overruns=[]
for p in ports:
    r=r_by_name.get(p['RAILLINE_NAME'])
    if r and r['CURVE']=='0':
        a=n_by_name[r['FROM_NODE']];b=n_by_name[r['TO_NODE']]
        length=math.hypot(float(a['POSITION_X'])-float(b['POSITION_X']),float(a['POSITION_Y'])-float(b['POSITION_Y']))
        if float(p['DISTANCE'])>length+1:length_overruns.append((p['NAME'],p['DISTANCE'],length))
stats={
 'workbook_sheets':list(data),'workbook_sheet_count':len(data),
 'sheet_record_counts':{k:len(v)-1 for k,v in data.items()},
 'equipment_tool_group_count':len(counts),'extra_groups_vs_A2_physical':extra_groups,
 'explicit_SMAT_to_A2_name_aliases':aliases,
 'A2_physical_groups_missing_in_SMAT':sorted(set(lvhm)-set(counts)),
 'matched_physical_group_count':sum(g in counts for g in lvhm),
 'matched_physical_equipment_qty':sum(counts[g] for g in lvhm),
 'groups_with_identical_qty':sum(r['difference']==0 for r in mapping),
 'groups_with_different_qty':sum(r['difference']!=0 for r in mapping),
 'quantity_differences_nonzero':[r for r in mapping if r['difference']],
 'physical_groups_in_multiple_bays':sum(len(group_bays[g])>1 for g in lvhm),
 'physical_group_max_bay_count':max(len(group_bays[g]) for g in lvhm),
 'bay_types':dict(collections.Counter(r['TYPE'] for r in bays)),
 'bay_reticle':dict(collections.Counter(r['RETICLE'] for r in bays)),
 'port_types':dict(collections.Counter(r['PORT_TYPE'] for r in ports)),
 'port_type_specs':records('PortType'),'vehicle_type_specs':records('VehicleType'),
 'rail_speed_values':dict(rail_speeds),'rail_curve_values':dict(collections.Counter(r['CURVE'] for r in rails)),
 'bad_rail_endpoint_count':sum(r['FROM_NODE'] not in n_by_name or r['TO_NODE'] not in n_by_name for r in rails),
 'bad_port_rail_count':len(bad_ports),'bad_port_equipment_reference_count':len(unknown_eq),
 'equipment_without_ports':[r['NAME'] for r in eq if r['NAME'] not in port_eq_counts],
 'port_equipment_refs_histogram':dict(collections.Counter(port_eq_counts.values())),
 'bad_vehicle_rail_count':sum(r['RAILLINE_NAME'] not in r_by_name for r in vehs),
 'directed_graph_scc_sizes':sorted(scc,reverse=True),
 'node_xy_range_raw':{k:[min(float(r[k]) for r in nodes),max(float(r[k]) for r in nodes)] for k in ['POSITION_X','POSITION_Y']},
 'straight_rail_port_distance_overruns_gt1_raw_unit_count':len(length_overruns),
 'straight_rail_port_distance_overrun_examples':length_overruns[:5],
 'example_group_mapping':mapping[:5],
}
(ROOT/'smat2022/cross_audit_summary.json').write_text(json.dumps(stats,ensure_ascii=False,indent=2),encoding='utf-8')
compact={k:v for k,v in stats.items() if k!='quantity_differences_nonzero' and k!='equipment_without_ports'}
compact['equipment_without_ports_count']=len(stats['equipment_without_ports'])
print(json.dumps(compact,ensure_ascii=False,indent=2))
