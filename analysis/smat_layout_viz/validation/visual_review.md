# 实际视觉检查记录

日期：2026-10-15。检查方式：打开实际 PNG，并结合 contact_overview.png、contact_workcenters.png 检查全套结果。浏览器另用真实交互操作检查，截图为 browser_*.jpg。

| 文件 | 检查结果 |
|---|---|
| 01_equipment_layout | 全厂两排设备及源/汇、STOCKER 可见；43 Bay 标签可辨；设备矩形尺寸来自原表。 |
| 02_rail_network | 提高独立轨道图对比度后复查；直线与虚线曲线连接示意可见，局部箭头方向保留。 |
| 03_equipment_rail_overlay | 轨道和设备对齐，轨道透明度不会盖住设备；源/汇位于工厂四端附近。 |
| 04_tool_group_layout | 11 类颜色与图例设备数相符；图例两行完整，未遮挡坐标轴；物流设施独立着色。 |
| 05_workcenter_bay_heatmap | 105 行、43 列完整；3 个零生产设备的 InterBay 列保留；非零格数字可在原尺寸查看。 |
| 06_bay_equipment_distribution | 三组统计共用 43 Bay 横轴，柱顶数量没有裁切；INTERBAY 为独立灰色。 |
| 07_bay_directed_network | 43 个 Bay 节点与有向衔接可见；标签未严重覆盖；节点位置是 Rail 端点中位值。 |
| 08_topology_and_stockers | STOCKER、汇入/分流节点及抽样高介数点符号可辨；明确标注没有测量拥堵。 |
| 09_equipment_density_grid | 热度、比例、坐标与轨道叠加正常；颜色条注明固定网格内设备坐标点数。 |
| 10_equipment_anchor_points | 以原始坐标点代替矩形，完整保留工艺类别与物流设施，便于对照锚点歧义。 |
| selected_workcenters/01_DE_FE_86 及 detail | 149 台、6 Bay 的全厂高亮与 A12 局部图可读；局部标注部分 ECH 实例。 |
| selected_workcenters/02_LithoTrack_FE_95 及 detail | 47 台、3 Bay 的高亮与 B7 局部图正常。 |
| selected_workcenters/03_DE_BE_66 及 detail | 21 台、2 Bay 的高亮与 A4 局部图正常。 |
| selected_workcenters/04_TF_BE_40 及 detail | 21 台、2 Bay 的高亮与 B13 局部图正常。 |
| selected_workcenters/05_Diffusion_FE_94 及 detail | A20 的 13 台与 B19 的 1 台清晰分离；A20 局部标注部分 DIF 实例。 |

所有平面布局图均使用等比例 X/Y 坐标。热力矩阵及柱状统计图的横纵轴是类别/数量，不属于物理空间比例图。

20 张 PNG 的尺寸和非空检查见 independent_checks.json，对应 SVG 均存在。主要全厂图 5700×3240，局部图 2700×3300，完整热力图 5400×7500。

保留的限制：源坐标与尺寸按中心约定存在 533 对矩形相交；这不是绘图时随意移动可解决的问题，没有通过缩小矩形、平移设备或删除实例来隐藏。坐标单位及锚点尚未确认，不将矩形解释为经过安装校验的真实设备占地。曲线没有精确几何，不将虚线解释为真实轨道形状。Bay 没有真实边界，图中未伪造多边形边界。

浏览器实际检查包含筛选、高亮、图层开关、定位、选中设备端口、缩放和平移。页面错误/警告日志为空。受自动化浏览器协议限制，file:// 直接打开未获测试；同一内嵌全部数据和脚本的 HTML 已通过本地 HTTP 打开并验证。详情见 browser_checks.json。
