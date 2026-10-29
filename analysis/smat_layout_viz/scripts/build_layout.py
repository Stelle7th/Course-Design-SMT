"""Rebuild the SMAT2022 spatial baseline. Never edits source inputs.

Run from any directory: python analysis/smat_layout_viz/scripts/build_layout.py
Only standard Python plus numpy/pandas/matplotlib/networkx/scipy are required.
The previously audited OOXML reader is reused to read the original workbook.
"""
from pathlib import Path
import sys, json, hashlib, math, platform, importlib.metadata, shutil
from collections import Counter, defaultdict
import numpy as np
import pandas as pd
import networkx as nx
from scipy.spatial.distance import pdist, cdist
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle, Patch
from matplotlib.collections import PatchCollection, LineCollection
from matplotlib.lines import Line2D

ROOT = Path(__file__).resolve().parents[3]
OUT = ROOT/'analysis/smat_layout_viz'
SRC = ROOT/'analysis/a2_audit/smat2022'
OLD = Path('C:/Users/HP/.codex/.chatgpt-projects/g-p-6aae3af666cc8191ae33dfecc4757614/analysis/a2_audit')
sys.path.insert(0,str(ROOT/'analysis/a2_audit'))
from audit_smat import workbook_rows
for folder in ('figures/selected_workcenters','tables/raw','interactive','validation'):
    (OUT/folder).mkdir(parents=True,exist_ok=True)

plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','DejaVu Sans'], 'axes.unicode_minus':False,
                     'svg.fonttype':'none','font.size':10,'axes.spines.top':False,'axes.spines.right':False})
SCALE=1000.0
NOTE='坐标刻度 ×1000 原始单位；X/Y 等比例；设备矩形暂按坐标为中心绘制（锚点未获文档确认）'
CURVE_NOTE='虚线 = CURVE=1 的端点连接示意，非真实曲线；箭头仅示方向，不代表流量'
COLORS=['#0072B2','#E69F00','#009E73','#CC79A7','#D55E00','#6A51A3','#56B4E9','#8C6D31','#BCBD22','#E377C2','#3B5B60']
FAC={'STOCKER':'#444444','COMMIT':'#008575','COMPLETE':'#C5353E'}
CHECKS=[]
def check(name, actual, expected):
    ok=bool(actual==expected)
    CHECKS.append({'check':name,'actual':actual,'expected':expected,'passed':ok})
    if not ok: raise AssertionError(f'{name}: {actual!r} != {expected!r}')
def csv(df,name,index=False):df.to_csv(OUT/'tables'/name,index=index,encoding='utf-8-sig')
def digest(p):return hashlib.sha256(p.read_bytes()).hexdigest()
def natural(s):
    import re
    return [int(x) if x.isdigit() else x for x in re.split(r'(\d+)',s)]
def md(df):
    # No optional tabulate dependency needed.
    def f(v):return str(round(v,4)) if isinstance(v,float) else str(v)
    return '| '+' | '.join(map(str,df.columns))+' |\n| '+' | '.join(['---']*len(df.columns))+' |\n'+'\n'.join('| '+' | '.join(f(v) for v in row)+' |' for row in df.itertuples(index=False,name=None))

def load():
    workbook=SRC/'SMAT_2022_Model_Data_-_LVHM_E.xlsx'
    raw=workbook_rows(workbook)
    tables={k:pd.DataFrame([r+['']*(len(v[0])-len(r)) for r in v[1:]],columns=v[0]) for k,v in raw.items()}
    expected={'Address':2858,'ZCU':734,'Rail':3424,'Bay':43,'Equipment':1116,'PortType':6,'Port':22120,'VehicleType':1,'Vehicle':500}
    check('sheet names',sorted(tables),sorted(expected))
    for name,d in tables.items():
        check(name+' rows',len(d),expected[name]); check(name+' duplicate NAME',int(d.NAME.duplicated().sum()),0)
        for col in ('POSITION_X','POSITION_Y','WIDTH','HEIGHT','DISTANCE','CURVE'):
            if col in d:d[col]=pd.to_numeric(d[col],errors='raise')
        csv(d,'raw/'+name+'.csv')
    manifest=json.loads((SRC/'download_manifest.json').read_text(encoding='utf-8'))
    source_manifest=[]
    for item in manifest:
        p=SRC/item['local_file']; check('source hash '+p.name,digest(p),item['sha256'])
    for p in [workbook,SRC/'A2_SMAT_group_mapping.csv',ROOT/'analysis/a2_audit/核查结论与实施方案.md',ROOT/'analysis/a2_audit/SMT2020_LVHM_group_inventory.csv',SRC/'SMAT_2022_generic.txt',SRC/'SMAT_2022_PINOKIO_documentation.txt']:
        old=OLD/p.relative_to(ROOT/'analysis/a2_audit')
        if old.exists():check('copy equality '+p.name,digest(p),digest(old))
        source_manifest.append({'source':str(old),'local_path':str(p),'sha256':digest(p),'bytes':p.stat().st_size})
    (OUT/'validation/source_manifest.json').write_text(json.dumps(source_manifest,ensure_ascii=False,indent=2),encoding='utf-8')
    return tables

def prepare(t):
    e=t['Equipment'].copy(); a=t['Address'].copy(); r=t['Rail'].copy(); b=t['Bay'].copy(); p=t['Port'].copy(); v=t['Vehicle'].copy()
    mapping=pd.read_csv(SRC/'A2_SMAT_group_mapping.csv',keep_default_na=False)
    check('mapping unique groups',mapping.group.nunique(),105)
    check('mapping duplicate groups',int(mapping.group.duplicated().sum()),0)
    check('mapping process classes',mapping.area.nunique(),11)
    e['STNFAM']=e.TOOL_GROUP.replace({'DefMet_FE_118':'DefMEt_FE_118'})
    e['kind']=np.where(e.TOOL_GROUP.isin(FAC),e.TOOL_GROUP,'PRODUCTION')
    e=e.merge(mapping[['group','area']],left_on='STNFAM',right_on='group',how='left',validate='many_to_one').drop(columns='group')
    e['area']=e.area.fillna('UNMAPPED')
    for k,n in {'PRODUCTION':1068,'STOCKER':40,'COMMIT':4,'COMPLETE':4}.items():check('equipment '+k,int((e.kind==k).sum()),n)
    csv(e[(e.kind=='PRODUCTION')&(e.area=='UNMAPPED')],'unmapped_equipment.csv')
    check('unmapped production',int(((e.kind=='PRODUCTION')&(e.area=='UNMAPPED')).sum()),0)
    check('equipment Bay FK',int((~e.BAY.isin(b.NAME)).sum()),0)
    check('positive dimensions',int(((e.WIDTH<=0)|(e.HEIGHT<=0)).sum()),0)
    check('finite equipment geometry',bool(np.isfinite(e[['WIDTH','HEIGHT','POSITION_X','POSITION_Y']].to_numpy()).all()),True)
    check('finite Address geometry',bool(np.isfinite(a[['POSITION_X','POSITION_Y']].to_numpy()).all()),True)
    check('Bay type counts',b.TYPE.value_counts().to_dict(),{'INTRABAY':40,'INTERBAY':3})
    check('Rail Bay FK',int((~r.BAY_NAME.isin(b.NAME)).sum()),0)
    for col in ('FROM_NODE','TO_NODE'):check('Rail '+col+' FK',int((~r[col].isin(a.NAME)).sum()),0)
    xy=a.set_index('NAME')[['POSITION_X','POSITION_Y']]
    for col,endpoint in [('FROM_NODE','0'),('TO_NODE','1')]:
        r['x'+endpoint]=r[col].map(xy.POSITION_X); r['y'+endpoint]=r[col].map(xy.POSITION_Y)
    r['endpoint_chord_raw']=np.hypot(r.x1-r.x0,r.y1-r.y0)
    r['straight_length_raw']=r.endpoint_chord_raw.where(r.CURVE==0)
    check('zero length straight rails',int(((r.CURVE==0)&(r.straight_length_raw<=0)).sum()),0)
    check('binary CURVE',sorted(r.CURVE.unique().tolist()),[0,1])
    for df,label in [(p,'Port'),(v,'Vehicle')]:
        check(label+' Rail FK',int((~df.RAILLINE_NAME.isin(r.NAME)).sum()),0)
        for c in ('x0','y0','x1','y1','CURVE','BAY_NAME','endpoint_chord_raw'):df[c]=df.RAILLINE_NAME.map(r.set_index('NAME')[c])
        df['straight_overrun_raw']=np.where(df.CURVE==0,df.DISTANCE-df.endpoint_chord_raw,np.nan)
        check(label+' negative DISTANCE',int((df.DISTANCE<0).sum()),0)
        check(label+' straight overrun >1',int((df.straight_overrun_raw>1).sum()),0)
        # No interpolation or fabricated arc geometry for CURVE=1.
        q=df.DISTANCE/df.endpoint_chord_raw
        df['derived_x']=(df.x0+(df.x1-df.x0)*q).where(df.CURVE==0)
        df['derived_y']=(df.y0+(df.y1-df.y0)*q).where(df.CURVE==0)
        df['position_method']=np.where(df.CURVE==0,'straight_FROM_plus_DISTANCE','unavailable_curve_geometry')
    p['has_equipment']=~p.EQP_NAME.isin(['',','])
    check('Port equipment FK',int((p.has_equipment&~p.EQP_NAME.isin(e.NAME)).sum()),0)
    check('Port type FK',int((~p.PORT_TYPE.isin(t['PortType'].NAME)).sum()),0)
    check('Vehicle type FK',int((~v.TYPE.isin(t['VehicleType'].NAME)).sum()),0)
    check('Address ZCU FK',int((~a.ZCU_NAME.isin(t['ZCU'].NAME)&~a.ZCU_NAME.isin(['',','])).sum()),0)
    e['port_count']=e.NAME.map(p[p.has_equipment].EQP_NAME.value_counts()).fillna(0).astype(int)
    for k,count in [('PRODUCTION',4),('STOCKER',2),('COMMIT',1),('COMPLETE',1)]:check(k+' port count',sorted(e[e.kind==k].port_count.unique().tolist()),[count])
    prod=e[e.kind=='PRODUCTION']
    bays=sorted(b.NAME,key=natural)
    matrix=pd.crosstab(prod.STNFAM,prod.BAY).reindex(index=sorted(mapping.group),columns=bays,fill_value=0)
    check('matrix total',int(matrix.to_numpy().sum()),1068)
    check('workcenter Bay pairs',int((matrix>0).to_numpy().sum()),142)
    check('multi Bay groups',int(((matrix>0).sum(axis=1)>1).sum()),32)
    check('maximum Bay count',int((matrix>0).sum(axis=1).max()),6)
    current=matrix.sum(axis=1).reindex(mapping.group).to_numpy()
    check('mapping equipment quantities',current.tolist(),mapping.SMAT_equipment_qty.tolist())
    for row in mapping.itertuples():
        check('mapping Bay set '+row.group,sorted(matrix.columns[matrix.loc[row.group]>0]),sorted(row.SMAT_bays.split('|')))
    csv(matrix,'workcenter_bay_matrix.csv',True)
    wc=[]
    for g,d in prod.groupby('STNFAM'):
        xy2=d[['POSITION_X','POSITION_Y']].to_numpy()
        gs=sorted(d.BAY.unique(),key=natural)
        wc.append({'STNFAM':g,'area':d.area.iloc[0],'equipment_count':len(d),'bay_count':len(gs),'bays':'|'.join(gs),
                   'max_anchor_distance_raw':float(pdist(xy2).max()) if len(d)>1 else 0.,
                   'x_span_raw':float(np.ptp(xy2[:,0])),'y_span_raw':float(np.ptp(xy2[:,1])),
                   'both_A_B_rows':any(x.startswith('A') for x in gs) and any(x.startswith('B') for x in gs)})
    wc=pd.DataFrame(wc).sort_values(['bay_count','max_anchor_distance_raw'],ascending=False)
    csv(wc,'workcenter_distribution_summary.csv')
    csv(prod.groupby(['STNFAM','area','BAY']).size().reset_index(name='equipment_count'),'workcenter_bay_detail.csv')
    summary=[]
    anchors={}
    for bay in bays:
        d=e[e.BAY==bay]; pr=d[d.kind=='PRODUCTION']; rr=r[r.BAY_NAME==bay]
        xs=np.r_[rr.x0,rr.x1]; ys=np.r_[rr.y0,rr.y1]
        anchors[bay]=(float(np.median(xs))/SCALE,float(np.median(ys))/SCALE)
        xmin=(pr.POSITION_X-pr.WIDTH/2).min(); xmax=(pr.POSITION_X+pr.WIDTH/2).max()
        ymin=(pr.POSITION_Y-pr.HEIGHT/2).min(); ymax=(pr.POSITION_Y+pr.HEIGHT/2).max()
        envelope=(xmax-xmin)*(ymax-ymin)
        summary.append({'Bay':bay,'type':b.set_index('NAME').loc[bay,'TYPE'],'reticle':int(b.set_index('NAME').loc[bay,'RETICLE']),
                        'production_count':len(pr),'workcenter_count':pr.STNFAM.nunique(),'stocker_count':int((d.kind=='STOCKER').sum()),
                        'commit_count':int((d.kind=='COMMIT').sum()),'complete_count':int((d.kind=='COMPLETE').sum()),'rail_count':len(rr),
                        'equipment_envelope_area_raw2':envelope,'equipment_rect_area_sum_raw2':float((pr.WIDTH*pr.HEIGHT).sum()),
                        'count_per_1e8_envelope_raw2':len(pr)*1e8/envelope if envelope>0 else np.nan,
                        'rail_endpoint_xmin':float(xs.min()),'rail_endpoint_xmax':float(xs.max()),'rail_endpoint_ymin':float(ys.min()),'rail_endpoint_ymax':float(ys.max())})
    bs=pd.DataFrame(summary); csv(bs,'bay_equipment_summary.csv')
    check('Bay production totals',int(bs.production_count.sum()),1068)
    check('one STOCKER per INTRABAY',bs[bs.type=='INTRABAY'].stocker_count.tolist(),[1]*40)
    check('no production in INTERBAY',int(bs[bs.type=='INTERBAY'].production_count.sum()),0)
    check('group production totals',int(wc.equipment_count.sum()),1068)
    # Coordinate-anchor diagnostics do not certify CAD interpretation.
    geom=[]
    for convention in ('center','lower_left'):
        x=e.POSITION_X.to_numpy()-(e.WIDTH.to_numpy()/2 if convention=='center' else 0)
        y=e.POSITION_Y.to_numpy()-(e.HEIGHT.to_numpy()/2 if convention=='center' else 0)
        w=e.WIDTH.to_numpy(); h=e.HEIGHT.to_numpy()
        overlap=(np.minimum((x+w)[:,None],(x+w)[None,:])-np.maximum(x[:,None],x[None,:])>1e-6)&(np.minimum((y+h)[:,None],(y+h)[None,:])-np.maximum(y[:,None],y[None,:])>1e-6)
        pairs=np.argwhere(np.triu(overlap,1))
        geom.append({'convention':convention,'overlapping_rectangle_pairs':len(pairs)})
        csv(pd.DataFrame([{'equipment_1':e.iloc[i].NAME,'equipment_2':e.iloc[j].NAME} for i,j in pairs],columns=['equipment_1','equipment_2']),f'geometry_overlap_{convention}.csv')
    csv(pd.DataFrame(geom),'coordinate_anchor_diagnostics.csv')
    stock=e[e.kind=='STOCKER']; distances=cdist(prod[['POSITION_X','POSITION_Y']],stock[['POSITION_X','POSITION_Y']])
    near=distances.argmin(axis=1)
    near_df=pd.DataFrame({'equipment':prod.NAME.to_numpy(),'Bay':prod.BAY.to_numpy(),'nearest_stocker':stock.NAME.to_numpy()[near],
                          'nearest_stocker_Bay':stock.BAY.to_numpy()[near],'anchor_distance_raw':distances.min(axis=1)})
    csv(near_df,'equipment_nearest_stocker.csv')
    e['rectangle_anchor_assumption']='center_unconfirmed'; csv(e,'equipment_position_summary.csv')
    csv(r,'rail_geometry.csv'); csv(p,'port_position_detail.csv'); csv(v,'vehicle_initial_positions.csv')
    csv(pd.DataFrame({'area':sorted(prod.area.unique()),'color':COLORS}),'process_colors.csv')
    return e,a,r,b,p,v,matrix,wc,bs,anchors,near_df

def network(a,r,b):
    G=nx.DiGraph();G.add_nodes_from(a.NAME);G.add_edges_from(zip(r.FROM_NODE,r.TO_NODE))
    sizes=sorted(map(len,nx.strongly_connected_components(G)),reverse=True)
    check('strong components',sizes,[2858])
    # Directed line-graph transitions at exact shared Address IDs.
    inc=defaultdict(list);out=defaultdict(list)
    for row in r.itertuples():inc[row.TO_NODE].append(row);out[row.FROM_NODE].append(row)
    witnesses=[]
    for node in inc:
        for x in inc[node]:
            for y in out[node]:
                if x.BAY_NAME!=y.BAY_NAME:witnesses.append({'from_bay':x.BAY_NAME,'to_bay':y.BAY_NAME,'shared_node':node,'incoming_rail':x.NAME,'outgoing_rail':y.NAME})
    w=pd.DataFrame(witnesses);csv(w,'bay_transition_witnesses.csv')
    edges=w.groupby(['from_bay','to_bay']).agg(transition_count=('shared_node','size'),unique_shared_nodes=('shared_node','nunique')).reset_index()
    csv(edges,'bay_directed_connections.csv')
    outgoing=edges.groupby('from_bay').agg(out_neighbor_bays=('to_bay','nunique'),out_transitions=('transition_count','sum'))
    incoming=edges.groupby('to_bay').agg(in_neighbor_bays=('from_bay','nunique'),in_transitions=('transition_count','sum'))
    connections=outgoing.join(incoming).rename_axis('Bay')
    connections['total_transitions']=connections.out_transitions+connections.in_transitions
    csv(connections.sort_values('total_transitions',ascending=False),'bay_connection_summary.csv',True)
    BG=nx.DiGraph();BG.add_nodes_from(b.NAME);BG.add_edges_from(zip(edges.from_bay,edges.to_bay))
    names=sorted(b.NAME,key=natural)
    reach=pd.DataFrame(0,index=names,columns=names)
    for name in names:reach.loc[name,list(nx.descendants(BG,name)|{name})]=1
    check('Bay directed reachable ordered pairs excluding self',int(reach.to_numpy().sum()-len(names)),43*42)
    csv(reach,'bay_reachability_matrix.csv',True)
    declared=[]
    for row in b.itertuples():
        for target in row.NEIGHBOR_BAY.split(','):
            if target:declared.append({'from_bay':row.NAME,'to_bay':target,'direct_rail_transition':BG.has_edge(row.NAME,target)})
    csv(pd.DataFrame(declared),'declared_neighbor_comparison.csv')
    print('Computing sampled directed topology betweenness (k=128, seed=2022)...',flush=True)
    bc=nx.betweenness_centrality(G,k=128,normalized=True,seed=2022)
    metrics=a.copy();metrics['in_degree']=metrics.NAME.map(dict(G.in_degree()));metrics['out_degree']=metrics.NAME.map(dict(G.out_degree()));metrics['betweenness_sampled_k128']=metrics.NAME.map(bc)
    csv(metrics.sort_values('betweenness_sampled_k128',ascending=False),'network_node_topology.csv')
    return G,BG,edges,metrics,sizes

def setup(title,subtitle=NOTE):
    fig,ax=plt.subplots(figsize=(19,10.8));fig.subplots_adjust(left=.055,right=.985,bottom=.13,top=.90)
    fig.suptitle(title,fontsize=19,fontweight='bold',y=.975)
    fig.text(.055,.925,subtitle,fontsize=10,color='#46566A')
    ax.set_aspect('equal',adjustable='box');ax.set_xlabel('X / 1000 原始单位');ax.set_ylabel('Y / 1000 原始单位')
    ax.tick_params(labelsize=9);ax.grid(alpha=.13,zorder=0);ax.set_axisbelow(True)
    ax.set_xlim(-4,305);ax.set_ylim(-10,152)
    return fig,ax
def save(fig,name):
    fig.savefig(OUT/'figures'/f'{name}.png',dpi=300,facecolor='white')
    fig.savefig(OUT/'figures'/f'{name}.svg',facecolor='white')
    plt.close(fig); print('Saved',name,flush=True)
def rects(ax,e,colors=None,alpha=.9,zorder=3):
    patches=[Rectangle(((d.POSITION_X-d.WIDTH/2)/SCALE,(d.POSITION_Y-d.HEIGHT/2)/SCALE),d.WIDTH/SCALE,d.HEIGHT/SCALE) for d in e.itertuples()]
    if colors is None:colors=[FAC.get(k,'#648AB2') for k in e.kind]
    ax.add_collection(PatchCollection(patches,facecolors=colors,edgecolors='white',linewidths=.12,alpha=alpha,zorder=zorder))
def rails(ax,r,alpha=.5,lw=.45,arrows=False,color=None):
    for curve in (0,1):
        d=r[r.CURVE==curve]
        segments=np.stack([d[['x0','y0']].to_numpy(),d[['x1','y1']].to_numpy()],axis=1)/SCALE
        cols=color or ('#566A81' if curve==0 else '#D09A45')
        ax.add_collection(LineCollection(segments,colors=cols,linewidths=lw,alpha=alpha,linestyles='solid' if curve==0 else (0,(3,2)),zorder=2))
    if arrows:
        # Every fifth rail for a legible overview; full directions remain in data/viewer.
        d=r.iloc[::5];dx=(d.x1-d.x0)/SCALE;dy=(d.y1-d.y0)/SCALE;norm=np.hypot(dx,dy)
        ax.quiver((d.x0*.45+d.x1*.55)/SCALE,(d.y0*.45+d.y1*.55)/SCALE,dx/norm,dy/norm,angles='xy',scale_units='xy',scale=.7,width=.001,headwidth=3.5,color='#253C53',alpha=.8,zorder=5)
def baylabels(ax,r,b):
    for d in b.itertuples():
        rr=r[r.BAY_NAME==d.NAME];x=float(np.median(np.r_[rr.x0,rr.x1]))/SCALE
        if d.TYPE=='INTRABAY':
            y=141.5 if d.NAME.startswith('A') else -1.3
            ax.text(x,y,d.NAME,ha='center',va='center',fontsize=8,fontweight='bold',bbox={'facecolor':'white','alpha':.8,'edgecolor':'none','pad':1.2},zorder=8)
        else:
            y=float(np.median(np.r_[rr.y0,rr.y1]))/SCALE
            ax.text(153,y,d.NAME,ha='center',va='center',fontsize=8,color='#8F6325',bbox={'facecolor':'white','alpha':.9,'edgecolor':'none','pad':1},zorder=8)
def baselegend():return [Patch(facecolor='#648AB2',label='生产设备 1068'),*[Patch(facecolor=c,label=f'{k} {n}') for (k,c),n in zip(FAC.items(),[40,4,4])]]
def raillegend():return [Line2D([0],[0],color='#566A81',lw=1,label='直线 Rail 2473'),Line2D([0],[0],color='#D09A45',ls='--',lw=1,label='曲线连接示意 951')]

def figures(e,a,r,b,matrix,wc,bs,metrics,BG,edges,anchors):
    prod=e[e.kind=='PRODUCTION'];areas=sorted(prod.area.unique());palette=dict(zip(areas,COLORS))
    for name,title,showe,showr in [('01_equipment_layout','SMAT2022 · 完整设备布局',True,False),('02_rail_network','SMAT2022 · 有向轨道网络',False,True),('03_equipment_rail_overlay','SMAT2022 · 设备与轨道叠加',True,True)]:
        fig,ax=setup(title)
        if showr:rails(ax,r,alpha=.85 if not showe else .42,lw=.65 if not showe else .45,arrows=True)
        if showe:rects(ax,e)
        baylabels(ax,r,b);fig.legend(handles=(baselegend() if showe else [])+(raillegend() if showr else []),loc='lower center',ncol=6,bbox_to_anchor=(.51,.035),frameon=False)
        if showr:fig.text(.055,.013,CURVE_NOTE,fontsize=9,color='#75521E')
        save(fig,name)
    fig,ax=setup('SMAT2022 · 11 类工艺功能的设备空间分布')
    rails(ax,r,alpha=.18,lw=.32)
    rects(ax,e,[palette.get(row.area,FAC.get(row.kind,'#999999')) for row in e.itertuples()]);baylabels(ax,r,b)
    counts=prod.area.value_counts();handles=[Patch(facecolor=palette[k],label=f'{k} ({counts[k]})') for k in areas]+[Patch(facecolor=FAC[k],label=k) for k in FAC]
    fig.legend(handles=handles,loc='lower center',ncol=7,bbox_to_anchor=(.51,.005),frameon=False,fontsize=9)
    save(fig,'04_tool_group_layout')
    # All 43 Bay columns are retained, including zero-production interbays.
    order=wc.STNFAM.tolist();mat=matrix.loc[order]
    fig,ax=plt.subplots(figsize=(18,25));fig.subplots_adjust(left=.22,right=.93,bottom=.07,top=.96)
    im=ax.imshow(mat.to_numpy(),aspect='auto',cmap='Blues',vmin=0,vmax=mat.to_numpy().max())
    ax.set_xticks(range(len(mat.columns)),mat.columns,rotation=90,fontsize=9)
    ax.set_yticks(range(len(mat)),[f'{g}  [{int(wc.set_index("STNFAM").loc[g,"bay_count"])} Bay]' for g in mat.index],fontsize=8)
    for i,j in np.argwhere(mat.to_numpy()>0):
        n=mat.iat[i,j];ax.text(j,i,str(n),ha='center',va='center',fontsize=7,color='white' if n>mat.to_numpy().max()/2 else '#18344D')
    ax.set_title('工作中心—Bay 设备数量矩阵 · 105 × 43\n按跨 Bay 数量、空间跨度排序；InterBay 三列为零',fontsize=15,pad=14)
    fig.colorbar(im,ax=ax,shrink=.28,pad=.015,label='生产设备实例数');save(fig,'05_workcenter_bay_heatmap')
    fig,axes=plt.subplots(3,1,figsize=(18,11),sharex=True,gridspec_kw={'hspace':.18});fig.subplots_adjust(left=.07,right=.97,top=.93,bottom=.09)
    x=np.arange(len(bs));barcolors=['#5584B1' if x=='INTRABAY' else '#B8BEC6' for x in bs.type]
    for ax,c,label in zip(axes,['production_count','workcenter_count','rail_count'],['生产设备数量','不同工作中心数量','归属 Rail 数量']):
        ax.bar(x,bs[c],color=barcolors);ax.set_ylabel(label);ax.grid(axis='y',alpha=.16);ax.set_axisbelow(True)
        for j,n in enumerate(bs[c]):
            if n:ax.text(j,n,str(n),ha='center',va='bottom',fontsize=7)
        ax.margins(y=.2)
    axes[-1].set_xticks(x,bs.Bay,rotation=90);fig.suptitle('Bay 设备、工作中心和轨道分布 · 保留全部 43 条 Bay 记录',fontsize=17);save(fig,'06_bay_equipment_distribution')
    fig,ax=setup('Bay 之间的有向轨道衔接 · 由共享 Address 节点推导',NOTE+'；Bay 点为轨道端点中位位置，不代表真实边界')
    rails(ax,r,.14,.3)
    for row in edges.itertuples():
        x,y=anchors[row.from_bay];u,v=anchors[row.to_bay]
        ax.annotate('',xy=(u,v),xytext=(x,y),arrowprops={'arrowstyle':'->','color':'#536E88','lw':.5,'alpha':.48,'connectionstyle':'arc3,rad=.09'})
    for row in b.itertuples():
        x,y=anchors[row.NAME];ax.scatter(x,y,s=240 if row.TYPE=='INTERBAY' else 65,c='#D89A3A' if row.TYPE=='INTERBAY' else '#4379A4',zorder=4)
        ax.annotate(row.NAME,(x,y),xytext=(0,9),textcoords='offset points',ha='center',fontsize=8,zorder=5)
    fig.text(.06,.04,'每条箭头：存在 incoming Rail → 共享节点 → outgoing Rail，且两条 Rail 的 BAY_NAME 不同。所有 43 Bay 拓扑互达。',fontsize=10)
    save(fig,'07_bay_directed_network')
    fig,ax=setup('轨道汇入/分流结构与 STOCKER 位置 · 拓扑诊断')
    rails(ax,r,.35,.4);rects(ax,e[e.kind=='STOCKER'],alpha=1)
    junction=metrics[(metrics.in_degree>1)|(metrics.out_degree>1)]
    ax.scatter(junction.POSITION_X/SCALE,junction.POSITION_Y/SCALE,s=5,c='#E39A37',alpha=.65,zorder=5)
    top=metrics.nlargest(12,'betweenness_sampled_k128');ax.scatter(top.POSITION_X/SCALE,top.POSITION_Y/SCALE,s=45,facecolors='none',edgecolors='#BA4146',zorder=6)
    baylabels(ax,r,b)
    fig.legend(handles=[Patch(facecolor='#444444',label='40 STOCKER'),Line2D([0],[0],marker='o',ls='',color='#E39A37',label='入度或出度 >1 的节点'),Line2D([0],[0],marker='o',ls='',markerfacecolor='none',color='#BA4146',label='抽样介数最高的 12 个节点')],loc='lower center',ncol=3,bbox_to_anchor=(.51,.035),frameon=False)
    fig.text(.055,.013,'介数为 k=128、seed=2022 的有向无权最短跳数估计；无运输任务，未测量拥堵或 ZCU 利用率。',fontsize=9)
    save(fig,'08_topology_and_stockers')
    fig,ax=setup('生产设备的空间密集区域 · 固定网格计数')
    xedges=np.arange(0,310000,10000);yedges=np.arange(-10000,160000,10000)
    hist,_,_=np.histogram2d(prod.POSITION_X,prod.POSITION_Y,bins=[xedges,yedges])
    im=ax.pcolormesh(xedges/SCALE,yedges/SCALE,np.ma.masked_where(hist.T==0,hist.T),cmap='YlOrRd',alpha=.8,zorder=1)
    rails(ax,r,.3,.25);baylabels(ax,r,b);fig.colorbar(im,ax=ax,shrink=.65,pad=.01,label='设备坐标点数 / (10000 × 10000 原始单位)')
    save(fig,'09_equipment_density_grid')
    cells=[]
    for i,j in np.argwhere(hist>0):cells.append({'xmin_raw':int(xedges[i]),'ymin_raw':int(yedges[j]),'width_raw':10000,'height_raw':10000,'equipment_count':int(hist[i,j])})
    csv(pd.DataFrame(cells).sort_values('equipment_count',ascending=False),'equipment_density_grid.csv')
    fig,ax=setup('设备原始坐标点 · 不依赖矩形锚点的分布对照', '坐标刻度 ×1000 原始单位；X/Y 等比例；点位置直接使用 Equipment.POSITION_X / POSITION_Y')
    rails(ax,r,.22,.35)
    for area in areas:
        d=prod[prod.area==area];ax.scatter(d.POSITION_X/SCALE,d.POSITION_Y/SCALE,s=5,c=palette[area],label=f'{area} ({len(d)})',zorder=4)
    for kind,color in FAC.items():
        d=e[e.kind==kind];ax.scatter(d.POSITION_X/SCALE,d.POSITION_Y/SCALE,s=16,c=color,marker='s' if kind=='STOCKER' else '^',label=kind,zorder=6)
    baylabels(ax,r,b);fig.legend(loc='lower center',ncol=7,bbox_to_anchor=(.51,.005),frameon=False,fontsize=9,markerscale=1.5)
    save(fig,'10_equipment_anchor_points')
    # Cover six-Bay, three-Bay, long two-Bay and the unique cross-row pattern.
    selected=list(dict.fromkeys(wc.head(3).STNFAM.tolist()+wc[wc.STNFAM=='TF_BE_40'].STNFAM.tolist()+wc[wc.both_A_B_rows].head(1).STNFAM.tolist()))
    for i,g in enumerate(selected,1):
        d=prod[prod.STNFAM==g];fig,ax=setup(f'跨 Bay 工作中心 · {g} · {len(d)} 台 / {d.BAY.nunique()} Bay')
        rects(ax,e,colors=['#D8DDE3']*len(e),alpha=.65);rails(ax,r,.2,.3)
        rects(ax,d,colors=[palette[d.area.iloc[0]]]*len(d),alpha=1,zorder=6)
        ax.scatter(d.POSITION_X/SCALE,d.POSITION_Y/SCALE,s=20,facecolors='none',edgecolors='#192D45',linewidths=.65,zorder=7)
        baylabels(ax,r,b)
        fig.text(.06,.045,'各 Bay 数量：'+'，'.join(f'{bay}: {n}' for bay,n in d.groupby('BAY').size().items())+'。完整设备名和坐标见交互查看器及明细表。',fontsize=10)
        save(fig,f'selected_workcenters/{i:02d}_{g}')
        # A local Bay inset as a separate equal-scale plot with partial instance labels.
        bay=d.BAY.value_counts().index[0];local=e[e.BAY==bay];target=d[d.BAY==bay]
        fig,ax=plt.subplots(figsize=(9,11));fig.subplots_adjust(left=.12,right=.96,bottom=.09,top=.89)
        rails(ax,r,.35,.5);rects(ax,local,colors=['#D4DAE2']*len(local));rects(ax,target,colors=[palette[d.area.iloc[0]]]*len(target),zorder=6)
        xmin=(local.POSITION_X-local.WIDTH/2).min()/SCALE;xmax=(local.POSITION_X+local.WIDTH/2).max()/SCALE
        ymin=(local.POSITION_Y-local.HEIGHT/2).min()/SCALE;ymax=(local.POSITION_Y+local.HEIGHT/2).max()/SCALE
        ax.set_xlim(xmin-4,xmax+7);ax.set_ylim(ymin-3,ymax+3);ax.set_aspect('equal')
        for row in target.sort_values('POSITION_Y').iloc[::max(1,len(target)//8)].head(8).itertuples():
            ax.annotate(row.NAME,(row.POSITION_X/SCALE,row.POSITION_Y/SCALE),xytext=(10,0),textcoords='offset points',fontsize=8,va='center',bbox={'facecolor':'white','edgecolor':'none','alpha':.85,'pad':1},zorder=8)
        ax.set_xlabel('X / 1000 原始单位');ax.set_ylabel('Y / 1000 原始单位');ax.grid(alpha=.12)
        fig.suptitle(f'{g} · {bay} 局部设备实例',fontsize=16);fig.text(.1,.925,'原始尺寸；矩形中心约定未确认；仅标注部分实例，避免重叠。',fontsize=9)
        save(fig,f'selected_workcenters/{i:02d}_{g}_detail')
    return palette,selected

def viewer(e,r,p,b,palette):
    def records(d):return json.loads(d.to_json(orient='records',force_ascii=False))
    data={'equipment':records(e),'rails':records(r[['NAME','BAY_NAME','FROM_NODE','TO_NODE','CURVE','x0','y0','x1','y1']]),
          'ports':records(p[p.has_equipment][['NAME','EQP_NAME','PORT_TYPE','RAILLINE_NAME','DISTANCE','derived_x','derived_y','position_method']]),
          'bays':records(b),'colors':palette,'facilities':FAC}
    (OUT/'interactive/layout_data.json').write_text(json.dumps(data,ensure_ascii=False,separators=(',',':')),encoding='utf-8')
    template=(OUT/'scripts/viewer_template.html').read_text(encoding='utf-8')
    html=template.replace('__LAYOUT_DATA__',json.dumps(data,ensure_ascii=False,separators=(',',':')))
    (OUT/'interactive/smat_layout_viewer.html').write_text(html,encoding='utf-8')

def report(e,a,r,b,p,v,matrix,wc,bs,near_df,metrics,edges,sizes,selected):
    prod=e[e.kind=='PRODUCTION'];counts=prod.groupby('area').size().reset_index(name='设备数')
    topbay=bs.sort_values(['workcenter_count','production_count'],ascending=False).head(8)
    dense=bs[bs.production_count>0].nlargest(5,'count_per_1e8_envelope_raw2')
    anchor=pd.read_csv(OUT/'tables/coordinate_anchor_diagnostics.csv')
    ncurve=int((r.CURVE==1).sum());portstats=p.groupby(['PORT_TYPE','has_equipment']).size().reset_index(name='records')
    comparison=pd.read_csv(OUT/'tables/declared_neighbor_comparison.csv')
    local_count=int((near_df.Bay==near_df.nearest_stocker_Bay).sum())
    report=f'''# SMAT2022 原始布局可视化与分析报告

生成日期：2026-10-15（Asia/Shanghai）。项目根目录：`{ROOT}`。

## 1. 结论与成果入口

本次读取原始 LVHM_E 工作簿，完成空间解析、11 类工艺映射、工作中心—Bay 分布、轨道拓扑和交互查看器。没有运行布局优化、生产仿真或 OHT 调度。全部图形坐标来自 Equipment/Address，未使用随机布局，也未使用此前 synthetic_initial_layout。

- [完整设备布局](figures/01_equipment_layout.png)
- [完整有向轨道网络](figures/02_rail_network.png)
- [设备与轨道叠加](figures/03_equipment_rail_overlay.png)
- [11 类工艺布局](figures/04_tool_group_layout.png)
- [105×43 工作中心—Bay 热力图](figures/05_workcenter_bay_heatmap.png)
- [43 Bay 设备和轨道统计](figures/06_bay_equipment_distribution.png)
- [Bay 有向连接](figures/07_bay_directed_network.png)
- [拓扑诊断与 STOCKER](figures/08_topology_and_stockers.png)
- [固定网格设备密度](figures/09_equipment_density_grid.png)
- [原始坐标点对照](figures/10_equipment_anchor_points.png)
- [离线交互查看器](interactive/smat_layout_viewer.html)

静态图同时提供 PNG（300 dpi）与保留文字的 SVG。主要全厂图为 5700×3240 像素。HTML 内嵌全部所需数据和绘制代码，可双击打开，不依赖网络或后端。

## 2. 数据来源、版本及路径

来源：[SMAT2022 作者仓库](https://github.com/kwoo-lee/SMAT2022/tree/a6df7fef99745fa49cf347306abaeb4b19002169)，固定提交 `a6df7fef99745fa49cf347306abaeb4b19002169`。
仓库工作簿路径为 `General Data/dataset 4/SMAT_2022_Model_Data_-_LVHM_E.xlsx`。

旧项目中已下载文件位于 `{OLD}/smat2022/`；本次原样复制到 `{SRC}`，未重新下载，也未修改原件。
读取文件：

- `analysis/a2_audit/smat2022/SMAT_2022_Model_Data_-_LVHM_E.xlsx`，SHA256 `{digest(SRC/'SMAT_2022_Model_Data_-_LVHM_E.xlsx')}`。
- `analysis/a2_audit/smat2022/A2_SMAT_group_mapping.csv`：沿用原 105 组映射。
- `analysis/a2_audit/核查结论与实施方案.md`、`SMT2020_LVHM_group_inventory.csv`。
- `analysis/a2_audit/smat2022/SMAT_2022_generic.txt`、`SMAT_2022_PINOKIO_documentation.txt`、`README.md`、`download_manifest.json`。

复用此前 `analysis/a2_audit/audit_smat.py` 的 OOXML `workbook_rows` 解析器，重新读取 XLSX，非仅依赖旧 CSV。已有代码只有审计及映射逻辑，没有可复用的布局绘图器。源文件复制校验及下载清单中四个文件的 SHA256 均核对通过。完整路径、大小和散列见 `validation/source_manifest.json`。

## 3. 数据完整性与映射复核

{md(pd.DataFrame([{'工作表':k,'数据行数':len(d)} for k,d in TABLES.items()]))}

全部表 NAME 唯一。Rail 起终节点、Rail.BAY_NAME、Equipment.BAY、Port 的轨道/类型/非空设备引用、Vehicle 的轨道/类型引用及 Address.ZCU_NAME 引用通过检查。设备几何数值有限，宽高为正。

Equipment：1068 个生产实例、40 STOCKER、4 COMMIT、4 COMPLETE。40 INTRABAY 每个均有一个 STOCKER；3 INTERBAY 是运输通道记录，不是 3 个新增生产区。

只在派生表中应用 `DefMet_FE_118 → DefMEt_FE_118`。105 个生产 STNFAM、11 个 STNGRP 全部匹配，未映射生产设备为 0，空清单仍保存在 `tables/unmapped_equipment.csv`。
矩阵总和、逐组设备数、逐组 Bay 集合与原映射 CSV 一致；32 个工作中心跨 Bay，142 个非零（STNFAM，Bay）组合，最大跨 6 Bay，与前次核查完全一致。

{md(counts)}

A2 LVHM 的 913 个资源与 SMAT 的 1068 个生产实例存在数量差异。此次绘制全部 1068 台，没有替换为 A2 的数量或改变映射基准。

## 4. 几何与坐标解释

### 坐标单位、方向和矩形锚点

文档明确 VehicleType.MAX_SPEED 为 mm/s，加减速度为 mm/s²，但没有逐列明确 Equipment/Address 坐标和 WIDTH/HEIGHT 的单位。此前报告的“先按 mm 整理”是情景约定，不能升级成已证实事实。本次保留原始单位，坐标轴除以 1000 便于阅读，未标为 m 或 mm。所有平面布局图的 X/Y 均保持等比例。

采用数学坐标方向：X 向右、Y 向上，没有翻转源数据。源模拟器是否使用屏幕向下的 Y 轴没有被本地说明确认，因此此图不声称复现模拟器屏幕朝向。

源文件没有设备坐标锚点、旋转或机台维护空间说明。为绘制 WIDTH×HEIGHT 矩形，本次明确暂定 POSITION_X/Y 为中心；交互和派生表保留原坐标，并标识 `rectangle_anchor_assumption=center_unconfirmed`。
几何诊断如下（按轴对齐矩形内部相交，不含恰好接触）：

{md(anchor)}

中心约定产生 533 对矩形内部相交，左下角约定产生 521 对。图 10 以原始坐标点给出不依赖矩形锚点的替代分布。诊断不是锚点定义的证明，也不能将相交直接解释成真实设备碰撞。任何重叠不应静默修复，更不能据此改动真实坐标。布局优化前必须确认锚点、维护空间与可交换机台的占地规则，当前不能声称已建立无重叠且可安装的槽位基准。

### Bay 的空间信息

Bay 表只有类型、RETICLE、NEIGHBOR_BAY，没有多边形边界。图中标签基于归属 Rail 端点的中位位置及两排设备的留白位置；没有绘制“真实 Bay 边界”。设备包络面积仅是按中心假设的矩形外包围面积，用于相对密度描述；不是洁净室可用面积、装机容量或真实 Bay 面积。

### 轨道与 Port

Rail 按 FROM_NODE→TO_NODE 构建有向图。2473 条 CURVE=0 使用端点直线；{ncurve} 条 CURVE=1 仅用金色虚线连接端点。虚线不是恢复的弧线，`endpoint_chord_raw` 只是端点弦长，曲线的 `straight_length_raw` 留空。不以弦长替代曲线长度计算旅行时间。

Port 分类：

{md(portstats)}

有 Equipment 引用的端口共 {int(p.has_equipment.sum())} 条（1068×4 + 40×2 + 8）；其余 {int((~p.has_equipment).sum())} 条为无单台 Equipment 引用的 LSTB/RSTB/UTB 记录，EQP_NAME 的逗号占位符视为无引用。不能将 22120 行解释为独立机台装卸站。

每台生产设备 4 Port，每 STOCKER 2 Port，每 COMMIT/COMPLETE 1 Port。对直线 Rail，按起点加单位方向乘 DISTANCE 推导 Port/Vehicle 位置；超过直线长度 1 原始单位的记录为 0。DISTANCE 的取整误差被保留，未强制截断。曲线上的 Port/Vehicle 坐标留空，原始 Rail+DISTANCE 仍保存。没有伪造精确曲线端口位置。HTML 默认不绘制全部端口，点击设备可查看该设备端口及可推导坐标。

500 辆 Vehicle 初始 Rail 引用全部有效，{int(v.derived_x.notna().sum())} 个可由直线恢复位置，{int(v.derived_x.isna().sum())} 个因曲线几何不足不绘制精确位置。全量记录见 `tables/vehicle_initial_positions.csv`。

## 5. 主要空间特征

全厂呈两排狭长 INTRABAY：A1–A20 位于较高 Y 区域，B1–B20 位于较低 Y 区域，三个 INTERBAY 连接两排内外侧通道。生产设备沿 Bay 的长向分布。不同工艺类大体形成连续区域，但工作中心与 Bay 并非一一对应。

生产设备原始坐标 X 范围 {prod.POSITION_X.min():.3f}–{prod.POSITION_X.max():.3f}，Y 范围 {prod.POSITION_Y.min():.3f}–{prod.POSITION_Y.max():.3f}。轨道端点的 X 范围 {a.POSITION_X.min():.3f}–{a.POSITION_X.max():.3f}，Y 范围 {a.POSITION_Y.min():.3f}–{a.POSITION_Y.max():.3f}。

73 个工作中心仅在一个 Bay，32 个跨 Bay。一个工作中心用单一空间点表示会损失设备位置、端口与源/目标设备选择。空间跨度只代表坐标离散程度，不是运输距离。

更细的分布为：73 组涉及 1 Bay，30 组涉及 2 Bay，1 组涉及 3 Bay，1 组涉及 6 Bay。生产实例数最多的 7 个 Bay 为 A11、A12、A19、A20、B4、B5、B6，均为 40 台。

五个代表工作中心及最大设备坐标点距：

{md(wc.set_index('STNFAM').loc[selected].reset_index()[['STNFAM','area','equipment_count','bay_count','bays','max_anchor_distance_raw']])}

代表图在 `figures/selected_workcenters/`：每个工作中心有全厂高亮图和一个设备较多 Bay 的等比例局部图，局部图标注部分设备名。当前示例为 {', '.join(selected)}。选择规则为排序前 3 组、薄膜代表 TF_BE_40 和唯一跨 A/B 两排的 Diffusion_FE_94，以覆盖不同空间模式；没有以优化收益作为选择依据。

Bay 设备类型复杂度最高的区域：

{md(topbay[['Bay','production_count','workcenter_count','rail_count']])}

按设备包络面积归一化的相对密集 Bay（分母不是真实 Bay 面积）：

{md(dense[['Bay','production_count','count_per_1e8_envelope_raw2']])}

另有固定 10000×10000 原始单位网格计数图/表，避免把包络面积当真实生产面积。密度结论依赖网格尺度；这是机台空间计数，不是利用率。

40 个 STOCKER 均按原坐标绘制，每 INTRABAY 一处。对生产设备坐标点计算最近 STOCKER 的欧氏距离，中位数 {near_df.anchor_distance_raw.median():.3f}，最大 {near_df.anchor_distance_raw.max():.3f} 原始单位；{local_count}/1068 台设备最近 STOCKER 与其 Bay 相同。欧氏最近不代表沿有向轨道最快，也不证明库存容量或储存策略合理。全量邻近关系见 `tables/equipment_nearest_stocker.csv`。

## 6. Bay 运输连接与拓扑诊断

Address 有向图强连通分量为 {sizes}，2858 个节点在同一个 SCC。忽略车辆、ZCU 控制、等待与端口服务约束时，全图拓扑可达。

Bay 连接规则：若 Rail r 的 TO_NODE 与 Rail s 的 FROM_NODE 是同一 Address，且 r.BAY_NAME≠s.BAY_NAME，则记 r 所属 Bay→s 所属 Bay 的有向衔接。它是两个原始轨道标签之间的过渡，不是任意空间邻近关系。每条边有 incoming_rail、outgoing_rail、shared_node 的可追溯证据，见 `tables/bay_transition_witnesses.csv`。共得到 {len(edges)} 对有向 Bay 直接衔接，43×42=1806 个不同 Bay 的有序对均有拓扑路径。

可达性还由完整 Address 图单一 SCC 独立验证，避免 Bay 聚合图因丢失内部连续性产生虚假可达。生产设备端口均有关联轨道，且 PortType.INOUT_TYPE 有明确方向；因此轨道层面具有连接基础，但不据此保证服务调度可执行。

NEIGHBOR_BAY 是另一种原始邻接描述，不能直接当有向轨道边。其 {len(comparison)} 条声明中 {int(comparison.direct_rail_transition.sum())} 条对应上述直接轨道衔接。差异保留在 `tables/declared_neighbor_comparison.csv`，不强行覆盖 Rail 推导关系。

InterBay2 与全部 40 个 INTRABAY 各有双向衔接，合计 80 个入/出过渡；InterBay1、InterBay3 分别与 20 个 INTRABAY 双向衔接，各合计 40 个过渡。由此可确认中间通道是连接两排生产区的结构性枢纽。连接统计见 `tables/bay_connection_summary.csv`。这说明值得优先研究通道依赖与替代路径，不能据此判定其已经拥堵。

图 08 将入/出度大于 1 的汇入分流节点与 STOCKER 叠加，并标出抽样介数前 12 节点。介数采用有向无权最短跳数、k=128、seed=2022，仅是结构筛查，受抽样与跳数定义影响。高介数和连接集中可能提示值得研究的路由依赖，**不等于实际拥堵、经过车流、ZCU 利用率或已确认容量瓶颈**。

## 7. 后续优化建模的可行范围

1. **集中还是分散：** 73/105 工作中心限制在一个 Bay，32/105 跨 Bay；按 Bay 数、坐标跨度和 A/B 两排分布联合描述。`workcenter_distribution_summary.csv` 保留每组跨度、Bay 清单及是否跨两排。单 Bay 也可能沿长轴分散，不能将其等同于共点。
2. **跨 Bay 的模式：** 31 组在同一排的多个 Bay 分布，只有 Diffusion_FE_94（14 台）跨 A20/B19 两排。典型样例包含 DE_FE_86 的 A11–A16 连续六 Bay、LithoTrack_FE_95 的 B7–B9 三 Bay、两 Bay 长轴分散，以及 Diffusion_FE_94 的跨排分布。跨排标记及五组图提供可核查证据，空间分离不能直接认定布局低效。
3. **高密度位置：** 上述 Bay 包络相对密度和固定网格计数已计算；不外推到实际可用面积或加工负荷。
4. **STOCKER 关系：** 每个生产 INTRABAY 一处，附近设备到 STOCKER 的点距可计算。有向路径时间、存储占用、进出策略尚不能回答。
5. **保持 Rail/Bay 时的重配置：** 可以把当前生产设备占用位置定义为“衍生候选槽位”，研究设备/工作中心重分配。源数据没有 Slot 表，也没有允许安装的空地清单。当前矩形尺寸存在差异，锚点未确认，因此不能直接断言任意两处可互换。
6. **原始可确认约束：** 当前设备占地字段、Bay 归属、RETICLE 标记、105 组对应、1068 原配置数量、Rail 方向与拓扑、端口 Rail+DISTANCE、端口输入/输出方向、车辆类型与初始位置。**需补充确认或设为假设：** 坐标单位/锚点/旋转、维修净距、真实 Bay 边界、洁净/污染/公用工程兼容性、搬迁许可、槽位适配、端口可重接规则和服务时间、工程活动、运输任务生成及 ZCU 控制语义。RETICLE 标记本身不等于已证明完整兼容性规则。
7. **决策变量建议：** 采用两层结构。上层整数 n[g,b] 配置工作中心在 Bay 的设备数；下层二元 x[g,s] 对衍生占用位置配置工作中心，并以 sum(s in b)x[g,s]=n[g,b] 连接。先限制同功能或确认兼容的区域，固定 STOCKER/COMMIT/COMPLETE 和轨道。若只做上层，必须保留组到 Bay 多点运输端口分布，不能只用组质心。
8. **Port 一致性：** 物理位置不动而改变该处工作中心时，保留位置上的 Equipment 物理 ID、矩形几何和 Port→Equipment→Rail+DISTANCE，另建场景级 Equipment→STNFAM 分配表，重建工艺到目标设备的映射。若真实搬迁设备或改变机身尺寸，则需显式重建 Equipment/Port 绑定和几何适配，不能只改 TOOL_GROUP 标签。四个生产端口的重复服务能力不可直接相加，需要端口服务语义。
9. **事实与假设：** 本报告行数、映射、坐标、跨 Bay 组合、轨道 SCC、引用和欧氏邻近统计均有代码与表格证据。减少工作中心离散度、靠近高需求工艺或靠近 STOCKER 可能改善搬运，只是待验证假设。当前没有运输事件与性能测量，不能给出改善百分比。

建议下一步先确认几何解释及允许交换规则，选择 SMAT 全 1068 生产容量情景或显式记录 A2 913 活动资源子集，再由 A2 工艺、投料及抽检/返工规则构造工作中心间需求，使用有向端口网络建立基线成本。曲线长度、端口服务与 ZCU 语义补齐后再做运输仿真验证。本次没有实施这些优化或仿真实验。

## 8. 复现与文件说明

在项目根目录执行：

```powershell
python analysis/smat_layout_viz/scripts/build_layout.py
```

环境要求见 `scripts/requirements.txt`，此次环境版本见 `validation/environment.json`。模型输入来自当前项目 `analysis/a2_audit/`，旧镜像仍存在时同时执行原件散列比对，仅向 `analysis/smat_layout_viz/` 写入成果。旧镜像不存在时仍可用当前项目的输入副本复现。复制来源详情见 source_manifest；源数据 SHA 在构建末尾重新检查。

主要表格：`equipment_position_summary.csv`（1116 实例、1068 生产）、`workcenter_bay_matrix.csv`（105×43）、`workcenter_bay_detail.csv`（142 非零组合）、`workcenter_distribution_summary.csv`（105 组）、`bay_equipment_summary.csv`（43 Bay）、`rail_geometry.csv`（3424 Rail）、`port_position_detail.csv`（22120 Port）、`vehicle_initial_positions.csv`（500 Vehicle）、`bay_directed_connections.csv`、`bay_transition_witnesses.csv`、`bay_reachability_matrix.csv`、`network_node_topology.csv`、`equipment_nearest_stocker.csv`、`equipment_density_grid.csv`。`tables/raw/` 是从原始 Excel 本次重读导出的九表快照。

验收证据：`validation/data_checks.json`（逐项断言）、`validation/visual_review.md`（实际图片检查）、`validation/browser_checks.json`（真实浏览器交互检查）和 `validation/` 中截图。查看器支持等比例缩放/平移、工艺筛选、Bay 筛选、工作中心高亮、轨道/方向/物流设施开关、设备悬停与点击端口详情。方向层绘制所有 Rail 的 FROM→TO，初始关闭以免遮挡。

浏览器验收通过本地 HTTP 服务打开此单文件 HTML。自动化浏览器禁止 file:// 协议，因此未在该浏览器中验证“双击本地文件”打开方式；HTML 内嵌数据和脚本，没有外部库、网络请求或后端依赖。
'''
    (OUT/'SMAT原始布局可视化与分析报告.md').write_text(report,encoding='utf-8')

if __name__=='__main__':
    TABLES=load();e,a,r,b,p,v,matrix,wc,bs,anchors,near=prepare(TABLES)
    G,BG,edges,metrics,sizes=network(a,r,b)
    palette,selected=figures(e,a,r,b,matrix,wc,bs,metrics,BG,edges,anchors)
    viewer(e,r,p,b,palette);report(e,a,r,b,p,v,matrix,wc,bs,near,metrics,edges,sizes,selected)
    source_manifest=json.loads((OUT/'validation/source_manifest.json').read_text(encoding='utf-8'))
    for item in source_manifest:
        check('source unchanged after build '+Path(item['local_path']).name,digest(Path(item['local_path'])),item['sha256'])
        if Path(item['source']).exists():check('original unchanged after build '+Path(item['source']).name,digest(Path(item['source'])),item['sha256'])
    (OUT/'validation/data_checks.json').write_text(json.dumps(CHECKS,ensure_ascii=False,indent=2),encoding='utf-8')
    env={'python':sys.version,'platform':platform.platform(),'packages':{k:importlib.metadata.version(k) for k in ['numpy','pandas','matplotlib','networkx','scipy']}}
    (OUT/'validation/environment.json').write_text(json.dumps(env,ensure_ascii=False,indent=2),encoding='utf-8')
    print(json.dumps({'passed_checks':len(CHECKS),'counts':e.kind.value_counts().to_dict(),'top_groups':wc.head(5).to_dict('records'),'top_complex_bays':bs.nlargest(5,'workcenter_count').to_dict('records'),'bay_edges':len(edges),'stocker_same_bay':int((near.Bay==near.nearest_stocker_Bay).sum()),'anchor_diagnostics':pd.read_csv(OUT/'tables/coordinate_anchor_diagnostics.csv').to_dict('records')},ensure_ascii=False,indent=2))
