# 半导体制造系统布局与物料运输优化

课程设计 A2 组项目。使用 **SMT2020** 的产品路线、订单和加工参数，以及 **SMAT2022** 的设备位置、尺寸、端口与有向轨道数据，研究设备布局与物料运输的联合优化。

本项目保留截至第六周的代码、数据分析和汇报成果，并在第七周增加 **全厂物流与加工仿真**。当前工作包括数据审计、固定参考布局 LP、两 Bay 局部 MILP 验证，以及 500 辆 OHT 和多工序物料流转的全厂参考运行模型。

## 先看哪些内容

| 入口 | 内容 |
| --- | --- |
| [本周：全厂制造仿真](week7/全厂制造仿真.html) | 全厂运输、加工、排队；点击车辆/设备/物料查看任务、路径和工艺流程 |
| [仿真范围与复现](week7/README.md) | 任务生成、资源规则、时间换算假设与运行命令 |
| [第七周单页汇报](week7/第七周汇报_仿真内容介绍_单页.pptx) | 沿用第六周风格，介绍仿真范围、流程与交互功能，附本地 HTML 链接和讲解备注 |
| [仿真演示建议](week7/汇报演示建议.md) | 全厂、产品、工艺、回流批次及排队特写的演示顺序与具体例子 |
| [MILP 交互展示](week6/汇报成稿/MILP交互展示.html) | 布局前后、设备移动、逐工序收益和实际进出路径 |
| [单页汇报：收益解释版](week6/汇报成稿/两Bay局部优化验证_收益解释版.pptx) | 与前三页汇报样式一致，区分整体和受益工序的改善率，附 HTML 超链接 |
| [两 Bay 边界示意图](week6/汇报成稿/两Bay边界示意图.png) | 优化区域与固定外部供需边界 |
| [求解摘要](week6/汇报准备/MILP_A2_A3/summary.json) | 实验参数、目标值、求解状态、变量规模和最优性 gap |
| [独立检查](week6/汇报准备/MILP_A2_A3/independent_checks.json) | 从保存的结果核对数量、需求、流量、产能与目标值 |
| [原始布局查看器](analysis/smat_layout_viz/interactive/smat_layout_viewer.html) | 未优化的工厂布局、设备组和轨道信息 |

GitHub 文件页展示 HTML 源码；下载或克隆后，用浏览器打开 HTML。页面自带数据，不需要服务端或重新求解。PPT 与 `MILP交互展示.html` 应放在同一文件夹，才能保持本地相对超链接；合并到总汇报后也应保留这一位置关系。

第七周 PPT 与 `全厂制造仿真.html` 同放在 `week7/`，保持同目录即可使用页内演示链接。当前全厂仿真使用 **SMAT2022 原始参考布局**，尚未接入第六周的 MILP 重排位置；产品筛选、配色及路线显示不会改变布局或运行结果。

## 目录结构

```text
.
├── README.md / requirements.txt
├── data/ docs/ scripts/ output/    # 原仓库已有的 E0/E1 数据、方法、代码与结果
├── week5/                         # 第五周汇报材料
├── week6/                         # 第六周静态模型、局部优化与报告
│   ├── data/                     # SMT2020、SMAT2022 数据副本
│   ├── docs/                     # 数据字段、数学方法与实验计划
│   ├── scripts/                  # E0 审计、E1 固定布局 LP 与可视化
│   ├── output/                   # 审计及参考布局 LP 的保存结果
│   ├── 汇报准备/
│   │   ├── scripts/              # 局部 MILP、结果整理和展示构建
│   │   └── MILP_A2_A3/           # 最终局部验证的 CSV、摘要与检查
│   ├── 交互展示/                 # HTML 模板、内嵌数据与逻辑检查记录
│   └── 汇报成稿/                 # PPT、讲稿、示意图与离线 HTML
├── week7/                         # 全厂仿真、交互界面、单页汇报与模型检查
├── analysis/
│   ├── a2_audit/                 # 布局解析输入及数据映射
│   ├── smat_layout_viz/          # 原始布局图、原始表快照和交互查看器
│   └── week6_review/             # 调研提取、探索实验与历史分析
└── A2-数据驱动的半导体制造系统布局与物料搬运调度优化/
                                  # 课题资料和前期调研材料
```

为保留原仓库历史，顶层 `data/docs/scripts/output` 继续存在。以下复现命令统一使用 **`week6/` 中的当前版本**；不要混用顶层结果和 week6 结果。`analysis/week6_review/` 内的探索性实验、早期草稿及旧版 PPT 仅作历史参考，最终结论以 `MILP_A2_A3/` 与收益解释版单页为准。

## 当前模型做了什么

1. **E0 数据审计**：关联 SMT2020 的工序设备族与 SMAT2022 的设备实例，检查端口和轨道引用。
2. **E1 固定布局 LP**：保持设备位置不变，优化连续加工量和运输流量，得到参考布局及局部边界输入。
3. **两 Bay MILP**：使用 A2、A3 的 48 个现有槽位，联合决定设备组配置、工序加工量、进出区域物流量，最小化 `Σ（流量 × 有向轨道最短距离）`。
4. **全厂离散事件仿真**：使用 500 辆 OHT、1,068 台生产设备和 2,156 条初始 WIP，推进 10 类产品的剩余工艺路线。支持产品/工艺筛选、粗线显示与隐藏、分类配色及多种跟踪镜头。

局部实验固定各外部源的供给量、各外部目标的接收量，以及区域承担的各工序加工量；设备组及尺寸类别数量保持不变。设备只能配置到同尺寸、同工艺大类、同 FE/BE 阶段的兼容槽位。轨道和槽位端口不重新设计。

颜色代表设备组，例如 `DE_BE_50` 为后段干法刻蚀设备族。设备组决定加工兼容性，设备移动不改变其类型。当前模型没有强制同组设备聚集；优化后局部混排是给定假设下的候选布局，还需要工程条件核对。

## 两 Bay 验证结果

实验使用 LVHM 数据，规划期 **10080 分钟（7 天）**、需求系数 **0.25**、有效机时系数 **0.85**。需求系数表示原始订单速率在规划期内产生的需求按 25% 缩放，不表示设备利用率为 25%。

| 指标 | 保存结果 |
| --- | ---: |
| 区域 / 设备数 / 设备组数 | A2、A3 / 48 / 4 |
| 区域产品工序数 | 59 |
| 总变量 / 二元配置变量 / 约束数 | 8,296 / 173 / 5,660 |
| 参考局部加权运输距离 | 304,663,194.167 |
| 优化后局部加权运输距离 | 302,889,755.960 |
| 全部 59 道工序合计改善 | **0.582%** |
| DE_BE_50 对应的 18 道受益工序合计改善 | **2.132%** |
| 其余 41 道工序 | 基本不变 |
| 变化槽位 / 主目标最优性 gap | 6 / 0 |

运输目标单位为**原始距离单位·lot**，不是时间或货币。受益工序的优化前成本占局部总成本约 **27.3%**，所以 `27.3% × 2.132% ≈ 0.582%`。这里按成本加权，不能用 `18 / 59` 代替权重，也不能把受益工序的 2.132% 写成整体改善率。

参考布局已优化过加工与物流分配，本次结果是进一步开放局部设备位置调整后的新增收益。主目标 `gap = 0` 表示在求解器数值精度内已求得当前模型的最优解；随后保持最优运输目标并尽量减少变化槽位，得到 6 个槽位调整，而非预先限制最多只能移动 6 台。

HTML 的具体例子为 **part_5 第 169 步**：优化前由 A3 的 ECH0163 加工，优化后由迁入 A2 的 ECH0155 加工。固定上下游设备时，每 lot 的进出总距离从约 **458.620** 降至 **448.778**（千原始距离单位），降低 **2.146%**。入程变长而出程缩短更多，应比较进出总路径。

结果来自 [summary.json](week6/汇报准备/MILP_A2_A3/summary.json)、[设备移动记录](week6/汇报准备/MILP_A2_A3/equipment_relocation.csv)、[独立检查](week6/汇报准备/MILP_A2_A3/independent_checks.json) 和 [展示数据](week6/交互展示/milp-data.json)。

## 环境与复现

### 第七周全厂仿真

仅打开 HTML 或 PPT 无需安装依赖。重新生成模型与页面只需 Python 标准库：

```powershell
python week7/factory/model.py
python week7/factory/build.py
python -m unittest discover -s week7/tests -v
```

可选前端交互检查使用 `week7/package.json` 中的开发依赖，具体命令、模型假设及数据口径见 [第七周说明](week7/README.md)。所有产品共享设备与车队，筛选只改变观察范围；当前没有车辆避碰、轨道互斥或现场标定，不能据此宣称真实交通拥堵或 MILP 运行收益。

### 第六周模型

建议 Python **3.10+**。依赖包括 NumPy、pandas、SciPy、openpyxl、Matplotlib、NetworkX、Pillow；具体下限见 [依赖清单](analysis/smat_layout_viz/scripts/requirements.txt)。MILP 使用 SciPy 的 HiGHS 接口，无需额外商业求解器。Node.js **18+** 仅用于现成 HTML 的 JavaScript 逻辑检查。

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
```

### 1. 数据审计与完整弧参考 LP

```powershell
python week6/scripts/e0_data_audit.py --data-root week6/data --production-model LVHM --output-dir week6/output/e0_audit

python week6/scripts/e1_reference_lp.py --data-root week6/data --production-model LVHM --output-dir week6/output/e1_reference_lp_full --horizon-min 10080 --demand-scale 0.25 --utilization 0.85 --top-k 0 --edge-length-mode manhattan
```

`--top-k 0` 保留完整候选运输弧；脚本默认值为 12，省略此参数会改变实验口径。完整弧模型约有 203 万变量，首次复算需要相应内存和时间；仅查看结果无需运行。

可选生成参考布局展示：

```powershell
python week6/scripts/e1_visualize.py --e1-dir week6/output/e1_reference_lp_full
```

### 2. 两 Bay MILP

```powershell
python "week6/汇报准备/scripts/milp_two_bay.py" --bays A2 A3 --time-limit 90 --gap 0.001
python "week6/汇报准备/scripts/build_milp_figures.py"
```

输入依赖：

- `analysis/smat_layout_viz/tables/raw/*.csv`：原始布局表快照，已随仓库提供。
- `week6/output/e1_reference_lp_full/operation_flow.csv`、`transport_flow.csv`：完整弧参考解，已随仓库提供。
- `week6/data/`：生产路线与设备组数据。

脚本目前将 **LVHM、10080 分钟、0.25 需求系数和 0.85 机时系数**写在代码中；命令行只开放 Bay、时限和目标 gap。修改生产场景时，需要同步重建参考解、区域边界与脚本参数，不能仅换一个需求参数后沿用旧 CSV。

运行会覆盖对应 `MILP_<Bay...>/` 的保存结果；同一最优值可能对应不同设备编号映射或等价布局。随后运行 `build_milp_figures.py`，刷新 `MILP_*` 目录下的独立检查、具体设备移动映射及图表，再重建 HTML，以免混用新布局与旧移动记录。

### 3. 重建离线 HTML 并检查

```powershell
python "week6/汇报准备/scripts/build_interactive_data.py"
node "week6/汇报准备/scripts/check_interactive_page.mjs"
```

构建脚本读取已有结果，不重新求解；它会更新 `week6/交互展示/milp-data.json` 和 `week6/汇报成稿/MILP交互展示.html`。HTML 当前固定展示 A2/A3 案例。检查脚本验证槽位、设备跟随、颜色切换、59 道工序路径和前后成本；这是 **JavaScript/模拟 DOM 逻辑检查，不是实际浏览器渲染验收**。

PPT 成稿可直接使用。`author_*.js` 是原始幻灯片创作会话源码；`finalize_one_slide.mjs`、`link_one_slide.py`、`render_reference.mjs` 等历史制作脚本包含原电脑路径和 Codex 创作环境依赖，不能作为通用命令直接重建 PPT，迁移前需调整路径与工具环境。

## 结论边界

- 本结果用于**固定边界下的两 Bay 局部模型验证**，不代表全厂最优布局或全厂改善率。
- 本例没有正的区域内部直接工序转移流，重点是位置、加工与外部进出物流的耦合。
- 第六周距离结果沿用有向轨道与曼哈顿长度近似，不直接代表动态排队、拥堵、车辆冲突、生产周期或产量改善；第七周另建原始布局的运行基准。
- 未计搬迁成本、停产损失，也未覆盖完整的洁净、公用工程、排气与维护空间约束。
- `gap = 0` 只针对当前数学模型，不代表现场可直接实施。

## 资料与版本整理

SMT2020 提供生产模型，SMAT2022 提供空间布局及搬运设施；字段和映射依据见 [数据说明](week6/docs/dataset_description.md) 与 [SMAT2022 说明](week6/data/SMAT2022/README.md)。原始课题和调研文献保留在资料目录，数据、论文及原始素材的权利归其各自提供方，本仓库未另行授予这些材料的新许可。

本分支保留 week5、week6、week7、analysis、原始课题资料及汇报附件。发布时排除嵌套 Git 元数据、Python/编辑器缓存、临时制作记录与重复压缩包；`新建文件夹/` 经逐文件核对与 week6 中的对应有效文件一致，也不重复提交。源目录中的文件不因此删除。
