# E3 全局布局-流量联合优化：启发式算法机理（SA + LNS + 内层 LP）

2026.11.05

## 0. 概述

E3 在 E1「固定布局参考 LP」的基础上，把设备在固定槽位上的重新分配作为外层决策，并与工序-设备的
流量分配联合优化。由于完整的「设备配置 × 工序流量」联合 MILP 在全厂规模（1068 台可移动设备、
约 3866 道工序、120 万+ 运输弧）下不可解，E3 采用**两阶段分解启发式**：

1. **外层**（组合优化）：模拟退火（SA）+ 大邻域搜索（LNS），在固定槽位间重新分配设备；
2. **内层**（线性规划）：周期性求解 E1 的流量 LP，刷新设备间流量并给出真实运输成本。

其核心思想是把「难解的外层组合问题」与「易解（但昂贵）的内层 LP」通过一个**代理成本**耦合：
外层搜索在冻结流量 $F$ 下用增量方式快速评估布局变化，内层 LP 周期性地校正该代理。

本文使用与 `methodology_v1.md` 一致的记号，并针对当前 `scripts/e3_heuristic.py` /
`e3_warmstart.py` 的实现给出精确的数学描述。

---

## 1. 问题定义与记号

### 1.1 集合与索引

- $E=\{1,\dots,n\}$：可移动设备集合，$n=1068$。
- $S=\{1,\dots,n\}$：固定槽位集合。每个槽位 $s$ 携带**固定的端口与轨道连接**，因而到任意其他槽位
  的有向轨道最短距离是固定的。
- $\mathcal G=\{G_1,\dots,G_m\}$：设备尺寸类（footprint class）划分，$G_k\subseteq E$ 为宽×高
  （四舍五入到 0.1）相同的设备集合，且 $|G_k|\ge 2$。
- $O$：工序集合；每道工序 $o\in O$ 有需求 $q_o$、兼容设备集 $E_o\subseteq E$、单位加工机时 $\tau_o$。
- $\mathcal T=\{(o,o')\}$：相邻工序对（transition）。$o'$ 为 $o$ 在同产品工艺路线中的下一道工序
  （`Delay_32` 等延迟节点跳过）。

### 1.2 距离

- 有向轨道图 $G=(V,A,w)$，节点为轨道 `Address`，有向边为 `Rail`，边权为曼哈顿（或欧氏）长度。
- 槽位对距离矩阵 $D\in\mathbb R^{n\times n}$：$D_{st}$ 为槽位 $s$ 到槽位 $t$ 的**有向**轨道最短距离，
  通过 Dijkstra 预计算一次：

  $$
  D_{st}=\operatorname{dist}_{G}\big(u(s), u(t)\big)
  $$

  其中 $u(s)$ 为槽位 $s$ 的代表端口在轨道上的接入节点。有向性来自轨道网络的方向约束（$D_{st}\ne D_{ts}$）。

### 1.3 决策变量

- **布局变量**：分配 $\sigma:E\to S$ 为双射，$\sigma_e$ 表示设备 $e$ 被放置到的槽位。
  由于设备只能在**同尺寸类**槽位间交换，$\sigma$ 需满足

  $$
  \sigma_e \in S_{G(e)} \triangleq \{s\in S:\ s\ \text{与设备}\ e\ \text{同尺寸}\}
  $$

  其中 $G(e)$ 为设备 $e$ 的尺寸类。可行域记为 $\Sigma_{\mathcal G}$。

- **流量变量**（内层 LP）：$y_{o,e}\ge 0$（工序 $o$ 在设备 $e$ 上加工的 lot 数）、
  $f_{o,e,e'}\ge 0$（相邻工序对 $(o,o')\in\mathcal T$ 中，从设备 $e$ 运往 $e'$ 的 lot 数）。

---

## 2. 内层流量 LP（固定布局）

给定分配 $\sigma$，设备对距离为 $\tilde D_{ee'}=D_{\sigma_e,\sigma_{e'}}$。E1 的流量 LP 为

$$
C^*(\sigma)=\min_{y,f}
\sum_{(o,o')\in\mathcal T}\ \sum_{e\in E_o}\ \sum_{e'\in E_{o'}}
D_{\sigma_e,\sigma_{e'}}\, f_{o,e,e'}
\tag{LP}
$$

约束：

1. **需求守恒**（每道工序的总加工量等于其需求）：

   $$
   \sum_{e\in E_o} y_{o,e}=q_o,\qquad \forall o\in O .
   $$

2. **出站流量守恒**（工序 $o$ 在设备 $e$ 的加工量全部流向下一工序的某台设备）：

   $$
   \sum_{e'\in E_{o'}} f_{o,e,e'}=y_{o,e},\qquad \forall (o,o')\in\mathcal T,\ e\in E_o .
   $$

3. **进站流量守恒**（工序 $o'$ 在设备 $e'$ 接收的流量等于其加工量）：

   $$
   \sum_{e\in E_o} f_{o,e,e'}=y_{o',e'},\qquad \forall (o,o')\in\mathcal T,\ e'\in E_{o'} .
   $$

4. **设备产能**（有效机时上界）：

   $$
   \sum_{o:\,e\in E_o}\tau_o\, y_{o,e}\le H\,\eta,\qquad \forall e\in E ,
   $$

   其中 $H$ 为规划周期（默认 10080 分钟），$\eta$ 为有效机时系数（默认 0.85）。

5. 非负性 $y\ge 0,\ f\ge 0$。

由解聚合得到设备间 From–To 流量：

$$
F_{ee'}=\sum_{(o,o')\in\mathcal T} f_{o,e,e'},\qquad e,e'\in E .
$$

**弧稀疏化（top-k）**：为控制规模，对每个源设备 $e$ 仅保留距离最近的 $k$ 个目标设备（$k$ 默认 12），
并对每个目标设备额外保留最近的 $k$ 个源设备以保证流量平衡可行；$k=0$ 表示保留全部有限弧。
记稀疏化后的目标为 $\hat C^*(\sigma)$。

---

## 3. 外层优化问题与代理成本

外层问题为

$$
\min_{\sigma\in\Sigma_{\mathcal G}}\ \hat C^*(\sigma) .
$$

由于每次评估 $\hat C^*(\sigma)$ 需求解一次大规模 LP（约 128 万变量 / 17 万约束，HiGHS 冷求解 62–115 秒），
外层不直接使用 $\hat C^*$，而使用**冻结流量下的代理成本**：

$$
C_F(\sigma)=\sum_{e,e'\in E} F_{ee'}\, D_{\sigma_e,\sigma_{e'}} .
$$

其中 $F$ 为最近一次内层 LP 解出的聚合流量（初始值来自 E1 的 `transport_flow.csv`）。当 $\sigma$ 变化时，
$C_F$ 只涉及距离矩阵的查表，可增量快速计算。内层 LP 周期性刷新 $F$ 与真实成本 $\hat C^*$，把代理重新拉回真实口径。

---

## 4. 模拟退火（SA）

### 4.1 邻域：同尺寸交换（transposition）

给定 $\sigma$，随机选择同一尺寸类 $G_k$ 中的两台设备 $i,j$，交换其槽位，得到

$$
\sigma'=\sigma\circ(i\,j),\qquad
\sigma'_i=\sigma_j,\ \sigma'_j=\sigma_i,\ \sigma'_e=\sigma_e\ (e\notin\{i,j\}) .
$$

该邻域保证每次移动后 $\sigma'\in\Sigma_{\mathcal G}$（同尺寸类内交换保持尺寸兼容性）。

### 4.2 增量成本 $\Delta_{ij}$ 的推导

代理成本的改变量为

$$
\Delta_{ij}(\sigma)=C_F(\sigma')-C_F(\sigma) .
$$

直接按 (6) 计算为 $O(|E|^2)$。利用 $F$ 的稀疏性可降至 $O(\deg(i)+\deg(j))$。定义

$$
N^+_e=\{e':F_{e,e'}>0\},\qquad
N^-_e=\{e':F_{e',e}>0\} .
$$

交换后只有以 $i$ 或 $j$ 为源/目标的项发生改变，逐项展开：

$$
\begin{aligned}
\Delta_{ij}(\sigma)
={}&
\sum_{e'\in N^+_i\setminus\{j\}} F_{i,e'}\big(D_{\sigma_j,\sigma_{e'}}-D_{\sigma_i,\sigma_{e'}}\big)
+\sum_{e'\in N^-_i\setminus\{j\}} F_{e',i}\big(D_{\sigma_{e'},\sigma_j}-D_{\sigma_{e'},\sigma_i}\big)\\[1mm]
&+\sum_{e'\in N^+_j\setminus\{i\}} F_{j,e'}\big(D_{\sigma_i,\sigma_{e'}}-D_{\sigma_j,\sigma_{e'}}\big)
+\sum_{e'\in N^-_j\setminus\{i\}} F_{e',j}\big(D_{\sigma_{e'},\sigma_i}-D_{\sigma_{e'},\sigma_j}\big)\\[1mm]
&+F_{ij}\big(D_{\sigma_j,\sigma_i}-D_{\sigma_i,\sigma_j}\big)
+F_{ji}\big(D_{\sigma_i,\sigma_j}-D_{\sigma_j,\sigma_i}\big) .
\end{aligned}
$$

前三行分别对应「以 $i$ 为源 / 以 $i$ 为目标 / 以 $j$ 为源 / 以 $j$ 为目标」的弧，最后两行处理
$i\leftrightarrow j$ 的直连弧（注意有向距离 $D_{st}\ne D_{ts}$，故两项不能抵消）。这正是
`delta_swap` 的实现。

### 4.3 Metropolis 接受准则

对移动 $\Delta$，接受概率为

$$
P_{\text{acc}}(\Delta;T)=
\begin{cases}
1, & \Delta\le 0,\\[2mm]
\exp\!\left(-\dfrac{\Delta}{T}\right), & \Delta>0 .
\end{cases}
$$

即：改进移动必接受，劣化移动以随温度衰减的概率接受，从而允许跳出局部最优。

### 4.4 初温估计与温度调度

初温取随机采样交换增量绝对值均值的 10 倍：

$$
T_0=\max\!\Big(10\cdot\frac{1}{m}\sum_{k=1}^{m}|\Delta^{(k)}|,\ 1\Big),\qquad m=100 .
$$

温度按几何方式退火：

$$
T_{r+1}=\alpha\, T_r,\qquad \alpha=0.95 ,
$$

当 $T<T_{\min}$（默认 $10^{-3}$）时终止。搜索共 $\text{max\_epochs}\times\text{iter\_per\_epoch}$
次移动（默认 $100\times200=2\times10^4$）。

---

## 5. 大邻域搜索（LNS）

以概率 $p_{\text{lns}}$（默认 0.15）执行 LNS 破坏-修复移动，用于跳出 SA 单步交换难以跨越的深谷：

1. **破坏**：随机选择一个尺寸类 $G_k$，从其中随机抽取 $k_0=\max\big(2,\ \lfloor 0.5\,|G_k|\rfloor\big)$
   台设备，记其槽位集合 $S_0=\{\sigma_e:e\in D_0\}$；
2. **修复**：将 $S_0$ 随机打乱后重新分配给 $D_0$，得到 $\sigma'$。

由于 LNS 一次改变多台设备，其成本改变无法用 $O(\deg)$ 增量表达，故直接用 (6) 全量重算：

$$
\Delta_{\text{lns}}=C_F(\sigma')-C_F(\sigma) .
$$

该移动同样经 Metropolis 准则（4.3）接受。

---

## 6. 内层 LP 刷新与 warm-start

### 6.1 刷新策略

每累计接受 $K$ 次移动（`--lp-every`，默认 10），调用内层 LP 以当前 $\sigma$ 重解，得到新的
聚合流量 $F$ 与真实成本 $\hat C^*(\sigma)$，并据此更新代理成本口径与历史最优。

### 6.2 结构固定性与 warm-start

关键观察：LP (2)–(5) 的**约束矩阵只依赖 $(O,E,\text{弧集})$，与 $\sigma$ 无关**；$\sigma$ 仅通过
$D_{\sigma_e,\sigma_{e'}}$ 进入**目标系数**，并通过 top-k 进入**选弧**。因此：

1. **冻结弧集**（以 $k=0$ 全弧集或固定 $k$ 一次性确定），约束结构在搜索全程不变；
2. 交换 $(i,j)$ 后，只有**以 $i$ 或 $j$ 为源/目标的弧**的目标系数发生改变：

   $$
   \tilde D_{ee'}=D_{\sigma_e,\sigma_{e'}}\ \text{在}\ e\notin\{i,j\}\ \text{且}\ e'\notin\{i,j\}\ \text{时保持不变} .
   $$

据此，`e3_warmstart.py` 用 `highspy` 维护一个**持久化 HiGHS 模型**（`presolve=off` + 对偶单纯形）：
每次刷新仅对受影响弧调用 `changeColsCost` 更新目标系数，再 `run()` 从上一轮的基（basis）做对偶单纯形
再优化，避免每轮重建 17 万约束、百万级变量的 LP 并冷求解。实测单次内层 LP 刷新由冷求解的 62–115 秒
降至约 15–18 秒。

---

## 7. 完整算法

```
输入: E, S, O, T, 距离矩阵 D, E1 初始流量 F_0, 参数集
输出: 最优分配 σ*, 成本 Ĉ*(σ*)

1. 预计算 D（有向轨道图 Dijkstra）
2. F ← F_0；构建出/入邻接 N^+, N^-
3. 划分尺寸类 G
4. σ ← identity；C ← C_F(σ)；σ* ← σ；C* ← C
5. 估算 T_0；T ← T_0
6. 若 warm-start：构建持久化 HiGHS 模型（冻结弧集）
7. for epoch = 1 .. max_epochs:
8.     for it = 1 .. iter_per_epoch:
9.         with prob p_lns: (σ', Δ) ← LNS_shuffle(σ)      # 全量重算
10.        else:            (i,j) ← 同尺寸随机对
11.                          (σ', Δ) ← 交换 + delta_swap   # O(deg) 增量
12.        if Δ ≤ 0 or random() < exp(-Δ/T):              # Metropolis
13.            σ ← σ'; C ← C + Δ; accept += 1
14.            if C < C*: σ* ← σ; C* ← C
15.        if accept ≥ K:                                  # 内层 LP 刷新
16.            (F, Ĉ) ← 求解内层 LP(σ)                     # warm-start 或冷求解
17.            C ← Ĉ；更新 N^+, N^-；accept ← 0
18.            if C < C*: σ* ← σ; C* ← C
19.    T ← α·T
20.    if T < T_min: break
21. 对 σ* 做最终精确 LP（k=0）得到 Ĉ*(σ*)
22. 输出 layout.csv 与 e3_summary.json
```

---

## 8. 复杂度分析

| 阶段 | 复杂度 |
|---|---|
| 距离矩阵预计算（Dijkstra） | $O\big(|V|\,(|A|+|V|\log|V|)\big)$，一次 |
| `delta_swap` 增量 | $O(\deg(i)+\deg(j))$，单次移动约微秒级 |
| `lns_shuffle` | $O(|\operatorname{supp}(F)|)$，全量重算 |
| 内层 LP 构建 | $O(\text{变量数}+\text{弧数})$，约 4 秒 |
| 内层 LP 求解（HiGHS） | 冷求解约 62–115 秒；warm-start 约 15–18 秒 |
| 外层主循环 | 约 $6\times10^3$ 次移动/秒（纯增量路径） |

**瓶颈**：内层 LP 求解占绝对主导。搜索 2 万次移动中，外层增量运算仅约 3 秒，而内层 LP 按默认
`lp_every=10` 会触发约 500+ 次求解，累计数小时，因此 warm-start 是性能关键。

---

## 9. 参数一览（默认值）

| 参数 | 默认 | 含义 |
|---|---|---|
| `--horizon-min` | 10080 | 规划周期（分钟） |
| `--demand-scale` | 0.25 | 需求缩放系数 |
| `--utilization` | 0.85 | 有效机时系数 $\eta$ |
| `--top-k` | 12 | 内层 LP 弧稀疏化 $k$（0 = 全弧） |
| `--max-epochs` | 100 | 退火外循环数 |
| `--iter-per-epoch` | 200 | 每轮移动数 |
| `--alpha` | 0.95 | 退火降温系数 |
| `--t-min` | 1e-3 | 终止温度 |
| `--lp-every` | 10 | 每 $K$ 次接受移动刷新内层 LP |
| `--lns-prob` | 0.15 | LNS 移动概率 |
| `--lp-time-limit` | 120 | 内层 LP 时间上限（秒） |
| `--warm-start` | on | 持久化 HiGHS warm-start（`--no-warm-start` 回退冷求解） |

---

## 10. 假设与局限

1. **槽位固定**：$S$ 为 SMAT2022 参考布局中 1068 个可移动设备位置，每个槽位的端口与轨道连接固定，
   设备仅在这些槽位间重分配，不新增/删除槽位。
2. **同尺寸交换**：移动邻域仅在宽×高相同的设备间交换，保证几何与端口兼容。
3. **代理-校正分解**：外层用冻结流量 $F$ 的代理成本 (6) 指导搜索，真实成本由内层 LP 周期性校正；
   两次刷新之间代理与真实口径存在偏差。
4. **top-k 弧稀疏化**：内层 LP 仅保留最近 $k$ 个目标（+ 每个目标最近 $k$ 个源），是近似；
   最终精确 LP 用 $k=0$ 复核。
5. **确定性静态流量**：内层 LP 为聚合确定性流量，不含故障、换型、排队与车辆冲突（与 E1 口径一致）。
6. **启发式非精确**：SA + LNS 不保证全局最优，也不提供最优性间隙；质量依赖随机种子与参数。
7. **成本口径**：最终成本为「流量 × 有向轨道最短距离」，$F$ 来自内层 LP；参考成本用 E1 初始流量在
   恒等分配下按 (6) 计算。
