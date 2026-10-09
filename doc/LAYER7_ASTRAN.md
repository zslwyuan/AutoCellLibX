# 第 7 层深潜：ASTRAN 如何把晶体管网表变成版图

> 本文是 [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) §7 的完整展开，
> 面向想读懂（或修改）`tools/astran/` 的读者。所有结论都以当前源码为准并给出
> file:line；与指南不一致处以本文为准（指南示例中的 `nwellpos` 已按本文修订）。
> 术语与符号沿用 ASTRAN 源码：`tools/astran/src/autocell2.cpp`（编排与各阶段）、
> `cellnetlst.cpp`（折叠与布局）、`graphrouter.cpp`（布线）、`compaction.cpp`
> （ILP 引擎）、`designmng.cpp`（命令解释器）。

## 0. 全景：问题、契约与数据流

**问题定义**：给一个晶体管级 SPICE 网表（例如 18 管的 COMPLEX1）和一份工艺规则
文件（.rul，约百条最小宽度/间距/包围规则），自动生成一块**DRC 干净、LVS 等价**
的标准单元版图——所有晶体管排进一条固定高度的行里，P 管在上半、N 管在下半，
宽度越小越好。

**为什么是 NP-hard 的组合问题**：晶体管排序不同 ⇒ 扩散区能否共享（相邻两管
源漏相接且网络相同即可合并成一条连续扩散）不同 ⇒ 宽度不同；折叠方式、布线
拥塞又反过来约束排序。ASTRAN 的策略是把问题拆成一串**每个阶段局部可解**的
子问题，这正是 `autoflow` 的全部意义。

**运行契约**（前后端只靠文件）：

```
pySrc/Astran.py 写出  COMPLEX1.run ──► Astran --shell COMPLEX1.run
                                        │
   tech_freePDK45.rul ──┐               ├─► stdout（GUI/CLI 存为 COMPLEX1.Astranlog）
   COMPLEX1.sp ─────────┤               ├─► COMPLEX1.gds
   gurobi_cl.cmd ◄──────┘ ILPmodel.lp / ILPmodel.sol（进程工作目录！）
```

`.run` 脚本逐行解释（`outputs/adder/COMPLEX1.run` 的真实内容，常量定义在
`pySrc/Astran.py:58-63`）：

```tcl
set lpsolve "…/gurobi_cl.cmd"        # compact 阶段外部求解器的命令行
load technology "…/tech_freePDK45.rul"  # ~百条规则进 Rules 表
load netlist "…/COMPLEX1.sp"            # Spice 解析进 Circuit
set rowheight 13                     # 行高 13 个纵向轨道
set grid 0.19 0.19                   # 横/纵制造网格 0.19µm → H=13×0.19=2.47µm
set supplysize 0.26                  # 电源轨总宽 0.26µm（上下各 0.13，与库 abutment 轨一致）
set nwellpos 1.235                   # N 阱下沿 y 坐标 = H/2 → P/N 扩散区等高（见 §2）
set celltemplate "Tapless"           # 阱接触模板：不在单元内放衬底接触（省宽度）
cellgen select COMPLEX1              # 阶段①：展平
cellgen autoflow                     # 阶段②–⑥：calcArea→fold→place→route→compact
export layout COMPLEX1 ./….gds       # 阶段⑦：写 GDS（独立于 autoflow 的命令）
```

**数据流一图**（括号内是承载该阶段结果的数据结构）：

```
.rul → Rules（designmng.cpp）          .sp → Circuit.cells
        │                                    │ CELLGEN SELECT
        │                          CellNetlst（展平后的晶体管数组）
        │ CELLGEN AUTOFLOW（autocell2.cpp:140-169，状态机 checkState 保证顺序）
        ├─ calcArea ─► 几何模板：trackPos[]、nDif/pDif_iniY/endY、nSize/pSize
        ├─ fold     ─► trans[] 增删（宽管→多条腿并联）
        ├─ place    ─► orderingP/orderingN：两排等长序列（P/N 不等长补 GAP）
        ├─ route    ─► GraphRouter：每个图节点的网络归属
        └─ compact  ─► CLayout：每个图形的 Box 坐标（ILP 解出）
EXPORT LAYOUT ─► Gds::generateBox（层号查 Rules、坐标×2、0×0 盒跳过）
stdout "-> Cell Size (W x H): 4.37 x 2.47" ─► .Astranlog（前端读宽度的唯一来源）
```

`autoFlow` 的实际编排（`autocell2.cpp:140-169`）比"六阶段直线"多两层循环：

```
外层 while(1)：                                  # 失败重试循环，conservative 0→4
  内层 while(1)：                                # 轨道数探索，nrTracks 2→3→4
      calcArea(nrTracks, conservative)
      foldTrans()
      placeTrans(快速模式)
      if 预估拥塞可接受（2轨≤6、3轨≤8、4轨无条件）: break
  placeTrans(speculate 模式，3 次尝试取最优)      # autocell2.cpp:158
  route()
  if compact(timeLimit=3600) 成功: break
  else conservative++                            # 收缩扩散区给布线让路，重来
conservative>4 → 抛 AstranError（该单元失败）
```

---

## 1. select：展平层次化网表

入口 `AutoCell::selectCell`（`autocell2.cpp:130-138`）→ `Circuit::getFlattenCell`
（`circuit.cpp:137-163`）。COMPLEX1.sp 内部引用 NAND2X1 等子单元，展平就是
递归地把每个实例的晶体管**拷贝进父级**：

1. 子单元内部的网名加实例名后缀（`net_1` → `net_1_XI3`），避免不同实例的内部
   网撞名（`circuit.cpp:148`）；
2. 子单元端口按实例的端口顺序重命名回父级网络（`:153-154`）——**这就是第 5 层
   "端口顺序影响版图"的物理通道**：端口顺序决定展平后哪根内部网对应哪根外部网；
3. 晶体管改名 `name_inst` 插入父级（`:155-159`）。

⚠️ 坑：子单元端口数与实例端口数不匹配时只打印 ERROR **不抛异常**
（`circuit.cpp:149-152`），会产生静默缺管的网表。目前靠前端的确定性导出
（`spice.py`）保证不会触发。

## 2. calcArea：几何模板——把"行高 13"翻译成所有 y 坐标

入口 `AutoCell::calcArea`（`autocell2.cpp:68-128`）。这一阶段不碰晶体管，只算
出全单元的**几何框架**，后续所有阶段都在这个框架里摆放：

- 网格：`hGrid/vGrid = set grid 值 × 规则缩放`（`:75-76`）；单元高
  `height = rowHeight × vGrid = 13 × 0.19 = 2.47µm`（`:77`）；
- 电源轨半宽 `supWidth = max(supplyVSize, W1M1)/2`（`:79`）；
- **`posNWell` 是 N 阱的下沿**（不是中线！）：N 扩散区上沿必须低于阱沿
  `nDif_iniY = posNWell − S1DNWN`（`:81`），P 扩散区必须被阱包围
  `pDif_iniY = posNWell + E1WNDP`（`:82`）。`nwellpos = H/2 = 1.235` 时 P/N 两侧
  可用扩散高度相等——历史上取 1.0825 时两侧不等高、小侧成为瓶颈，这就是
  `AUDIT_REPORT.md:507` 记录的那次修正；
- **布线轨道**：中心轨取 `round(posNWell/vGrid − 0.5)`（`:85-86`），向下以
  `S1M1M1+W1M1`（间距+线宽）为步长逐轨排到 GND 半宽处，向上同理（`:90-100`）——
  轨道数由规则自动推出，2.47µm 行高下通常 2–4 条；
- `celltemplate "Tapless"`（`:110-119` 三分支）：决定扩散区到单元上下边界的
  距离；Tapless 不在单元内放衬底/阱接触（由外部 tap 阵列负责），直接省宽度；
- `nSize/pSize`（`:121-122`）= P/N 可用扩散高度，小于晶体管最小宽度 `W2DF`
  直接抛错（`:124-125`）——**fold 阶段的折叠判据用的就是这两个数**。

## 3. fold：把放不下的宽管拆成并联"腿"

编排 `AutoCell::foldTrans`（`autocell2.cpp:171-180`）→ `CellNetlst::folding`
（`cellnetlst.cpp:254-286`）。动机：行高固定 ⇒ 单管最大宽度被 `nSize/pSize`
钉死；库里来的 W=1µm 管子放不下，必须拆成 `ceil(W/size)` 条等宽的并联腿。

两个判据（`cellnetlst.cpp:265-283`）：
- **孤立宽管**：`width > pSize+1e-5` 就拆；
- **串联链整体折叠**：`findSeriesToFolding`（`:741`）从 GND/VCC 出发沿"度为 2、
  非输出、非电源"的内部网找串联链；**只有当链上所有管子都超宽时**才整链折叠
  （`:837`），腿数取链上最宽管的 `ceil(W/size)`（`:820/830`）——整链同腿数
  才能保证折叠后链 still 对称可布。

折叠本身（`seriesFolding`，`:858-946+`）把每条腿的中间节点改名为 `net_腿号`，
首尾管保留真实端口网名。⚠️ 已修复的坑：**单元素串联链**原来会索引 `trans[-1]`
并让折叠腿悬空，现在直接让腿接在真实 drain/source 网之间（`:872-885` 注释）。
数组上界 `numSeries = 0.9×totalTrans`（`:780`）是启发式估值。

## 4. place：两排晶体管排序——Threshold Accept（不是教科书模拟退火）

入口 `AutoCell::placeTrans`（`autocell2.cpp:182-224`）→
`CellNetlst::transPlacement`（`cellnetlst.cpp:523-579`）。

**表示**：`orderingP`/`orderingN` 两个等长序列，每格 `{link, type}`，
`type ∈ {DRAIN, SOURCE}` 表示该管朝左的端子（决定扩散共享方向）。P/N 管数
不等时用 `link = −1` 的 **GAP** 补齐（`:547-553`）——读排序时必须先判 GAP，
`route()` 里四处未判的读取曾导致 NOR3X1（P6/N3）崩溃（`autocell2.cpp:260,269,
326-327,407/421` 的守卫与注释）。

**算法是 Threshold Accept**（`thresholdaccept.h:86-197`）——模拟退火的确定性
变体：接受准则是 `Δcost ≤ threshold` 而非 `exp(−Δ/T)`，阈值初值由
`FindInitialThreshold` 标定、按 `0.98 − (接受率²)/2` 衰减。没有 `srand`
（全库 grep 无），`rand()` 走 C 运行时默认种子 ⇒ **同一输入序列固定**，这就是
"布局确定性"的来源（AGENTS.md 不变量 8）。扰动 `perturbation()`
（`cellnetlst.cpp:462-472`）随机选 P 排、N 排或两排做 `move()`（`:474-507`：
随机长度段移位，或镜像翻转一段的 S/D 朝向）。

**代价函数**（`getCost`，`:364-460`）——六项加权和，权重在
`autocell2.cpp:158`（wC=4, gmC=4, rC=1, congC=4, ngC=2，外层 ×100 再加局部拥塞）：

| 分量 | 含义 | 为什么重要 |
|---|---|---|
| `mismatchesGate` | 同列 P/N 管栅网不同的列数 | 栅对齐 ⇒ 一条竖直 poly 直通到底，省 poly 也省接触 |
| `wGaps` | 扩散间断数（相邻列左网≠右网） | 每处间断要断开扩散、加间距，直接撑宽单元 |
| `posPN` | P/N 序列总宽度 | 一阶面积项 |
| `wRouting` | 各网 bounding box 跨度之和（除 VDD/GND） | 布线难度的线长代理 |
| `maxCong` / `localCong` | 最热轨道拥塞 / 局部拥塞平方和 | 防止宽进去了但布不通 |

**speculate 模式**（`autocell2.cpp:187-216`）：内层循环选出轨道数后，再跑
3 次"试布局 + 快速试布线"，用布线器返回的真实代价 `rt->getCost()` 选最优排序
——这是 place 与 route 之间唯一的反馈环。

## 5. route：Pathfinder 式迭代拆线重布

入口 `AutoCell::route`（`autocell2.cpp:243-474`）。先把排序翻译成一列列
`Element`（diff/poly/met 节点）构成**逐轨道图**：金属水平弧代价 4/16、poly 弧 6、
扩散区内接触弧 20（`COST_CNT_INSIDE_DIFF`）、inout 连接 495/500（`:28-38,42,
277,62`）。代价设计鼓励"先走扩散/金属、少用 poly、尽量不在扩散区内打孔"。

核心求解器 `GraphRouter::routeNets`（`graphrouter.cpp:92-166`）是教科书
**Pathfinder 协商布线**（VPR 家族）：

1. 每轮允许拥塞地布所有网，记录冲突节点；
2. 冲突节点的 `history++`（`:138`），下一轮 BFS 代价 = `弧代价 +
   history × (网数+1)`（`:431`）——反复被抢的资源越来越贵，网自然让开；
3. 拆掉冲突网重布（`:119-139`），直到无冲突或 8000 轮上限（`autocell2.cpp:470`）；
   `cntConflict>50000` 兜底判失败（`graphrouter.cpp:165`）；
4. 之后 `optimize()` 两轮做滑线式微调（`autocell2.cpp:472`）。

布不通不是终局——`autoFlow` 外层会 `conservative++` 收缩扩散区、腾出纵向轨道
再全流程重来（最多 4 次）。

## 6. compact：ILP 一维压缩——本层数学含量最高的阶段

入口 `AutoCell::compact`（`autocell2.cpp:476-1074`），LP 引擎
`compaction.cpp`。布线后的版图已合法但松弛，压缩把每个图形的坐标当成变量、
把所有设计规则写成线性约束，让求解器把总宽度压到最小。

### 6.1 变量体系（`createGeometry`/`createNode`，`autocell2.cpp:1517-1594`）

- 每个几何 Box：`x<id>a, x<id>b, y<id>a, y<id>b`（四条边坐标，连续变量）；
- **端线扩展变量** `x<id>a2/b2`：线端帽（end-of-line）外扩后的边。§5.11 的修复
  把它们用 `CP_EQ` 钉到真实边上（原为 `CP_MIN`，会被压缩器反向收缩导致对角
  间距违规，`autocell2.cpp:1570-1575`）；
- 二进制 `b<id>_endline_v/h`：标记是否为线端；
- DFM 变量 `max<id>H/V`：鼓励图形拉宽拉满（负权重，`:1589-1590`）；
- 常量行：`ZERO / UM / RELAXATION(=20000) / HGRID_OFFSET`（`compaction.cpp:502-505`）。

### 6.2 约束家族

- 最小宽度（`W1M1/W2P1`）、与边界距离（`minDist/2`）；
- **间距析取**：`insertDistanceRuleInteligent`（`autocell2.cpp:1643-1682`）给
  每对需要保持距离的图形三个二进制 `b<A>_<B>_1/2/3`（B 在 A 右侧 / 上方 /
  对角右上），约束 `b1+b2+b3=1`；每条间距约束写成
  `x<A>b + RELAXATION − x<B>a2 ≥ b·(minDist+relaxation)`——b=1 时收紧为真实间距，
  b=0 时被大 M（`relaxation=20000µm`，`autocell2.h:68`）松弛掉。对角项距离取
  `ceil(2·minDist/√2)`。**option-3（对角）是历史上唯一被证明可能过度约束的
  析取**（见 §8）；变体 `Inteligent2/3/3x1/Dumb` 处理其他相对位置（`:1684-1720`）；
- 宽度对齐：总宽 `width` 被强制为 hGrid 整数倍（`width_gpos`），保证多单元
  abutment 时对齐制造网格。

### 6.3 目标函数

`insertLPMinVar` 累积带权变量：**`width` 权重 5000 绝对主导**（`:810-813`），
其余是 tie-breaker：金属节点权 3、track 权 1、poly 节点权 6/track 4、L-turn
二进制权 4/7、DFM 变量负权。语义：先把宽度压到最小，同宽下让线更短更直。

### 6.4 求解与表达式重命名（`compaction.cpp:462-746`）

- 写 `ILPmodel.lp`（文件名硬编码于 `autocell2.cpp:499`），调外部求解器
  `gurobi_cl.cmd`，读回 `ILPmodel.sol`——**都在进程工作目录**，所以不能并发跑
  两个单元（架构上靠 CLI 顺序循环 / GUI 单 worker 保证）；
- ASTRAN 的约束 API 允许"变量名"是**表达式**（如 `"b0_17_1 + b0_17_2 + b0_17_3"`、
  `"x15b + RELAXATION"`）。CoinLpIO 拒绝这种列名并静默回退 `x0,x1,…`（模型断连），
  所以 `solve()` 自己先重命名：`needRename` 检出非 `[A-Za-z0-9_]` 字符 →
  换成 `astranExpr<k>`（`compaction.cpp:469-495`，按名字长度降序做子串替换防
  短名串扰），并**显式补定义约束** `Cexpr<j>: astranExpr<k> − b0_17_1 − … = 0`
  （`:605-611`）；解回读时再翻译回原名（`:729-735`）。同名变量系数先合并
  （`:520-532`）。这套机制就是 AGENTS.md 不变量 3 的实现；
- **spacing repair pass**（`autocell2.cpp:818-905`）：成对约束只覆盖相邻两列
  Element，远处轨道间可能漏检。最多 8 轮：从解读坐标，O(n²) 找违反规则的异网
  对，**每对插 4 个二进制**（右/左/上/下）且**每条约束都带 +RELAXATION 项、
  系数 = rule+relaxation**——少带一项会让"off"分支仍强制满足，四个选项互相
  矛盾、模型必然不可行（这是曾经真实烧掉一轮迭代才发现的坑，
  `autocell2.cpp:884-891` 注释）；
- **全零解 fail-fast**：求解失败时适配层只写 .sol 头（无变量行），
  `getVariableVal("width")<=0` 直接返回 false（`:830-831`），避免在退化解上做
  无意义的修复。

### 6.5 求解器适配层（`tools/gurobi_cl/gurobi_cl.py`）

ASTRAN 以为自己还在调 Gurobi 命令行，实际被替换成 python-mip + CBC：

- **自己解析 LP**（`:105-141`），不用 `Model.read()`（原因见上）；
- **inf 系数项丢弃**（`:85-94`）：ASTRAN 会对同一约束发射 0.0 与 inf 两个
  孪生系数，inf 表示"无界"，夹成 big-M 会把模型改掉 → CBC 报无解；
- **FEASIBLE 即成功**（`:274-276`）：2% 相对 gap（`:255`）下 CBC 常常找到好解
  但证不了最优；
- **时间预算**：phase1 = `GUROBI_CL_TIME_LIMIT`（默认 300s，clamp 到 [60,
  timelimit]）；仅当 **NO_SOLUTION_FOUND** 才追加 phase2（默认 900s，`:258-271`）；
- **option-3 重试**：仅当状态**精确等于 INFEASIBLE**（被证明不可行，不是超时）
  时，重建模型、丢弃 option-3 析取（`_is_option3_disjunct`，`:148-163`）再解，
  日志打 "retrying without the option-3 spacing disjuncts"，ASTRAN 的 repair
  pass 随后强制真实间距。设计理由的长注释在 `:281-297`；
- 失败时只写 `# Objective value = 0` 头（`:306-314`）→ ASTRAN 侧变量保持
  默认 0 → **0×0 版图** → 前端按宽度≤0 剔除（`main.py:154-158`），失败语义
  全链路可观测；`ASTRAN_DUMP_FAILED_LP=1` 时 C++ 侧把失败模型存成
  `ILPmodel.fail.lp`（`compaction.cpp:689-708`）。

## 7. export：写 GDS——独立的第六条命令

`export layout` 不在 autoflow 内（`designmng.cpp:331-381`）：层号查
`rules->getGDSIIVal`（tech 文件的 `SET TECHNOLOGY GDSII` 行）；坐标 ×2 取整
（半格点舍入）；**0×0 盒直接跳过**（`:359`）——所以失败求解导出的是空单元
而非全零方块；引脚文本必须放 MET1P purpose 层（`:371-375`）否则后端
stream-in 绑不上逻辑引脚。`Cell Size (W x H)` 打印在 compact 末尾
（`autocell2.cpp:1071`），由外层 shell 重定向进 `.Astranlog`。

## 8. 失败模式与排障速查

| 日志/现象 | 根因 | 处置 |
|---|---|---|
| `Cell Size (W x H): 0 x 0` | LP 求解失败写全零解 | grep "no usable LP solution"；`ASTRAN_DUMP_FAILED_LP=1` 留模型；该模式被剔除 |
| `retrying without the option-3 spacing disjuncts` | 证明 INFEASIBLE（历史上 1.0825 不等高几何触发过） | 自动恢复；现行 1.235 几何下 adder 四单元均未触发 |
| compact 反复失败 → conservative 递增至 >4 | 布线/压缩救不回来 | 单元抛 AstranError，前端剔除 |
| `trans[-1]` 崩溃（历史） | P/N 不等长的 GAP 未守卫 | 已修（route 四处 + 折叠一处） |
| 无法启动 Astran.exe | 360 误报隔离 | `gui/flow_core.py:_popen_astran` 给出白名单指引 |

**耗时分布**（一个单元 5–10 min）：place 的阈值接受迭代 + route 的 Pathfinder
是大头，compact 的 ILP 在 300s 封顶内通常几分钟内返回可行解。

## 9. 与学术前沿的差距（速览，详见 RESEARCH_AND_OPTIMIZATION.md）

- place 是 1990s 风格的阈值接受：近年 SMT 联合 folding+placement（ASP-DAC'26）、
  MILP 同时优化拓扑/布局/布线（SO3-Cell, ICCAD'25）、MCTS+AllSAT（CoP&R,
  ICCAD'25）都可作质量基线；
- route 的 Pathfinder 可被 CP-SAT 替换（TransRoute, DAC'25）；
- 评估只看宽度：Routability Booster（ISPD'24）、Cell-Flex（ISPD'25）、
  FastPass（TCAD'24）提供了可布性/引脚可达性第二维度；
- 架构是单面 bulk/FinFET 假设：CFET/BSPDN 需要双面感知引擎（ASP-DAC'26 等）。
