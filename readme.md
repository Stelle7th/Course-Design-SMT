# 半导体晶圆厂布局优化（SMT2020 + SMAT2022）

基于 SMT2020 生产数据与 SMAT2022 自动物料搬运系统（AMHS）数据，对半导体晶圆厂进行
**设备布局优化**研究。整体流程为：**数据审计（E0）→ 参考布局 LP（E1）→ MILP 布局优化（E2）→ 全局启发式（E3）**。

---

## 1. 配置需求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows / Linux / macOS |
| Python | ≥ 3.10 |
| 依赖包 | numpy、scipy、openpyxl、highspy（可选 cupy-cuda12x） |

安装依赖（等价于 `requirements.txt`）：

```powershell
pip install numpy scipy openpyxl highspy
```

> 说明：
> - `scipy.optimize.milp`（HiGHS 混合整数求解器）需要 scipy ≥ 1.9；
> - `scipy.optimize.linprog(method="highs")` 与 `scipy.sparse.csgraph.dijkstra` 由 scipy 提供；
> - `openpyxl` 仅 E0 读取 SMAT2022 的 Excel 工作簿时使用；
> - `highspy` 用于 E3 的持久化 warm-start 内层 LP；未安装时 E3 会自动回退到 scipy 冷求解（不影响正确性）；
> - `cupy-cuda12x` 可选，仅用于 `gpu_distance.py` 的 GPU 距离矩阵加速（需 NVIDIA GPU + CUDA）。

---

## 2. 目录结构

```
week6/
├── data/                 # 输入数据（SMT2020_* 生产数据 + SMAT2022 Excel）
├── docs/                 # 数据集说明、实验方案、方法论文档
├── scripts/              # 全部可执行脚本（E0 / E1 / E2 / E3）
├── output/               # 运行产物（审计、LP、布局优化结果）
├── 汇报准备/ 汇报成稿/    # 汇报相关材料
└── README.md
```

`scripts/` 下的脚本：

| 脚本 | 阶段 | 说明 |
|---|---|---|
| `e0_data_audit.py` | E0 | 数据审计（映射、轨道、端口、设备几何） |
| `e1_reference_lp.py` | E1 | 固定布局参考 LP（最小化运输成本） |
| `e1_visualize.py` | E1 | E1 结果交互式可视化 |
| `e2_common.py` | E2 | 共享工具（读 E0/E1 输出、流量聚合） |
| `e2_bay_ordering.py` | E2-L1 | Bay 沿主干道排序（1D QAP MILP） |
| `e2_bay_layout.py` | E2-L2 | Bay 内设备重排（连续 FLP MILP） |
| `e2_optimize.py` | E2 | 编排 L1+L2、成本对比、报告 |
| `e2_visualize.py` | E2 | 优化前后布局对比可视化 |
| `e3_heuristic.py` | E3 | 全局布局-流量联合启发式（模拟退火 SA + LNS + 内层 LP） |
| `e3_warmstart.py` | E3 | 持久化 HiGHS warm-start 内层 LP（被 `e3_heuristic.py` 调用） |
| `gpu_distance.py` | 工具 | CuPy GPU 设备距离矩阵（可选，无 GPU 时回退 CPU） |

---

## 3. 运行说明

所有命令均在项目根目录（`week6/`）下执行，使用 `--help` 可查看完整参数。

### 3.1 数据准备

确保 `data/` 目录包含：

- `data/SMT2020_LVHM/`（或 `SMT2020_HVLM/`）：制表符分隔的 `.txt` 生产数据；
- `data/SMAT2022/General Data/dataset 4/SMAT_2022_Model_Data_-_LVHM_E.xlsx`：AMHS 工作簿。

### 3.2 E0 数据审计

```powershell
python scripts/e0_data_audit.py --production-model LVHM --output-dir output/e0_audit
```

产物：`tool_mapping.csv`、`equipment_mapping.csv`、`port_audit.csv`、`rail_summary.json`、`audit_report.md` 等。

### 3.3 E1 参考布局 LP

```powershell
python scripts/e1_reference_lp.py --production-model LVHM --output-dir output/e1_reference_lp
python scripts/e1_visualize.py --e1-dir output/e1_reference_lp
```

关键参数：`--horizon-min`（规划周期，默认 10080 分钟）、`--demand-scale`（需求缩放，默认 0.25）、
`--utilization`（有效机时系数，默认 0.85）、`--top-k`（运输弧稀疏化，默认 12，0 表示全部）、
`--edge-length-mode`（`manhattan`/`euclidean`）。

产物：`transport_flow.csv`、`from_to_bay.csv`、`operation_flow.csv`、`device_utilization.csv`、`e1_report.md` 等。

### 3.4 E2 MILP 布局优化

```powershell
# 完整运行（L1 Bay 排序 + L2 Bay 内布局 + 报告）
python scripts/e2_optimize.py --e1-dir output/e1_reference_lp --e0-dir output/e0_audit --output-dir output/e2_layout

# 仅 L1：Bay 排序
python scripts/e2_bay_ordering.py --e1-dir output/e1_reference_lp

# 仅 L2：Bay 内设备重排
python scripts/e2_bay_layout.py --e1-dir output/e1_reference_lp --e0-dir output/e0_audit

# 生成优化前后对比图
python scripts/e2_visualize.py --e1-dir output/e1_reference_lp --e2-dir output/e2_layout
```

关键参数：`--l1-time-limit-sec` / `--l2-time-limit-sec`（求解时限，默认 30/60 秒）、`--skip-l1`（跳过 L1）。

产物：`new_layout.csv`（优化后设备坐标）、`bay_order.json`/`bay_order.txt`、`e2_summary.json`、`e2_report.md`。

> 依赖关系：E2 读取 E1 的 `transport_flow.csv`、`from_to_bay.csv`、`selected_equipment_ports.csv`
> 与 E0 的 `equipment_mapping.csv`，因此 **E2 前需先运行 E0 和 E1**。

### 3.5 E3 全局启发式（warm-start + SA/LNS）

启动命令（warm-start + 启发式，推荐默认）：

```powershell
# 首次使用先创建虚拟环境并安装依赖
# Linux/macOS:  python3 -m venv .venv && source .venv/bin/activate
# Windows:      python -m venv .venv && .venv\Scripts\activate
# pip install -r requirements.txt

python scripts/e3_heuristic.py --production-model LVHM --output-dir output/e3_global --warm-start
```

在 E1 的固定流量基准上，把「设备 → 槽位」的重新分配作为外层搜索，内层周期性重解 E1 的流量 LP，
实现布局与流量的联合优化。外层为**模拟退火（SA）+ 大邻域搜索（LNS）**，内层 LP 默认使用
**持久化 HiGHS warm-start**（`--warm-start`，推荐）；`--no-warm-start` 回退到 `scipy` 冷求解。

关键参数：`--max-epochs`（默认 100）、`--iter-per-epoch`（默认 200）、`--lp-every`（每 K 次接受移动刷新一次内层 LP，默认 10）、
`--top-k`（内层 LP 弧稀疏化，默认 12）、`--lp-time-limit`（默认 120 秒）、`--lns-prob`（LNS 移动概率，默认 0.15）、
`--warm-start` / `--no-warm-start`（是否使用持久化 HiGHS warm-start 内层 LP）。

> 说明：
> - `--warm-start`（默认）用 `e3_warmstart.py` 的持久化 HiGHS 模型（`presolve=off` + 对偶单纯形 +
>   稀疏目标系数更新），内层 LP 刷新从冷求解的 62–115 秒降到约 15–18 秒；`--no-warm-start` 回退到
>   `scipy.optimize.linprog` 冷求解，结果一致但更慢；
> - 未安装 `highspy` 时，即使指定 `--warm-start` 也会自动回退到冷求解；
> - E3 依赖 E1 的 `transport_flow.csv` 作为初始流量，因此 **E3 前需先运行 E1**。

产物：`layout.csv`（设备新槽位坐标）、`e3_summary.json`（参考/优化成本与降幅、移动设备数等）。

---

## 4. 原理简述

### 4.1 数据与关联

- **SMT2020**：产品（`part.txt`）、工艺路线（`route_*.txt`）、订单（`order.txt`）、设备族（`tool.txt.1l`）等，提供生产流量；
- **SMAT2022**：设备实例（`Equipment`）、轨道节点（`Address`）、有向轨道（`Rail`）、端口（`Port`）、
  OHT 车辆（`Vehicle`）等，提供厂房几何与 AMHS 拓扑。

两者通过 `route.STNFAM → tool.STN → Equipment.TOOL_GROUP → Port → Rail → Address` 关联，
E0 负责审计这条映射链（含别名归一化，如 `DefMEt_FE_118 → DefMet_FE_118`）与轨道/端口引用完整性。

### 4.2 E1 —— 固定布局参考 LP

设备位置固定，仅优化确定性的聚合加工与运输流量。决策变量为工序-设备分配流量 `y_{o,e}` 与设备间运输流量 `f_{s,t}`：

\[
\min \sum_{(s,t)} d_{s,t}\, f_{s,t}
\]

约束：① 需求守恒 `Σ_e y_{o,e} = D_p`；② 相邻工序流量守恒（出流 = 工序加工量，入流 = 下一工序加工量）；
③ 设备产能 `Σ_o y_{o,e} τ_o ≤ horizon × utilization`。其中 `d_{s,t}` 由有向轨道图上的 Dijkstra
最短路径计算。用 `scipy.optimize.linprog(method="highs")` 求解，作为后续布局优化的流量基准。

### 4.3 E2 —— MILP 布局优化（分层）

在 E1 的固定流量 `F` 下，将设备位置本身作为决策变量，最小化 `Σ F·d`。由于全厂一次性建模规模不可解，
利用半导体厂天然的 **spine（Interbay 主干道）+ Bay（Intrabay）** 结构分为两层：

- **L1（Bay 排序，1D QAP MILP）**：将 40 个 Intrabay 沿主干道赋予互不相同的整数位置，目标
  `min Σ F_{b,b'}·|pos_b − pos_{b'}|`。变量为整数位置 `pos`、顺序二元变量 `z` 与距离线性化变量 `u`。

- **L2（Bay 内设备重排，连续 FLP MILP）**：每台设备用连续坐标 `(cx, cy)` 表示，约束在 Bay 包围盒内；
  每对设备用 4 个二元分离方向变量实现非重叠，曼哈顿距离经绝对值线性化，目标
  `min Σ F_{e,e'}·(|Δx| + |Δy|)`。用 `scipy.optimize.milp`（HiGHS）求解。

E2 得到的新坐标后，可重新映射轨道、重算距离并回代 E1，形成「流量 ↔ 布局」的交替优化（本仓库当前
交付固定流量下的单次 E2；完整交替迭代为后续扩展）。

> 距离说明：E1 使用有向轨道图最短路径作为真实搬运距离；E2 阶段使用设备中心曼哈顿距离作为布局代理，
> 最终效果应回到 E1 的轨道距离口径下复核。

### 4.4 E3 —— 全局布局-流量联合启发式（SA + LNS + warm-start LP）

E2 在**固定流量**下优化布局，E3 进一步把布局与流量联合起来：外层在固定槽位上重新分配设备，内层周期性重解
E1 的流量 LP 来刷新流量与真实运输成本。

- **外层（SA + LNS）**：设备只能在**同尺寸（宽×高）槽位**间交换。`delta_swap` 用 O(出度) 增量求单次交换的成本变化；
  `lns_shuffle` 按概率对某一尺寸类做局部洗牌破坏-修复。接受准则为标准模拟退火 Metropolis 准则。
- **内层 LP（warm-start）**：每 `lp_every` 次接受移动重解一次流量 LP。由于 LP 的约束结构只依赖固定的工序/设备与
  冻结的运输弧集、设备距离只进入**目标系数**，因此可用 `highspy` 持久化模型：交换后仅用 `changeColsCost` 更新
  受影响弧的目标系数并热求解（`presolve=off` + 对偶单纯形），避免每次重建 170k 约束、百万级变量的 LP 再冷求解。

> 性能说明：内层 LP 是 E3 的绝对瓶颈（单次冷求解 62–115 秒）。warm-start 把每次刷新降到约 15–18 秒；
> 距离矩阵本身仅 0.15 秒、外层搜索约 6000 iter/s，均非瓶颈，也因 SA 串行、单步延迟型运算而不适合 GPU。

---

## 5. 输出文件索引

| 阶段 | 关键输出 | 内容 |
|---|---|---|
| E0 | `equipment_mapping.csv` | 设备实例的映射、固定/可移动分类与几何 |
| E1 | `transport_flow.csv` | 设备间运输流量（E2 的输入） |
| E1 | `from_to_bay.csv` | Bay 间流量（E2-L1 的输入） |
| E2 | `new_layout.csv` | 优化后的设备坐标 |
| E2 | `bay_order.json` / `bay_order.txt` | Bay 排序建议 |
| E2 | `e2_summary.json` / `e2_report.md` | 成本对比与各 Bay 求解状态 |
| E3 | `layout.csv` | 设备重新分配后的槽位坐标 |
| E3 | `e3_summary.json` | 参考/优化成本、降幅、移动设备数与求解统计 |
