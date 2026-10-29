# SMAT2022 原始布局可视化与分析报告

生成日期：2026-10-15（Asia/Shanghai）。项目根目录：`F:\Grade4\课程设计`。

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

旧项目中已下载文件位于 `C:\Users\HP\.codex\.chatgpt-projects\g-p-6aae3af666cc8191ae33dfecc4757614\analysis\a2_audit/smat2022/`；本次原样复制到 `F:\Grade4\课程设计\analysis\a2_audit\smat2022`，未重新下载，也未修改原件。
读取文件：

- `analysis/a2_audit/smat2022/SMAT_2022_Model_Data_-_LVHM_E.xlsx`，SHA256 `8e74e6db2272ad7dbeeb26de2adb1cd69e27a7848fe7baa0524803fd317156c0`。
- `analysis/a2_audit/smat2022/A2_SMAT_group_mapping.csv`：沿用原 105 组映射。
- `analysis/a2_audit/核查结论与实施方案.md`、`SMT2020_LVHM_group_inventory.csv`。
- `analysis/a2_audit/smat2022/SMAT_2022_generic.txt`、`SMAT_2022_PINOKIO_documentation.txt`、`README.md`、`download_manifest.json`。

复用此前 `analysis/a2_audit/audit_smat.py` 的 OOXML `workbook_rows` 解析器，重新读取 XLSX，非仅依赖旧 CSV。已有代码只有审计及映射逻辑，没有可复用的布局绘图器。源文件复制校验及下载清单中四个文件的 SHA256 均核对通过。完整路径、大小和散列见 `validation/source_manifest.json`。

## 3. 数据完整性与映射复核

| 工作表 | 数据行数 |
| --- | --- |
| Address | 2858 |
| ZCU | 734 |
| Rail | 3424 |
| Bay | 43 |
| Equipment | 1116 |
| PortType | 6 |
| Port | 22120 |
| VehicleType | 1 |
| Vehicle | 500 |

全部表 NAME 唯一。Rail 起终节点、Rail.BAY_NAME、Equipment.BAY、Port 的轨道/类型/非空设备引用、Vehicle 的轨道/类型引用及 Address.ZCU_NAME 引用通过检查。设备几何数值有限，宽高为正。

Equipment：1068 个生产实例、40 STOCKER、4 COMMIT、4 COMPLETE。40 INTRABAY 每个均有一个 STOCKER；3 INTERBAY 是运输通道记录，不是 3 个新增生产区。

只在派生表中应用 `DefMet_FE_118 → DefMEt_FE_118`。105 个生产 STNFAM、11 个 STNGRP 全部匹配，未映射生产设备为 0，空清单仍保存在 `tables/unmapped_equipment.csv`。
矩阵总和、逐组设备数、逐组 Bay 集合与原映射 CSV 一致；32 个工作中心跨 Bay，142 个非零（STNFAM，Bay）组合，最大跨 6 Bay，与前次核查完全一致。

| area | 设备数 |
| --- | --- |
| Def_Met | 17 |
| Dielectric | 67 |
| Diffusion | 75 |
| Dry_Etch | 393 |
| Implant | 36 |
| Litho | 188 |
| Litho_Met | 57 |
| Planar | 33 |
| TF | 93 |
| TF_Met | 5 |
| Wet_Etch | 104 |

A2 LVHM 的 913 个资源与 SMAT 的 1068 个生产实例存在数量差异。此次绘制全部 1068 台，没有替换为 A2 的数量或改变映射基准。

## 4. 几何与坐标解释

### 坐标单位、方向和矩形锚点

文档明确 VehicleType.MAX_SPEED 为 mm/s，加减速度为 mm/s²，但没有逐列明确 Equipment/Address 坐标和 WIDTH/HEIGHT 的单位。此前报告的“先按 mm 整理”是情景约定，不能升级成已证实事实。本次保留原始单位，坐标轴除以 1000 便于阅读，未标为 m 或 mm。所有平面布局图的 X/Y 均保持等比例。

采用数学坐标方向：X 向右、Y 向上，没有翻转源数据。源模拟器是否使用屏幕向下的 Y 轴没有被本地说明确认，因此此图不声称复现模拟器屏幕朝向。

源文件没有设备坐标锚点、旋转或机台维护空间说明。为绘制 WIDTH×HEIGHT 矩形，本次明确暂定 POSITION_X/Y 为中心；交互和派生表保留原坐标，并标识 `rectangle_anchor_assumption=center_unconfirmed`。
几何诊断如下（按轴对齐矩形内部相交，不含恰好接触）：

| convention | overlapping_rectangle_pairs |
| --- | --- |
| center | 533 |
| lower_left | 521 |

中心约定产生 533 对矩形内部相交，左下角约定产生 521 对。图 10 以原始坐标点给出不依赖矩形锚点的替代分布。诊断不是锚点定义的证明，也不能将相交直接解释成真实设备碰撞。任何重叠不应静默修复，更不能据此改动真实坐标。布局优化前必须确认锚点、维护空间与可交换机台的占地规则，当前不能声称已建立无重叠且可安装的槽位基准。

### Bay 的空间信息

Bay 表只有类型、RETICLE、NEIGHBOR_BAY，没有多边形边界。图中标签基于归属 Rail 端点的中位位置及两排设备的留白位置；没有绘制“真实 Bay 边界”。设备包络面积仅是按中心假设的矩形外包围面积，用于相对密度描述；不是洁净室可用面积、装机容量或真实 Bay 面积。

### 轨道与 Port

Rail 按 FROM_NODE→TO_NODE 构建有向图。2473 条 CURVE=0 使用端点直线；951 条 CURVE=1 仅用金色虚线连接端点。虚线不是恢复的弧线，`endpoint_chord_raw` 只是端点弦长，曲线的 `straight_length_raw` 留空。不以弦长替代曲线长度计算旅行时间。

Port 分类：

| PORT_TYPE | has_equipment | records |
| --- | --- | --- |
| COMMIT | True | 4 |
| COMPLETE | True | 4 |
| EQPPort | True | 4352 |
| LSTB | False | 5920 |
| RSTB | False | 5920 |
| UTB | False | 5920 |

有 Equipment 引用的端口共 4360 条（1068×4 + 40×2 + 8）；其余 17760 条为无单台 Equipment 引用的 LSTB/RSTB/UTB 记录，EQP_NAME 的逗号占位符视为无引用。不能将 22120 行解释为独立机台装卸站。

每台生产设备 4 Port，每 STOCKER 2 Port，每 COMMIT/COMPLETE 1 Port。对直线 Rail，按起点加单位方向乘 DISTANCE 推导 Port/Vehicle 位置；超过直线长度 1 原始单位的记录为 0。DISTANCE 的取整误差被保留，未强制截断。曲线上的 Port/Vehicle 坐标留空，原始 Rail+DISTANCE 仍保存。没有伪造精确曲线端口位置。HTML 默认不绘制全部端口，点击设备可查看该设备端口及可推导坐标。

500 辆 Vehicle 初始 Rail 引用全部有效，500 个可由直线恢复位置，0 个因曲线几何不足不绘制精确位置。全量记录见 `tables/vehicle_initial_positions.csv`。

## 5. 主要空间特征

全厂呈两排狭长 INTRABAY：A1–A20 位于较高 Y 区域，B1–B20 位于较低 Y 区域，三个 INTERBAY 连接两排内外侧通道。生产设备沿 Bay 的长向分布。不同工艺类大体形成连续区域，但工作中心与 Bay 并非一一对应。

生产设备原始坐标 X 范围 1458.426–298869.306，Y 范围 8125.005–133958.419。轨道端点的 X 范围 0.000–300327.953，Y 范围 -5580.357–147247.024。

73 个工作中心仅在一个 Bay，32 个跨 Bay。一个工作中心用单一空间点表示会损失设备位置、端口与源/目标设备选择。空间跨度只代表坐标离散程度，不是运输距离。

更细的分布为：73 组涉及 1 Bay，30 组涉及 2 Bay，1 组涉及 3 Bay，1 组涉及 6 Bay。生产实例数最多的 7 个 Bay 为 A11、A12、A19、A20、B4、B5、B6，均为 40 台。

五个代表工作中心及最大设备坐标点距：

| STNFAM | area | equipment_count | bay_count | bays | max_anchor_distance_raw |
| --- | --- | --- | --- | --- | --- |
| DE_FE_86 | Dry_Etch | 149 | 6 | A11|A12|A13|A14|A15|A16 | 92477.2857 |
| LithoTrack_FE_95 | Litho | 47 | 3 | B7|B8|B9 | 61245.0988 |
| DE_BE_66 | Dry_Etch | 21 | 2 | A4|A5 | 56730.1155 |
| TF_BE_40 | TF | 21 | 2 | B12|B13 | 56474.0998 |
| Diffusion_FE_94 | Diffusion | 14 | 2 | A20|B19 | 53573.3295 |

代表图在 `figures/selected_workcenters/`：每个工作中心有全厂高亮图和一个设备较多 Bay 的等比例局部图，局部图标注部分设备名。当前示例为 DE_FE_86, LithoTrack_FE_95, DE_BE_66, TF_BE_40, Diffusion_FE_94。选择规则为排序前 3 组、薄膜代表 TF_BE_40 和唯一跨 A/B 两排的 Diffusion_FE_94，以覆盖不同空间模式；没有以优化收益作为选择依据。

Bay 设备类型复杂度最高的区域：

| Bay | production_count | workcenter_count | rail_count |
| --- | --- | --- | --- |
| A16 | 27 | 9 | 40 |
| A19 | 40 | 7 | 40 |
| B19 | 26 | 7 | 40 |
| B15 | 22 | 7 | 40 |
| A20 | 40 | 6 | 37 |
| A18 | 30 | 6 | 40 |
| A7 | 24 | 6 | 40 |
| B20 | 22 | 6 | 37 |

按设备包络面积归一化的相对密集 Bay（分母不是真实 Bay 面积）：

| Bay | production_count | count_per_1e8_envelope_raw2 |
| --- | --- | --- |
| A11 | 40 | 5.5919 |
| A19 | 40 | 5.5919 |
| A20 | 40 | 5.5919 |
| A12 | 40 | 5.5919 |
| B4 | 40 | 5.5919 |

另有固定 10000×10000 原始单位网格计数图/表，避免把包络面积当真实生产面积。密度结论依赖网格尺度；这是机台空间计数，不是利用率。

40 个 STOCKER 均按原坐标绘制，每 INTRABAY 一处。对生产设备坐标点计算最近 STOCKER 的欧氏距离，中位数 29352.841，最大 58127.511 原始单位；565/1068 台设备最近 STOCKER 与其 Bay 相同。欧氏最近不代表沿有向轨道最快，也不证明库存容量或储存策略合理。全量邻近关系见 `tables/equipment_nearest_stocker.csv`。

## 6. Bay 运输连接与拓扑诊断

Address 有向图强连通分量为 [2858]，2858 个节点在同一个 SCC。忽略车辆、ZCU 控制、等待与端口服务约束时，全图拓扑可达。

Bay 连接规则：若 Rail r 的 TO_NODE 与 Rail s 的 FROM_NODE 是同一 Address，且 r.BAY_NAME≠s.BAY_NAME，则记 r 所属 Bay→s 所属 Bay 的有向衔接。它是两个原始轨道标签之间的过渡，不是任意空间邻近关系。每条边有 incoming_rail、outgoing_rail、shared_node 的可追溯证据，见 `tables/bay_transition_witnesses.csv`。共得到 236 对有向 Bay 直接衔接，43×42=1806 个不同 Bay 的有序对均有拓扑路径。

可达性还由完整 Address 图单一 SCC 独立验证，避免 Bay 聚合图因丢失内部连续性产生虚假可达。生产设备端口均有关联轨道，且 PortType.INOUT_TYPE 有明确方向；因此轨道层面具有连接基础，但不据此保证服务调度可执行。

NEIGHBOR_BAY 是另一种原始邻接描述，不能直接当有向轨道边。其 160 条声明中 156 条对应上述直接轨道衔接。差异保留在 `tables/declared_neighbor_comparison.csv`，不强行覆盖 Rail 推导关系。

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
