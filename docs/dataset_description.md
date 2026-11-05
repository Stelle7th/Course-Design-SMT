# SMT2020 / SMAT2022 数据集说明

版本：1.0  
整理日期：2026-10-22

本文档根据当前 `data` 目录中的文件整理，说明数据文件的组织方式、主要字段和文件之间的关系。字段含义优先采用数据集 README、`SMAT_2022_generic.docx` 和字段样例；仅根据字段名推断的内容会标注为“待确认”。

## 1. 数据集组成

当前目录包含两类数据：

1. `SMT2020_HVLM` 和 `SMT2020_LVHM`：晶圆制造生产系统数据，采用制表符分隔的文本文件；
2. `SMAT2022`：在 SMT2020 基础上增加 AMHS 的厂房、设备、轨道、端口和车辆数据，主要存储在 Excel 文件中。

SMT2020 提供产品、工艺路线、设备工艺族、订单、在制品、故障和维护等生产信息。SMAT2022 提供工厂空间和自动物料搬运系统信息。两者通过产品路线、工艺设备族、设备组和设备实例建立关联。

当前选用的 SMAT2022 文件为：

```text
data/SMAT2022/General Data/dataset 4/SMAT_2022_Model_Data_-_LVHM_E.xlsx
```

该文件名表明它对应 LVHM_E 模型。当前目录中没有发现其他 SMAT2022 模型 Excel 文件。

## 2. SMT2020 生产数据

### 2.1 两个模型的规模

| 模型 | 产品数 | 路线文件数 | 路线记录数 | 订单记录数 | 工具记录数 | 工具数量合计 | WIP 记录数 |
|---|---:|---:|---:|---:|---:|---:|---:|
| HVLM | 2 | 2 | 926 | 5 | 106 | 1443 | 2255 |
| LVHM | 10 | 10 | 4013 | 21 | 106 | 1313 | 2156 |

工具数量合计来自 `tool.txt.1l` 的 `STNQTY` 求和。它表示 SMT2020 生产模型中的工具数量口径，与 SMAT2022 `Equipment` 中的实际设备实例数量不一定相同。

### 2.2 文件结构

两个 SMT2020 模型目录具有相同的文件类型。LVHM 目录包含 `route_1.txt` 至 `route_10.txt`，HVLM 目录包含 `route_3.txt` 和 `route_4.txt`。

| 文件 | 主要内容 |
|---|---|
| `part.txt` | 产品、产品族与路线文件的映射 |
| `route_*.txt` | 产品工艺路线和每道工序的加工参数 |
| `order.txt` | 订单、到达间隔、优先级和交付时间 |
| `tool.txt.1l` | 设备工艺族、设备实例/数量、设备组和调度属性 |
| `WIP.txt` | 仿真开始时的在制品 |
| `fromto.txt` | 地点之间的运输或转移时间分布 |
| `attach.txt` | 故障或停机日历与资源组的关联 |
| `downcal.txt` | 故障日历中的 MTTF 和 MTTR 参数 |
| `pmcal.txt` | 预防维护周期和维护修复时间 |
| `setup.txt` | 设备从一种设置切换到另一种设置的时间 |
| `setupgrp.txt` | 设置组、允许的设置状态和最小运行条件 |

所有文本文件的第一行是字段名，字段之间使用制表符分隔。部分文件扩展名为 `.txt.1l`，读取时仍应按普通文本表格处理。

## 3. SMT2020 文件字段说明

### 3.1 `part.txt`

典型字段：

| 字段 | 含义 |
|---|---|
| `PARTGRP` | 产品大类或产品组，例如 `Saleable` |
| `PARTFAM` | 产品族，例如 `product_1` |
| `PART` | 产品标识，例如 `part_1` |
| `ROUTEFILE` | 对应的路线文件名 |
| `ROUTE` | 路线标识，例如 `r_1` |

关联关系：

```text
PART -> ROUTEFILE -> ROUTE -> route_*.txt
```

### 3.2 `route_*.txt`

每一行表示路线中的一道工序。主要字段如下：

| 字段 | 含义 |
|---|---|
| `ROUTE` | 路线标识 |
| `STEP` | 工序序号 |
| `DESC` | 工序描述或工序名称 |
| `STNFAM` | 执行该工序的设备工艺族/设备族 |
| `PDIST` | 加工时间的分布类型，例如 `uniform` |
| `PTIME` | 加工时间参数 |
| `PTIME2` | 加工时间的第二个参数 |
| `PTUNITS` | 加工时间单位，当前样例主要为 `min` |
| `PTPER` | 加工时间的计量口径，例如 `per_lot`、`per_piece`、`per_batch` |
| `BATCHMN` | 批处理最小数量 |
| `BATCHMX` | 批处理最大数量 |
| `SETUP` | 相关设置或换型标识 |
| `WHEN` | 设置或条件触发条件，具体规则待确认 |
| `STIME` | 设置时间或附加时间 |
| `STUNITS` | 设置时间单位 |
| `SVESTN` | 相关设备或前序设备信息，具体语义待确认 |
| `FORSTEP` | 与其他工序的关联信息，具体语义待确认 |
| `BatchInterval` | 批处理间隔 |
| `BatchIntUnits` | 批处理间隔单位 |
| `PartInterval` | 单片或单件处理间隔 |
| `PartIntUnits` | 单片或单件间隔单位 |
| `RWKSTEP` | 返工相关工序 |
| `REWORK` | 返工目标或返工参数 |
| `RWKTYPE` | 返工类型 |
| `StepPercent` | 工序比例或相关概率，具体语义待确认 |
| `STEP_CQT` | 工序级周期时间参数 |
| `CQT` | 周期时间参数 |
| `CQTUNITS` | 周期时间单位 |
| `IGNORE` | 关联的工艺族、日历或忽略标识 |

`PTIME` 不能脱离 `PTPER` 使用。对于布局流量模型，需要先将不同计量口径换算为统一的 lot 流量或设备占用时间。

当前数据中存在 `per_batch` 和返工字段，因此将路线直接视为简单线性工序链会丢失部分生产语义。若第一阶段暂时采用线性主路线，应在实验记录中明确忽略了哪些返工和批处理动态。

### 3.3 `order.txt`

| 字段 | 含义 |
|---|---|
| `LOT` | 订单或批次标识 |
| `PART` | 产品标识 |
| `PRIOR` | 订单优先级 |
| `PIECES` | 每个 lot 的片数或件数，当前样例为 25 |
| `START` | 订单开始时间 |
| `RDIST` | 到达间隔分布类型，例如 `constant` |
| `REPEAT` | 重复到达间隔数值，当前样例通常以分钟为单位 |
| `RUNITS` | `REPEAT` 的时间单位 |
| `RPT#` | 重复次数或订单重复规模，具体是否表示总到达次数需结合原始仿真器确认 |
| `LOTSPERRPT` | 每次重复产生的 lot 数量 |
| `DUE` | 订单交付时间 |
| `ORDER` | 订单标识 |
| `HOTLOT` | 是否为 hot lot |

`RPT#` 的精确语义目前待确认。对于确定性布局流量，建议优先使用到达率：

\[
\lambda_p=\sum_{o\in O_p}\frac{LOTSPERRPT_o}{REPEAT_o}
\]

而不是直接把 `RPT#` 当作一个规划周期内的需求量。

### 3.4 `tool.txt.1l`

该文件描述生产设备族及其调度属性。

| 字段 | 含义 |
|---|---|
| `STNFAM` | 设备族/设备工艺族 |
| `STN` | 设备站点或设备类型标识 |
| `RULE` | 调度规则 |
| `FWLRANK` | 正向生产队列排序规则 |
| `WAKERESRANK` | 唤醒资源排序规则 |
| `BATCHCRITF` | 批处理判定条件 |
| `BATCHPER` | 批处理周期或相关参数 |
| `LTIME` | 装载、卸载或等待时间参数 |
| `LTUNITS` | `LTIME` 单位 |
| `ULTIME` | 另一类装卸或处理时间参数 |
| `ULTUNITS` | `ULTIME` 单位 |
| `STNCAP` | 设备能力参数，当前多数为空或需结合仿真器解释 |
| `STNQTY` | SMT2020 模型中的设备数量 |
| `STNGRP` | 设备大组，例如 `Diffusion`、`Dry_Etch` |
| `STNFAMSTEP_ACTLIST` | 设备执行工序时使用的活动列表 |
| `STNFAMLOC` | 设备所在位置，当前样例主要为 `Fab` |
| `PRERULERWL` | 前置规则或前置返工限制 |
| `SETUPGRP` | 设置组标识 |

布局研究中建议使用 `STN`/`STNFAM` 作为细粒度设备类型，因为不同具体设备族的尺寸、加工能力和工艺适用范围可能不同；`STNGRP` 适合用于汇总分析。

### 3.5 `WIP.txt`

| 字段 | 含义 |
|---|---|
| `LOT` | 在制品批次标识 |
| `PART` | 产品标识 |
| `PRIOR` | 优先级 |
| `PIECES` | 批次中的片数或件数 |
| `START` | 进入系统的时间 |
| `CURSTEP` | 当前所在工序编号 |
| `DUE` | 交付时间 |
| `ORDER` | 对应订单 |
| `HOTLOT` | hot lot 标识 |
| `TRACE` | 追踪信息 |

`WIP.txt` 适合用于离散事件仿真初始状态。若布局模型只使用稳态聚合流量，可以暂不使用 WIP，但应说明这一点。

### 3.6 `fromto.txt`

典型字段：

| 字段 | 含义 |
|---|---|
| `FROMLOC` | 起点位置 |
| `TOLOC` | 终点位置 |
| `DDIST` | 运输时间分布类型 |
| `DTIME` | 运输时间参数 |
| `DTIME2` | 运输时间第二参数 |
| `DUNITS` | 运输时间单位 |

当前数据中出现 `Fab -> Fab` 的记录。`DTIME` 和 `DTIME2` 在不同分布下可能分别表示固定值、均值/上界或分布参数，精确含义待原始 SMT2020 格式说明确认。

### 3.7 `attach.txt` 与 `downcal.txt`

`attach.txt` 将故障日历关联到资源组：

| 字段 | 含义 |
|---|---|
| `CALNAME` | 日历名称 |
| `CALTYPE` | 日历类型 |
| `RESTYPE` | 资源类型 |
| `RESNAME` | 资源组名称 |
| `FOADIST` | 故障发生或首次发生时间的分布 |
| `FOA` | 故障发生参数 |
| `FOAUNITS` | 参数单位 |

`downcal.txt` 定义故障和维修参数：

| 字段 | 含义 |
|---|---|
| `DOWNCALNAME` | 故障日历名称 |
| `DOWNCALTYPE` | 故障日历类型 |
| `MTTFDIST` | 平均故障间隔时间分布 |
| `MTTF` | 平均故障间隔时间参数 |
| `MTTFUNITS` | MTTF 单位 |
| `MTTRDIST` | 平均修复时间分布 |
| `MTTR` | 平均修复时间参数 |
| `MTTRUNITS` | MTTR 单位 |
| `IGNORE` | 关联资源组或忽略标识 |

当前研究的确定性布局模型暂不使用这些随机故障参数。后续进行仿真验证时，应将它们恢复到设备状态模型中。

### 3.8 `pmcal.txt`

该文件描述预防维护日历。

| 字段 | 含义 |
|---|---|
| `PMCALNAME` | 预防维护日历名称 |
| `PMCALTYPE` | 日历类型 |
| `MTBPM` | 平均预防维护间隔 |
| `MTBPMUNITS` | 维护间隔单位 |
| `MTTRDIST` | 预防维护修复时间分布 |
| `MTTR` | 维护修复时间参数 |
| `MTTR2` | 修复时间第二参数 |
| `MTTRUNITS` | 修复时间单位 |
| `IGNORE` | 关联资源组或忽略标识 |

### 3.9 `setup.txt` 与 `setupgrp.txt`

`setup.txt` 描述设备从当前设置切换到新设置的时间：

| 字段 | 含义 |
|---|---|
| `CURSETUP` | 当前设置 |
| `NEWSETUP` | 新设置 |
| `STIME` | 设置时间 |
| `STUNITS` | 设置时间单位 |
| `IGNORE` | 关联设备族或忽略标识 |

`setupgrp.txt` 描述设置组：

| 字段 | 含义 |
|---|---|
| `SETUPGRP` | 设置组名称 |
| `SETUP` | 允许的设置状态 |
| `MINRUN` | 最小连续运行量或最小运行条件 |
| `IGNORE` | 关联设备族或忽略标识 |

这些文件对考虑换型成本、批次合并和调度策略很重要，但不进入当前静态布局 LP 的基础版本。

## 4. SMAT2022 Excel 数据

### 4.1 工作表总览

当前 `SMAT_2022_Model_Data_-_LVHM_E.xlsx` 包含以下 9 个工作表：

| 工作表 | 数据行数 | 主要用途 |
|---|---:|---|
| `Address` | 2858 | OHT 轨道节点及节点坐标 |
| `ZCU` | 734 | Zone Control Unit |
| `Rail` | 3424 | OHT 轨道有向连接 |
| `Bay` | 43 | Bay 类型、邻接关系和 reticle 属性 |
| `Equipment` | 1116 | 设备实例、设备组、Bay、尺寸和坐标 |
| `PortType` | 6 | 端口类型 |
| `Port` | 22120 | 端口与设备/轨道的连接关系 |
| `VehicleType` | 1 | OHT 车辆类型参数 |
| `Vehicle` | 500 | OHT 车辆初始位置 |

原始 README 中提到“八个 additional sheets”，但当前 Excel 实际包含上述九个 AMHS 相关工作表，数量表述存在不一致。

### 4.2 `Address`

| 字段 | 含义 |
|---|---|
| `NAME` | 轨道节点名称 |
| `FAB_NAME` | 工厂名称 |
| `POSITION_X` | 节点 X 坐标 |
| `POSITION_Y` | 节点 Y 坐标 |
| `ZCU_NAME` | 连接的 ZCU 名称 |
| `ZCU_TYPE` | ZCU 节点类型，例如 `STOP`、`RESET`、`NONE` |

`POSITION_X` 和 `POSITION_Y` 用于建立轨道几何。坐标单位没有在当前通用格式文档中明确说明；结合设备尺寸和车辆参数，可能是毫米，但实现前应统一核对。

### 4.3 `ZCU`

| 字段 | 含义 |
|---|---|
| `NAME` | ZCU 名称 |
| `FAB_NAME` | 工厂名称 |

ZCU 用于描述轨道交叉点或区域控制关系。当前研究只计算静态最短路径时，可以将其作为轨道拓扑的附属信息；若模拟车辆冲突和死锁，需要进一步使用 `ZCU_TYPE` 和 ZCU 控制逻辑。

### 4.4 `Rail`

| 字段 | 含义 |
|---|---|
| `NAME` | 轨道边名称 |
| `FAB_NAME` | 工厂名称 |
| `BAY_NAME` | 轨道所在 Bay |
| `FROM_NODE` | 起始节点 |
| `TO_NODE` | 终止节点 |
| `MAX_SPEED` | 轨道最大速度或速度参数 |
| `CURVE` | 是否为弯曲轨道，当前为 0/1 |

`FROM_NODE` 和 `TO_NODE` 表明轨道应按有向图处理，不能默认转换成无向图。`MAX_SPEED` 的单位和 `CURVE` 对路径长度的具体影响需要进一步确认。若只计算距离，轨道边长度应根据两端节点坐标或专门的曲线长度计算。

### 4.5 `Bay`

| 字段 | 含义 |
|---|---|
| `NAME` | Bay 名称 |
| `FAB_NAME` | 工厂名称 |
| `TYPE` | Bay 类型，当前有 `INTRABAY` 和 `INTERBAY` |
| `RETICLE` | 是否为 reticle Bay，当前为 0/1 |
| `NEIGHBOR_BAY` | 邻接 Bay 名称列表，以逗号分隔 |

当前文件包含 40 个 Intrabay 和 3 个 InterBay。`NEIGHBOR_BAY` 是文本列表，使用时需要拆分并与 Bay 名称表校验。

### 4.6 `Equipment`

| 字段 | 含义 |
|---|---|
| `NAME` | 设备实例名称 |
| `TOOL_GROUP` | 设备所属工艺组或设备组 |
| `BAY` | 设备所在 Bay |
| `WIDTH` | 设备宽度 |
| `HEIGHT` | 设备长度或高度字段，二维布局中通常视为另一平面尺寸 |
| `POSITION_X` | 设备 X 坐标 |
| `POSITION_Y` | 设备 Y 坐标 |

当前文件共有 1116 台设备。`TOOL_GROUP` 与 SMT2020 `tool.txt.1l` 的 `STN` 大部分可以直接匹配，但存在别名和 AMHS 专用设备组。设备尺寸和坐标单位需要与 `Address` 坐标统一，当前文档暂按同一平面坐标系处理。

### 4.7 `PortType`

| 字段 | 含义 |
|---|---|
| `NAME` | 端口类型名称 |
| `SIZE` | 端口尺寸 |
| `INOUT_TYPE` | 端口方向类型，例如 `IN`、`OUT`、`BOTH` |

当前数据中包括 `COMMIT`、`COMPLETE`、`EQPPort`、`LSTB`、`RSTB`、`UTB` 等端口类型。`SIZE` 的单位和是否代表端口物理长度待确认。

### 4.8 `Port`

| 字段 | 含义 |
|---|---|
| `NAME` | 端口名称 |
| `FAB_NAME` | 工厂名称 |
| `PORT_TYPE` | 端口类型，对应 `PortType.NAME` |
| `EQP_NAME` | 连接的设备实例 |
| `RAILLINE_NAME` | 连接的轨道边 |
| `DISTANCE` | 端口在轨道边上的位置 |

`Port` 将设备与轨道连接起来，是从设备代表点计算实际搬运路径的重要数据。当前数据中有些 `EQP_NAME` 值为逗号或空值，这些记录可能是 Bay 侧、轨道侧或未绑定设备的公共端口，具体语义待确认。

### 4.9 `VehicleType`

| 字段 | 含义 |
|---|---|
| `NAME` | 车辆类型名称 |
| `SIZE` | 车辆尺寸 |
| `MAX_SPEED` | 最大速度 |
| `ACCELERATION` | 加速度 |
| `DECELERATION` | 减速度 |
| `MIN_DISTANCE` | 车辆最小安全间距 |

通用格式文档明确 `MAX_SPEED`、`ACCELERATION` 和 `DECELERATION` 的单位为毫米/秒或毫米/秒²。`SIZE` 和 `MIN_DISTANCE` 的单位应与轨道坐标保持一致。

### 4.10 `Vehicle`

| 字段 | 含义 |
|---|---|
| `NAME` | 车辆实例名称 |
| `FAB_NAME` | 工厂名称 |
| `TYPE` | 车辆类型，对应 `VehicleType.NAME` |
| `RAILLINE_NAME` | 车辆初始所在轨道边 |
| `DISTANCE` | 车辆在轨道边上的初始位置 |

该表描述仿真开始时的车辆初始状态。静态布局距离模型通常不需要使用它；动态 AMHS 仿真需要使用它。

## 5. 数据之间的关联

### 5.1 生产数据内部关联

```text
part.txt
  -> PART / ROUTEFILE / ROUTE
  -> route_*.txt
  -> STNFAM
  -> tool.txt.1l.STNFAM / STN
```

订单和 WIP 通过 `PART` 与产品路线关联：

```text
order.txt.PART -> part.txt.PART
WIP.txt.PART   -> part.txt.PART
```

### 5.2 生产数据与 SMAT2022 关联

主要关联链为：

```text
route_*.txt.STNFAM
  -> tool.txt.1l.STN 或 STNFAM
  -> SMAT2022.Equipment.TOOL_GROUP
  -> Equipment.NAME
  -> Port.EQP_NAME
  -> Port.RAILLINE_NAME
  -> Rail.NAME
  -> Rail.FROM_NODE / TO_NODE
  -> Address.POSITION_X / POSITION_Y
```

当前已发现的名称问题：

| 类型 | 内容 |
|---|---|
| 拼写差异 | `DefMEt_FE_118` 与 `DefMet_FE_118` |
| 生产数据中未使用 | `Delay1` |
| 仅出现在 SMAT2022 | `COMMIT`、`COMPLETE`、`STOCKER` |
| 端口未绑定设备 | `Port.EQP_NAME` 为空或为逗号 |

这些情况不能直接静默丢弃，应在数据预处理阶段输出映射审计表。

## 6. 面向布局研究的建议数据处理

### 6.1 设备数量

如果研究对象是 SMAT2022 当前厂房的固定设备布局，设备数量应使用 `Equipment` 中的实际设备实例计数。`tool.txt.1l.STNQTY` 可作为 SMT2020 生产模型的参考数量，但不应在没有校验的情况下覆盖 SMAT2022 的设备实例数量。

### 6.2 工艺兼容性

可以使用路线中的 `STNFAM` 建立工序与设备族的兼容关系：

\[
G_{ps}=\{g:\text{设备类型 }g\text{ 能够执行产品 }p\text{ 的工序 }s\}
\]

若一条路线只给出一个 `STNFAM`，则第一版模型可以将该设备族视为该工序的唯一兼容设备族。若存在替代设备族，需要从 SMT2020 工具和路线规则中进一步解析。

### 6.3 加工时间

建议先统一为每 lot 的设备占用时间：

- `per_lot`：直接使用 `PTIME`；
- `per_piece`：乘以 `PIECES`；
- `per_batch`：按确定的代表批量换算；
- `PTIME2`：只有在确认其统计意义后才使用。

### 6.4 搬运距离

建议使用：

1. `Equipment` 或 `Port` 确定设备代表点；
2. `Port.RAILLINE_NAME` 将代表点映射到轨道边；
3. `Rail` 和 `Address` 建立有向轨道图；
4. 使用最短可行轨道路径计算距离。

不能仅使用设备中心之间的欧氏距离替代轨道路径，除非作为单独的简化对照实验。

## 7. 尚未完全确认的内容

以下事项当前无法仅凭 `data` 目录中的字段和样例完全确认：

1. 所有坐标、设备尺寸、端口尺寸和轨道 `DISTANCE` 字段的精确单位；
2. `order.txt.RPT#` 的确切语义；
3. `fromto.txt` 中 `DTIME` 与 `DTIME2` 在不同分布下的具体含义；
4. `route_*.txt` 中 `SVESTN`、`FORSTEP`、`StepPercent` 和 `CQT` 的完整语义；
5. `attach.txt` 中 `FOA` 的确切统计含义；
6. `tool.txt.1l` 中 `STNCAP`、`LTIME` 和 `ULTIME` 是否参与设备能力计算；
7. `Rail.MAX_SPEED` 是否为真实速度、归一化速度还是仿真器内部参数；
8. `Rail.CURVE=1` 时轨道实际长度的计算方式；
9. `Port.EQP_NAME` 为空或为逗号的端口所属对象；
10. SMT2020 的 `STNQTY` 与 SMAT2022 设备实例数量差异的来源；
11. 参考图片中的通道和几何边界是否有对应的机器可读数据。

在这些内容确认前，建议将相关参数作为显式实验假设，并在结果中进行敏感性分析。
