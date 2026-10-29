var oneSlideResult = await artifactSession.run(async ({presentation}) => {
  const D=__DECK_DATA__;
  const purple='#783C91',ink='#25232E',muted='#716A78',teal='#168E93';
  presentation.theme.defaultFont='Microsoft YaHei';
  presentation.slides.keep([]);
  const s=presentation.slides.add({width:1280,height:720,background:{fill:'#FFFFFF'}});
  function sh(g,x,y,w,h,fill='none',stroke='none',lw=0){return s.shapes.add({geometry:g,position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:stroke,width:lw}});}
  function tx(v,x,y,w,h,size=26,color=ink,bold=false,align='left'){const t=sh('textbox',x,y,w,h);t.text=v;t.text.style={fontSize:size,color,bold,fontFamily:'Microsoft YaHei',alignment:align};return t;}
  tx('两 Bay 局部布局 MILP 验证',56,35,1168,70,44,ink,true);
  tx('A2、A3 真实槽位  ·  48 台设备  ·  4 个设备组  ·  59 道区域工序',58,110,1165,42,25,muted);
  const palette={'DE_BE_13':purple,'DE_BE_48':teal,'DE_BE_50':'#D88F31','DE_BE_65':'#5685BE'};
  for(const [col,bx,title] of [['original_group',80,'参考布局'],['optimized_group',380,'优化布局']]){
    tx(title,bx-2,173,224,42,28,ink,true,'center');
    tx('A2',bx+20,218,66,30,20,muted,true,'center');tx('A3',bx+110,218,66,30,20,muted,true,'center');
    for(const r of D.layout){const sc=5.1,x=bx+(r.position_x/1000-13)*sc,y=550-(r.position_y/1000-74)*sc,w=r.width/1000*sc,h=r.height/1000*sc;sh('rect',x-w/2,y-h/2,w,h,palette[r[col]],'#FFFFFF',.6);if(r.changed_group)sh('rect',x-w/2-2,y-h/2-2,w+4,h+4,'none',ink,1.5);}
  }
  tx('→',295,355,66,60,42,muted,true,'center');
  let k=0;for(const [group,color] of Object.entries(palette)){sh('rect',58+k*154,570,15,15,color);tx(group.replace('DE_BE_','组 '),80+k*154,561,117,32,20,ink);k++;}
  tx('颜色表示设备组；黑框标出 6 个调整槽位',58,528,605,35,21,muted);
  tx('联合优化什么',714,172,510,43,28,purple,true);
  tx('设备槽位配置\n工序加工量与进出物流分配',714,223,510,83,27,ink);
  tx('0.582%',710,318,510,92,70,teal,true);
  tx('局部加权运输距离降低',716,415,500,43,28,ink,true);
  tx('6 / 48 槽位调整  ·  gap = 0',716,478,500,40,25,purple,true);
  tx('18 道工序改善，41 道基本不变',716,530,500,39,24,muted);
  tx('移动例：ECH0155（DE_BE_50）由 A3 → A2，设备类型保持不变',58,610,1166,40,25,ink);
  const link=tx('打开 HTML 交互展示：布局变化 → 工序收益 → 实际路径',58,657,1155,35,24,purple,true);
  link.name='OPEN_MILP_HTML';
  tx('固定边界、0.25 倍需求；未计搬迁成本。改善率仅针对两 Bay 相关运输。',58,696,1158,22,16,muted);
  s.speakerNotes.text=`【本页开场，约 40 秒】
我们在 A2、A3 两个 Bay 的 48 台真实设备上做局部 MILP 验证，覆盖 4 个设备组、59 道区域工序。外部供需、槽位端口与轨道、设备组及尺寸类别数量固定，联合决定设备放在哪个槽位、工序在哪里加工以及进出物流如何分配。目标是最小化“运输量×有向轨道最短距离”的总和。参考成本 304,663,194.167，优化后 302,889,755.960，降低 0.582%；6 个槽位调整，主目标 gap 为 0，独立检查及固定新布局后的 LP 重评通过。这些是给定边界和 0.25 倍需求下的局部结果，尚未计搬迁成本。

【点击本页紫色链接，按 HTML 讲解，约 2 分钟】
1. 布局怎么变了：先看默认槽位 S0146。颜色表示设备组，这里从组 48 变成组 50，是槽位上的设备换了，并非把机器改造成另一种类型。4 种颜色都属于后段干法刻蚀设备；同组聚集没有写进模型，因此少量颜色分散。黑框只有 6 个，另外 42 个槽位保持原组。
切换“跟随具体设备看”，选择 ECH0155：它始终属于 DE_BE_50，从 A3 的 S0155 移至 A2 的 S0146，并对接目标槽位端口 ECH0146_Port1。其他设备同步重排，这是同组设备可交换条件下的一种具体身份实现。
2. 哪些工序受益：59 道区域工序中，18 道改善、41 道基本不变。选择示例 part_5 第 169 步，进入实际路径页。
3. 实际路径为什么变短：固定外部源 LITH0213 与外部目标 ECH0498。该工序优化前由 A3 的 ECH0163 加工，优化后改由搬到 A2 的 ECH0155 加工。不要把这解释成优化前也是 ECH0155 加工。每 lot 入程距离 172.418→179.535，出程 286.202→269.243，总计 458.620→448.778，降低 2.146%（显示值均为千原始距离单位）。入程变长，但出程缩短得更多，说明模型在权衡完整进出路径。2.146% 是这道工序的收益，整段 59 道工序的加权总收益为 0.582%。可切换前后线路显示以说明走向。

【边界答辩】
这是两 Bay 的条件局部模型；保留每个外部源供给、每个外部目标接收量及区域工序量。本例没有正的区域内部直接转移流，主要验证设备配置、加工与进出物流耦合。gap=0 仅指当前数学模型的主目标最优，不能推出全厂改善率、实际周期时间或经济收益。

【链接使用】
本 PPTX 与 MILP交互展示.html 放在同一文件夹；合并到总汇报后也保留这一相对位置。放映时点击紫色链接；编辑模式可 Ctrl+单击。若演示软件询问打开本地文件，允许打开即可。

【数据来源】
week6/汇报准备/MILP_A2_A3/summary.json、layout_result.csv、processing_flow.csv、boundary_flow.csv、equipment_relocation.csv、independent_checks.json；week6/交互展示/milp-data.json；week6/汇报成稿/MILP交互展示.html。`;
  await presentation.render({slide:0,scale:1});
  await presentation.export({format:'pptx',fileName:'two-bay-one-slide.pptx'});
  return {slideCount:presentation.slides.items.length,hyperlinkShapeName:link.name};
},{artifactType:'presentation',create:true});
nodeRepl.write(oneSlideResult);
