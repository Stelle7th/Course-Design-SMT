# SMAT2022 原始布局成果入口

所有内容位于当前项目 `F:/Grade4/课程设计/analysis/smat_layout_viz/`。这是原始布局解析与可视化成果，没有运行布局优化或运输仿真。

- [完整分析报告](SMAT原始布局可视化与分析报告.md)
- [交互式布局查看器](interactive/smat_layout_viewer.html)
- [完整设备布局 PNG](figures/01_equipment_layout.png)
- [完整轨道网络 PNG](figures/02_rail_network.png)
- [设备与轨道叠加 PNG](figures/03_equipment_rail_overlay.png)
- [11 类工艺分布 PNG](figures/04_tool_group_layout.png)
- [工作中心—Bay 完整热力图 PNG](figures/05_workcenter_bay_heatmap.png)
- [Bay 统计 PNG](figures/06_bay_equipment_distribution.png)
- [Bay 有向连接 PNG](figures/07_bay_directed_network.png)
- [拓扑与 STOCKER PNG](figures/08_topology_and_stockers.png)
- [设备密度 PNG](figures/09_equipment_density_grid.png)
- [原始坐标点对照 PNG](figures/10_equipment_anchor_points.png)

每张图均有同名 SVG。`figures/selected_workcenters/` 另有 5 个工作中心的全厂高亮与局部实例图，共 10 张。总计 20 张 PNG + 20 张 SVG。

## 统计数据

- [1116 个设备实例的坐标、尺寸、STNFAM 与工艺分类](tables/equipment_position_summary.csv)
- [105×43 工作中心—Bay 数量矩阵](tables/workcenter_bay_matrix.csv)
- [142 个非零工作中心—Bay 组合](tables/workcenter_bay_detail.csv)
- [105 个工作中心跨 Bay 与空间跨度](tables/workcenter_distribution_summary.csv)
- [43 Bay 的生产设备、工作中心与轨道统计](tables/bay_equipment_summary.csv)
- [有向 Bay 衔接及证据](tables/bay_transition_witnesses.csv)
- [Bay 连接汇总](tables/bay_connection_summary.csv)
- [22120 个 Port 的引用与直线推导位置](tables/port_position_detail.csv)
- [500 辆车初始位置](tables/vehicle_initial_positions.csv)

共有 21 张派生 CSV 与 `tables/raw/` 下本次从原始 XLSX 重读导出的 9 张快照表。所有 CSV 为带 BOM 的 UTF-8，便于 Excel 打开。几何长度保留原始单位。

## 运行与验收

在项目根目录执行：

```powershell
python analysis/smat_layout_viz/scripts/build_layout.py
python analysis/smat_layout_viz/scripts/verify_outputs.py
```

输入副本、原映射、前次报告和复用的 OOXML 解析器位于 `analysis/a2_audit/`。没有修改这些输入。

查看器的全部数据及代码内嵌在 HTML。也可以在项目根目录启动仅绑定本机的 HTTP 服务再访问：

```powershell
python -m http.server 8765 --bind 127.0.0.1 --directory analysis/smat_layout_viz
```

浏览器访问 `http://127.0.0.1:8765/interactive/smat_layout_viewer.html`。

- [189 项构建数据检查](validation/data_checks.json)
- [103 项独立检查，采用 openpyxl 重新读取 XLSX](validation/independent_checks.json)
- [实际视觉检查记录](validation/visual_review.md)
- [13 项浏览器验收记录](validation/browser_checks.json)
- [原始文件来源及 SHA256](validation/source_manifest.json)

坐标单位及矩形锚点没有被源文档明确确认；中心绘制约定产生 533 对矩形相交，已原样保留并提供坐标点对照。曲线 Rail 只提供虚线端点连接示意。拓扑与空间分布事实不能直接当作拥堵测量或可安装槽位约束。
