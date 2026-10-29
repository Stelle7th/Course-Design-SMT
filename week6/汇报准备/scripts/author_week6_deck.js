var result = await artifactSession.run(async ({presentation,session}) => {
  const D=__DECK_DATA__;
  const purple='#783C91',ink='#25232E',muted='#716A78',teal='#168E93',grey='#E5DFE9';
  presentation.theme.defaultFont='Microsoft YaHei';
  presentation.slides.keep([]);
  function shape(s,g,x,y,w,h,fill='none',stroke='none',lw=0){return s.shapes.add({geometry:g,position:{left:x,top:y,width:w,height:h},fill,line:{style:'solid',fill:stroke,width:lw}});}
  function tx(s,v,x,y,w,h,size=28,color=ink,bold=false,align='left'){
    const t=shape(s,'textbox',x,y,w,h);t.text=v;t.text.style={fontSize:size,color,bold,fontFamily:'Microsoft YaHei',alignment:align};return t;
  }
  function base(title,n){const s=presentation.slides.add({width:1280,height:720,background:{fill:'#FFFFFF'}});tx(s,title,56,40,1170,72,44,ink,true);tx(s,'A2 组  第六周课程设计',56,675,700,28,17,muted);tx(s,n+' / 8',1130,675,94,28,17,muted,false,'right');return s;}
  function table(s,values,x,y,w,h,widths){const t=s.tables.add({rows:values.length,columns:values[0].length,left:x,top:y,width:w,height:h,columnWidths:widths,values});t.cells.block({row:0,column:0,rowCount:values.length,columnCount:values[0].length}).assign({textStyle:{fontSize:25,color:ink},fill:'#FFFFFF'});t.cells.block({row:0,column:0,rowCount:1,columnCount:values[0].length}).assign({fill:'#F3EDF7',textStyle:{fontSize:25,bold:true,color:purple}});t.borders.assign({fill:grey,width:1,style:'solid'});return t;}
  function connect(s,a,b,color=purple){return s.shapes.connect(a,b,{kind:'straight',fromSide:'right',toSide:'left',line:{fill:color,width:2,style:'solid'},tail:{type:'arrow',width:'med',length:'med'}});}
  const noteSource='数据来源：F:/Grade4/课程设计/week6/汇报准备/MILP_A2_A3/summary.json、layout_result.csv、processing_flow.csv、boundary_flow.csv、equipment_relocation.csv、independent_checks.json。';
  let s=base('第六周课程设计工作周报',1);
  tx(s,'半导体制造系统\n两 Bay 设备布局 MILP 验证',70,170,1120,175,59,ink,true);
  tx(s,'参考布局评价与设备位置、加工流量的联合优化',74,390,1100,60,30,purple);
  tx(s,'A2、A3 真实槽位    48 台设备    173 个二元变量',74,480,1110,55,28,ink);
  tx(s,'王嘉赫  刘若石  孙奕扬  周钦铭',74,570,1000,40,24,ink);
  tx(s,'指导老师：王晓芳    2026 年 10 月 22 日',74,613,1050,35,22,muted);
  s.speakerNotes.text='约 25 秒。上周完成了静态布局恢复和配置建模。本周先建立可求解的参考布局评价，再选取 A2、A3 两个 Bay，验证设备位置与加工、运输流量的联合优化。本次讲述仅覆盖 MILP 方法。'+noteSource;

  s=base('上周计划与本周完成情况',2);
  table(s,[['阶段','完成内容','对应产物'],['上周','静态布局恢复、联合建模方案','设备与轨道图、数学模型'],['本周基础','生产与空间关联、参考布局 LP','审计表、完整运输弧结果'],['本周验证','两 Bay 位置与加工物流联合 MILP','布局坐标、流量、gap、检查记录']],64,160,1152,340,[170,550,432]);
  tx(s,'本周新增：设备位置进入整数决策，形成可复核的局部布局结果',68,545,1130,95,32,purple,true);
  s.speakerNotes.text='约 35 秒。上周主要完成静态布局和数学方案。本周原有脚本完成了数据审计和固定参考布局 LP，设备位置保持固定。在这一基础上，新建两 Bay 的局部联合 MILP，位置变量、加工量和运输量同时求解。这样可以先检查模型，避免全厂规模掩盖建模问题。来源：week5/A2组_第五周周报_精简版(1).pdf；week6/output/e0_audit/audit_report.md；week6/output/e1_reference_lp_full/e1_summary.json。'+noteSource;

  s=base('A2、A3 局部模型的边界',3);
  const region=shape(s,'rect',350,185,580,355,'#FFFFFF',purple,2);
  tx(s,'优化区域：A2 与 A3',380,205,520,44,31,purple,true,'center');
  const a2=shape(s,'rect',390,280,220,142,'#F5F0F8',purple,1);
  tx(s,'A2',410,294,180,39,31,purple,true,'center');tx(s,'24 台工艺设备\n设备组 13、48',405,341,190,67,22,ink,false,'center');
  const a3=shape(s,'rect',670,280,220,142,'#EDF7F6',teal,1);
  tx(s,'A3',690,294,180,39,31,teal,true,'center');tx(s,'24 台工艺设备\n组 48 / 50 / 65',676,341,208,67,22,ink,false,'center');
  tx(s,'区域内决策：槽位配置 x\n加工量 y 与物流量 f',378,457,525,68,25,ink,false,'center');
  const left=shape(s,'rect',48,290,232,142,'#FFFFFF',grey,1.5);tx(s,'外部源设备',64,307,202,40,28,ink,true,'center');tx(s,'固定供给量\na(j,r)',70,355,188,62,24,muted,false,'center');
  const right=shape(s,'rect',1000,290,232,142,'#FFFFFF',grey,1.5);tx(s,'外部目标设备',1014,307,204,40,28,ink,true,'center');tx(s,'固定接收量\nb(r,j)',1020,355,192,62,24,muted,false,'center');
  connect(s,left,region);connect(s,region,right);
  tx(s,'固定输入：现有槽位与端口、轨道、设备数量、区域工序量',64,568,1152,42,25,ink);
  tx(s,'区域外生产由供需边界保留；本例无正的区域内部直接转移量',64,615,1152,37,22,muted);
  s.speakerNotes.text='约 55 秒。这张图说明裁剪边界。我们只调整 A2、A3 内的 48 台工艺设备，使用其现有槽位和端口。区域外的工序没有直接删掉，而是保留每个外部源的固定供给和每个外部目标的固定接收量。59 个产品工序在这个区域承担的加工量来自原完整弧参考解。MILP 决定这些工序在哪个槽位加工，以及进出区域的流量如何分配。轨道仍使用原有有向网络，距离路径可以经过区域外公共通道。本例参考流中没有正的区域内直接转移，因此当前验证重点是位置、加工和外部进出物流的耦合。'+noteSource;

  s=base('设备位置与加工物流联合模型',4);
  tx(s,'二元配置 x(k,c)',64,160,350,48,32,purple,true);tx(s,'槽位 c 放置哪一类设备\n设备组与尺寸类别数量守恒',64,223,350,110,26);
  tx(s,'连续加工 y(r,c)',465,160,350,48,32,purple,true);tx(s,'工序 r 在槽位 c 的加工量\n完成固定的区域工序需求',465,223,350,110,26);
  tx(s,'连续物流 f',866,160,350,48,32,purple,true);tx(s,'外部设备与槽位间的流量\n保持源供给与目标接收量',866,223,350,110,26);
  tx(s,'目标：最小化局部相关加权运输距离  min Σ D·f',64,380,1152,56,33,ink,true);
  tx(s,'约束：槽位唯一占用、设备数量守恒、尺寸与工艺阶段兼容',64,465,1152,48,27);
  tx(s,'耦合：加工机时 ≤ 配置设备的有效机时，流入 = 加工量 = 流出',64,522,1152,48,27);
  tx(s,'场景参数：T = 10080 min，需求缩放 0.25，有效机时系数 0.85',64,602,1152,42,23,muted);
  s.speakerNotes.text='约 45 秒。x 是设备类型与尺寸类别到槽位的二元配置，y 和 f 是连续加工量和运输流量。工作中心数量及尺寸类别全部保持，只能匹配相同尺寸、工艺功能和 FE/BE 阶段的槽位。产能约束把配置与加工联系起来：没有相应设备的槽位不能分配该组加工量。距离由固定槽位端口预先计算，所以目标和约束仍是线性的。这里采用 0.25 倍需求，是当前参考实验场景。'+noteSource;

  s=base('现有槽位的布局优化前后',5);
  const palette={'DE_BE_13':'#783C91','DE_BE_48':'#168E93','DE_BE_50':'#D88F31','DE_BE_65':'#5685BE'};
  for(const [col,bx,title] of [['original_group',125,'参考布局'],['optimized_group',490,'MILP 布局']]){
    tx(s,title,bx-40,132,290,45,30,ink,true,'center');
    tx(s,'A2',bx+9,180,80,30,22,ink,true,'center');tx(s,'A3',bx+92,180,100,30,22,ink,true,'center');
    const sc=5.45;
    for(const r of D.layout){const x=bx+(r.position_x/1000-13)*sc,y=620-(r.position_y/1000-70)*sc,w=r.width/1000*sc,h=r.height/1000*sc;shape(s,'rect',x-w/2,y-h/2,w,h,palette[r[col]],'#FFFFFF',.6);if(r.changed_group)shape(s,'rect',x-w/2-2,y-h/2-2,w+4,h+4,'none',ink,1.5);}
  }
  tx(s,'6 个槽位调整设备组',825,157,385,50,31,purple,true);
  const changed=D.layout.filter(r=>r.changed_group);
  table(s,[['槽位','原组','新组'],...changed.map(r=>['S'+r.slot_name.replace('ECH',''),r.original_group.split('_').at(-1),r.optimized_group.split('_').at(-1)])],825,230,380,328,[150,115,115]);
  tx(s,'设备类型不变，仅调整位置',825,590,390,34,23,muted);
  let k=0;for(const [group,color] of Object.entries(palette)){shape(s,'rect',64+k*302,638,20,16,color);tx(s,group,92+k*302,631,260,32,19);k++;}
  s.speakerNotes.text='约 45 秒。两幅图使用同一套真实槽位和坐标，颜色代表四个设备组，黑框表示设备组改变的槽位。主目标取得最优距离后，再尽量减少槽位变化，最终只需 6 个。S0146 表示参考设备 ECH0146 所在的固定槽位，并不是把 ECH0146 改造成另一种设备。具体设备类型保持不变，采用设备移动实现配置。图中按原始坐标的中心约定绘制。'+noteSource;

  s=base('具体例子：ECH0155 从 A3 迁至 A2',6);
  const old=shape(s,'rect',72,170,435,165,'#FFFFFF',purple,2);tx(s,'原位置：A3，槽位 S0155',94,192,390,48,30,purple,true);tx(s,'坐标 (31.707，121.042)\n端口 ECH0155_Port1',94,253,390,70,24);
  const dest=shape(s,'rect',773,170,435,165,'#FFFFFF',teal,2);tx(s,'新位置：A2，槽位 S0146',795,192,390,48,30,teal,true);tx(s,'坐标 (26.630，77.292)\n端口 ECH0146_Port1',795,253,390,70,24);connect(s,old,dest);
  tx(s,'保持 DE_BE_50 类型及占地尺寸，使用目标槽位端口接入轨道',72,376,1135,58,28,ink,true);
  tx(s,'同一外部源 LITH0213 到两个槽位的路径对照',72,465,1135,44,28,purple,true);
  tx(s,'185.042    →    179.535',80,525,790,78,45,ink,true);
  tx(s,'减少 5.507 千原始距离单位',800,538,415,60,25,teal,true);
  tx(s,'坐标与距离均按原始单位 / 1000 展示。单条路径对照不等于整体改善率。',72,618,1136,35,20,muted);
  s.speakerNotes.text='约 65 秒。这里展示一台有明确新槽位加工分配的设备。ECH0155 属于 DE_BE_50，从 A3 的 S0155 移到 A2 的 S0146，设备类型和尺寸保持不变，但对接的固定端口变为 ECH0146_Port1。完整布局中，其他设备同步迁移，腾出并填补槽位。按同类设备可交换的模型，这是六台设备重排的一种具体身份实现。为了说明距离矩阵如何改变，我们固定同一外部源 LITH0213 比较两个槽位的有向最短路径，距离从 185.042 降到 179.535 千原始单位。新布局中 part_5 第169步在这一槽位有正流量。这个对照解释位置和端口改变的影响，并不表示整厂收益来自这一条路径；整体 0.582% 来自六台设备与加工物流的联合优化。'+noteSource+'路径对照来源：week6/汇报准备/presentation_data.json 中 example 字段。';

  s=base('局部求解结果与独立验证',7);
  table(s,[['指标','结果'],['参考局部加权距离','304,663,194.167'],['优化后局部加权距离','302,889,755.960'],['总变量 / 二元变量','8,296 / 173'],['约束数','5,660'],['最优性 gap','0']],64,165,720,380,[330,390]);
  tx(s,'0.582%',845,170,365,105,70,teal,true);tx(s,'局部相关加权距离降低',841,285,375,52,27,ink,true);
  tx(s,'独立检查全部通过',842,384,375,45,28,purple,true);tx(s,'设备数量与工艺兼容\n需求与逐槽位流守恒\n外部供需与设备产能\n固定新布局后的 LP 重评',842,441,375,157,24);
  tx(s,'距离单位：原始距离单位·lot。改善率仅针对 A2、A3 的相关运输。',64,608,1152,43,22,muted);
  s.speakerNotes.text='约 45 秒。当前模型有8296个变量，其中173个为二元配置变量。参考局部加权距离约3.0466亿，优化后约3.0289亿，降低0.582%，求解器主目标gap为零。导出的CSV独立检查验证了设备数量、工艺兼容、加工需求、每个槽位的流入和流出、外部供需边界与产能。固定新布局后再次求解LP，成本与MILP一致。这里的最优性只针对给定槽位、给定生产边界的局部模型。'+noteSource;

  s=base('当前边界与下一步工作',8);
  tx(s,'本次已经验证',64,165,510,50,32,purple,true);tx(s,'现有槽位中的设备整数配置\n配置、加工量与边界物流联合求解\n具体位置输出与独立验收',64,245,540,184,28);
  tx(s,'下一步保持小规模',700,165,510,50,32,purple,true);tx(s,'选择有内部工序转移的 2–3 个 Bay\n控制产品数与活跃工序数\n统一边界后做负荷敏感性实验',700,245,515,184,28);
  tx(s,'适用范围',64,478,1135,45,29,ink,true);
  tx(s,'当前采用 0.25 倍需求及确定性加工近似，尚未覆盖完整抽检、返工和动态拥堵。',64,539,1150,55,24,muted);
  tx(s,'洁净、公用工程和维护条件仍需补充；本结果用于局部模型验证。',64,606,1150,45,24,muted);
  s.speakerNotes.text='约 35 秒。本周已经完成的是两Bay条件下的位置整数决策和加工物流联合验证。下一步继续控制在两到三个Bay，优先选择存在内部工序转移的区域，并限制产品与活跃工序规模，再做统一边界下的负荷敏感性。当前结果基于0.25倍需求以及批处理等效机时等确定性近似，抽检、返工、洁净、公用工程和动态拥堵仍需逐步补充。'+noteSource;
  return {slideCount:presentation.slides.items.length,title:'A2组 第六周周报：两 Bay 设备布局 MILP 验证'};
},{artifactType:'presentation'});
nodeRepl.write(result);
