from pathlib import Path
from collections import Counter
import json,sys,csv
import numpy as np
import pandas as pd
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
from matplotlib.patches import Rectangle,Patch

ROOT=Path(__file__).resolve().parents[3];WEEK=ROOT/'week6';OUT=WEEK/'汇报准备';FIG=OUT/'figures'
plt.rcParams.update({'font.sans-serif':['Microsoft YaHei','SimHei','DejaVu Sans'],'axes.unicode_minus':False,
                     'font.size':12,'svg.fonttype':'none','axes.spines.top':False,'axes.spines.right':False})
PURPLE,TEAL,GREY='#783C91','#168E93','#DCD7E2'
summaries=[]
for folder in sorted(OUT.glob('MILP_*')):
    if not (folder/'summary.json').exists():continue
    s=json.loads((folder/'summary.json').read_text(encoding='utf-8'));s['folder']=folder;summaries.append(s)
    if 'objective' not in s:continue
    layout=pd.read_csv(folder/'layout_result.csv',encoding='utf-8-sig')
    relocation=[]
    for (group,width,height),source in layout[layout.changed_group].groupby(['original_group','width','height']):
        target=layout[layout.changed_group & layout.optimized_group.eq(group) & layout.width.eq(width) & layout.height.eq(height)]
        assert len(source)==len(target)
        for a,b in zip(source.sort_values('slot_name').itertuples(),target.sort_values('slot_name').itertuples()):
            relocation.append({'equipment_name':a.slot_name,'equipment_group':group,'source_slot':'S'+a.slot_name.removeprefix('ECH'),
                               'target_slot':'S'+b.slot_name.removeprefix('ECH'),'source_bay':a.bay,'target_bay':b.bay,
                               'source_x':a.position_x,'source_y':a.position_y,'target_x':b.position_x,'target_y':b.position_y,
                               'target_port':b.port_name})
    pd.DataFrame(relocation).to_csv(folder/'equipment_relocation.csv',index=False,encoding='utf-8-sig')
    y=pd.read_csv(folder/'processing_flow.csv',encoding='utf-8-sig')
    f=pd.read_csv(folder/'boundary_flow.csv',encoding='utf-8-sig')
    internal=pd.read_csv(folder/'internal_flow.csv',encoding='utf-8-sig')
    boundary=pd.read_csv(folder/'boundary_conditions.csv',encoding='utf-8-sig')
    orig_ops=pd.read_csv(WEEK/'output/e1_reference_lp_full/operation_flow.csv',encoding='utf-8-sig')
    q=orig_ops[orig_ops.equipment_name.isin(layout.slot_name)].groupby(['part','step']).flow_lots.sum()
    ys=y.groupby(['part','step']).flow_lots.sum()
    demanderror=max(abs(ys.get(k,0)-v) for k,v in q.items())
    yg=y.groupby(['part','step','slot']).flow_lots.sum().to_dict()
    incoming=f[f.direction.eq('in')].groupby(['part','step','slot']).flow_lots.sum().to_dict()
    outgoing=f[f.direction.eq('out')].groupby(['part','step','slot']).flow_lots.sum().to_dict()
    for r in internal.itertuples():
        k=(r.part,r.step_from,r.source_slot);outgoing[k]=outgoing.get(k,0)+r.flow_lots
        k=(r.part,r.step_to,r.target_slot);incoming[k]=incoming.get(k,0)+r.flow_lots
    keys=set(yg)|set(incoming)|set(outgoing)
    inerror=max(abs(yg.get(k,0)-incoming.get(k,0)) for k in keys)
    outerror=max(abs(yg.get(k,0)-outgoing.get(k,0)) for k in keys)
    bf=f.groupby(['direction','part','step','external_equipment']).flow_lots.sum()
    berror=max(abs(bf.get((r.direction,r.part,r.step,r.external_equipment),0)-r.flow_lots) for r in boundary.itertuples())
    countok=Counter(zip(layout.original_group,layout.width,layout.height))==Counter(zip(layout.optimized_group,layout.width,layout.height))
    compatible=all(layout.set_index('slot_name').optimized_group[r.slot]==r.group for r in y.itertuples())
    caperror=max(0,float(y.groupby('slot').machine_time_min.sum().max())-8568)
    cost=float((f.flow_lots*f.distance_raw).sum()+(internal.flow_lots*internal.distance_raw).sum())
    costerror=abs(cost-s['objective'])/max(1,s['objective'])
    checks={'equipment_counts_by_group_and_footprint':countok,'processing_compatible':compatible,
      'max_regional_demand_residual':float(demanderror),'max_inflow_residual':float(inerror),
      'max_outflow_residual':float(outerror),'max_external_boundary_residual':float(berror),
      'max_capacity_excess_min':float(caperror),'objective_relative_difference':float(costerror),
      'checked_from':'saved CSV files and original reference operation allocations; separate from solver matrices'}
    checks['passed']=bool(countok and compatible and max(demanderror,inerror,outerror,berror)<1e-6 and caperror<1e-5 and costerror<1e-9)
    (folder/'independent_checks.json').write_text(json.dumps(checks,ensure_ascii=False,indent=2),encoding='utf-8')
    assert checks['passed'],checks

def save(fig,name):
    for ext in ['png','svg']:fig.savefig(FIG/(name+'.'+ext),dpi=190,bbox_inches='tight',facecolor='white')
    plt.close(fig)

valid=[s for s in summaries if 'objective' in s]
fig,(a,b)=plt.subplots(1,2,figsize=(13.6,7.4),gridspec_kw={'width_ratios':[1.2,1]})
for i,s in enumerate(valid):
    yy=i*3
    a.barh(yy+1,100,color=GREY,height=.65)
    a.barh(yy,100*s['objective']/s['reference_affected_cost'],color=PURPLE,height=.65)
    a.text(1,yy+1,'参考布局  100',va='center',fontsize=12)
    a.text(1,yy,f'MILP 布局  {100*s["objective"]/s["reference_affected_cost"]:.3f}',va='center',color='white',fontsize=12)
    a.text(102,yy+.5,' / '.join(s['bays']),va='center',fontsize=12)
a.set_xlim(0,130);a.set_yticks([]);a.set_xlabel('局部相关加权距离指数，参考布局 = 100')
a.set_title('同一局部边界下比较',loc='left',fontsize=17,pad=18)
labels=[' / '.join(s['bays']) for s in valid];improvements=[s['improvement_local']*100 for s in valid]
b.barh(labels,improvements,color=TEAL,height=.45)
for i,s in enumerate(valid):
    b.text(improvements[i]+.025,i,f'{improvements[i]:.3f}%\ngap {s["mip_gap"]:.2%}',va='center',fontsize=12)
b.set_xlim(0,max(1,max(improvements)*1.4));b.set_xlabel('局部相关加权距离降低 (%)')
b.set_title('改善幅度与求解间隙',loc='left',fontsize=17,pad=18)
fig.suptitle('现有两个 Bay 的联合 MILP 验证',x=.08,ha='left',fontsize=23,fontweight='bold')
fig.text(.08,.89,'固定外部物流边界，联合优化区域内设备配置、加工量与物流分配。',fontsize=12,color='#6A6270')
fig.text(.08,.035,'各案例分别以自己的局部参考成本归一化。改善率不代表全厂改善，也不能直接用于比较不同区域的难度。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.08,right=.94,top=.77,bottom=.15,wspace=.45)
save(fig,'07_milp_result_comparison')

folder=OUT/'MILP_A2_A3';layout=pd.read_csv(folder/'layout_result.csv',encoding='utf-8-sig')
s=json.loads((folder/'summary.json').read_text(encoding='utf-8'))
colors={'DE_BE_13':'#783C91','DE_BE_48':'#168E93','DE_BE_50':'#D88F31','DE_BE_65':'#5685BE'}
fig=plt.figure(figsize=(15.5,9));gs=fig.add_gridspec(1,3,width_ratios=[1,1,1.65],wspace=.23)
for ii,col,title in [(0,'original_group','参考布局'),(1,'optimized_group','MILP 布局')]:
    ax=fig.add_subplot(gs[ii])
    for row in layout.itertuples():
        x,y=row.position_x/1000,row.position_y/1000;w,h=row.width/1000,row.height/1000
        ax.add_patch(Rectangle((x-w/2,y-h/2),w,h,facecolor=colors[getattr(row,col)],edgecolor='white',lw=.5))
        if row.changed_group:
            ax.add_patch(Rectangle((x-w/2-.35,y-h/2-.35),w+.7,h+.7,facecolor='none',edgecolor='#26212E',lw=1.5))
            ax.text(x,y,getattr(row,col).split('_')[-1],ha='center',va='center',fontsize=8,color='white',fontweight='bold')
    for bay in ['A2','A3']:
        chunk=layout[layout.bay.eq(bay)];ax.text(chunk.position_x.mean()/1000,140,bay,ha='center',fontweight='bold',fontsize=14)
    ax.set_xlim(13,46);ax.set_ylim(70,143);ax.set_aspect('equal')
    ax.set_xlabel('X / 1000 原始单位');ax.set_title(title,fontsize=18,pad=18)
    if ii==0:ax.set_ylabel('Y / 1000 原始单位')
    else:ax.set_yticklabels([])
ax=fig.add_subplot(gs[2]);ax.axis('off')
changed=layout[layout.changed_group].copy()
table=[('S'+r.slot_name.removeprefix('ECH'),r.bay,r.original_group.split('_')[-1],r.optimized_group.split('_')[-1]) for r in changed.itertuples()]
tab=ax.table(cellText=table,colLabels=['槽位','Bay','原设备组','新设备组'],loc='upper left',bbox=[0,.38,1,.48],cellLoc='center')
tab.auto_set_font_size(False);tab.set_fontsize(10)
for (r,c),cell in tab.get_celld().items():
    cell.set_edgecolor('#DED8E2');cell.set_facecolor('#F3EFF5' if r==0 else 'white')
ax.text(0,.94,f'48 台设备，{s["changed_group_slots"]} 个槽位改变设备组',fontsize=15,fontweight='bold',transform=ax.transAxes)
ax.text(0,.29,f'局部相关加权距离降低 {s["improvement_local"]:.3%}\n主目标 gap = {s["mip_gap"]:.2%}\n固定新布局后的 LP 重评通过',fontsize=13,linespacing=1.8,va='top',transform=ax.transAxes)
handles=[Patch(facecolor=c,label=g) for g,c in colors.items()]
fig.legend(handles=handles,loc='lower center',ncol=4,frameon=False,bbox_to_anchor=(.5,.065),fontsize=11)
fig.suptitle('现有 A2、A3 的设备槽位重排',x=.07,ha='left',fontsize=24,fontweight='bold')
fig.text(.07,.91,'保持设备组数量和占地尺寸类别，第一目标最小运输距离，第二目标尽量减少槽位变化。',fontsize=12,color='#6A6270')
fig.text(.07,.025,'黑框表示调整槽位。S0146 指原 ECH0146 所在槽位；设备类型保持不变。几何按原始坐标中心约定绘制。',fontsize=10,color='#6A6270')
fig.subplots_adjust(left=.07,right=.97,top=.82,bottom=.19)
save(fig,'08_two_bay_layout')

rows=[]
for s in summaries:
    rows.append({k:s.get(k) for k in ['bays','equipment_count','group_count','regional_operation_count','binary_variables','total_variables','constraints','reference_affected_cost','objective','improvement_local','mip_gap','dual_bound','solver_seconds','changed_group_slots','positive_internal_reference_transitions']})
pd.DataFrame(rows).to_csv(OUT/'tables/milp_case_comparison.csv',index=False,encoding='utf-8-sig')
print(json.dumps(rows,ensure_ascii=False,indent=2))
