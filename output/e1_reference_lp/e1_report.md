# E1 参考布局 LP 报告

生成时间：2026-10-22T01:05:07.768805+00:00

## 运行配置

- 生产模型：`E:\code_index\course_design\v1_1021\data\SMT2020_LVHM`
- SMAT2022 文件：`E:\code_index\course_design\v1_1021\data\SMAT2022\General Data\dataset 4\SMAT_2022_Model_Data_-_LVHM_E.xlsx`
- 规划周期：10080.0 分钟
- 需求缩放系数：0.25
- 设备有效机时系数：0.85
- 轨道边长度：`manhattan`
- 每个源设备保留的目标设备数：12（0 表示全部）

## 求解结果

- 求解状态：`0`
- 求解消息：Optimization terminated successfully. (HiGHS Status 7: Optimal)
- 目标值：5803123608.491473
- 变量数：1285408
- 等式约束数：170305
- 不等式约束数：1068
- 运输弧数：1202127

## 可行性检查

- [x] solver_found_feasible_solution
- [x] all_operations_have_positive_demand
- [x] all_operations_have_eligible_equipment
- [x] all_selected_paths_reachable
- [x] order_and_flow_residuals_within_tolerance
- [x] capacity_within_tolerance

- 最大工序需求守恒残差：1.7763568394002505e-15
- 最大设备产能超限：1.8189894035458565e-12
- 最大设备利用率：1.0000000000000002
- 非零工序设备分配数：4028
- 非零运输弧数：4057

## 数据提示

- 路线中的 `Delay_32` 被视为非设备延迟节点，从设备位置和运输弧建模中跳过。
- `per_piece` 按产品的 `PIECES` 转换为每 lot 时间。
- `per_batch` 使用 `(BATCHMN+BATCHMX)/2` 作为代表批量。
- 设备位置使用每台设备选择的 `EQPPort`，若无该类型端口则使用排序后的第一个可用端口。
- `top_k` 会对完整设备对设备运输弧进行稀疏化。若结果不可行，应增加 `top_k` 或在小规模实例使用 `--top-k 0`。
- 本报告中的 LP 只处理确定性聚合流量，不包含故障、换型、排队和车辆冲突。

## 输出文件

- `e1_summary.json`：完整运行配置、求解状态和检查结果；
- `operation_flow.csv`：工序到参考布局设备的加工流量；
- `transport_flow.csv`：相邻工序间的运输流量；
- `from_to_bay.csv`：Bay 间 From-To 流量；
- `bay_flow.csv`：各 Bay 的出发流量；
- `device_utilization.csv`：设备负载和利用率；
- `selected_equipment_ports.csv`：每台设备用于距离计算的代表端口；
- `e1_report.md`：本报告。
