# E0 数据审计报告

生成时间（UTC）：2026-10-22T00:37:48.072047+00:00

生产模型：`E:\code_index\course_design\v1_1021\data\SMT2020_HVLM`  
SMAT2022 文件：`E:\code_index\course_design\v1_1021\data\SMAT2022\General Data\dataset 4\SMAT_2022_Model_Data_-_LVHM_E.xlsx`

## 审计结论

总体状态：**通过**

- [x] all_route_stnfam_mapped
- [x] all_movable_equipment_mapped
- [x] all_rail_endpoints_exist
- [x] all_rail_coordinates_present
- [x] all_equipment_has_port
- [x] all_equipment_geometry_present
- [x] all_port_rail_references_exist
- [x] all_port_distances_numeric
- [x] all_port_types_exist
- [x] all_equipment_bays_exist

## 数据规模

| 类别 | 数量 |
|---|---:|
| SMT2020 产品记录 | 2 |
| SMT2020 订单记录 | 5 |
| SMT2020 工具记录 | 106 |
| SMT2020 WIP 记录 | 2255 |
| SMT2020 路线记录 | 926 |
| SMAT2022 设备实例 | 1116 |
| 可移动工艺设备 | 1068 |
| 固定 AMHS 设备 | 48 |
| SMAT2022 端口记录 | 22120 |
| SMAT2022 轨道边 | 3424 |
| SMAT2022 轨道节点 | 2858 |
| SMAT2022 Bay | 43 |

## 映射结果

SMT2020 路线中的 `STNFAM`、SMT2020 工具表中的 `STN` 与 SMAT2022 的 `TOOL_GROUP` 已进行显式匹配。已知别名 `DefMEt_FE_118 -> DefMet_FE_118` 已应用。

未映射且不属于固定 AMHS 设备的 SMAT2022 设备组：

无

固定 AMHS 组：`STOCKER`、`COMMIT`、`COMPLETE`。完整结果见 `tool_mapping.csv`、`equipment_mapping.csv` 和 `route_coverage.csv`。

## 路线检查

- 路线文件数：2
- 路线记录数：926
- `PTPER` 分布：`{'per_batch': 28, 'per_piece': 408, 'per_lot': 490}`
- 含批处理边界的记录：28
- 含返工字段的记录：14
- 缺少 `PTIME` 的记录：0
- 识别为非设备延迟/等待节点：`Delay_32`

## 轨道和端口检查

- 轨道端点缺失：起点 0，终点 0
- 轨道边缺少端点坐标：0
- 轨道弱连通分量：1
- 最大弱连通分量节点数：2858
- 含曲线标记的轨道边：951
- 没有端口的设备：0
- 缺少几何字段的设备：0
- 端口引用不存在设备：0
- 端口引用不存在轨道：0
- 端口距离非数值记录：0
- 未知端口类型记录：0

`rail_summary.json` 中保存了端点、连通分量、边长度统计和样本可达性结果。边长度仅用于 E0 数据检查，正式路径矩阵仍应根据研究方案定义的轨道长度规则生成。

## 输出文件

- `audit_summary.json`：机器可读的总审计结果和关键检查状态；
- `tool_mapping.csv`：SMT2020 工具族与 SMAT2022 设备组映射；
- `route_coverage.csv`：路线 `STNFAM` 到 SMT2020 工具类型的覆盖情况；
- `equipment_mapping.csv`：每个 SMAT2022 设备实例的映射和固定/可移动分类；
- `port_audit.csv`：端口、设备引用和轨道引用检查；
- `equipment_port_audit.csv`：每个设备实例的端口覆盖情况；
- `rail_summary.json`：轨道图拓扑和坐标检查；
- `audit_report.md`：本报告。
