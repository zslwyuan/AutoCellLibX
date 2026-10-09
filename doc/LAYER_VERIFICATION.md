# 分层校验报告：方案与代码实现的正确性、合理性

> **校验对象**：[IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) 九层模型 vs
> 仓库实际实现（`pySrc/`、`tools/`、`gui/`、`tests/`、`outputs/`）。
> **校验方法**：逐条对照指南声明与代码（file:line 取证），关键数字实跑验证，
> 并运行完整单元测试（`python -m pytest` → **194 passed, 4 deselected**，
> 与指南"194 个测试"一致）。
> **总体结论**：九层的**架构叙述与主流程实现全部吻合**；发现的偏差集中在
> ① 指南 4 处具体数字/示例过期（已随本报告修订）；
> ② 代码 5 处隐患（已记录于 [AUDIT_REPORT.md](AUDIT_REPORT.md) §新增发现，未改动行为）；
> ③ 合理性层面 6 项系统性风险（构成 [RESEARCH_AND_OPTIMIZATION.md](RESEARCH_AND_OPTIMIZATION.md) 的动机）。
>
> 记号：✅ 与代码一致　❌ 文档/事实错误　⚠️ 行为正确但有风险或语义偏差
>
> **后续处置（2026-10-09）**：下表 5 处代码隐患已全部修复（带回归测试），
> 六项合理性风险中编码顺序敏感、生长宽度 1、重叠计重、宽度单指标、无等价
> 测试五项已落地优化（P0-1～P0-5），贪心停止/魔法数一项保持现状（启发式
> 调参留给后续消融实验）。见 [AUDIT_REPORT.md](AUDIT_REPORT.md) §5.18。

---

## 第 1 层 · 数据格式

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 1 | adder.blif 由 `.subckt`/`.names` 组成 | ✅ | 707 行 `.subckt` + 3 行 `.names`；但 3 行实为 `$false/$true/$undef` 常量门，指南示例 `.names g_27 g_31` 是示意非原文 |
| 2 | Liberty 只被用来取引脚方向 | ✅ | `pySrc/blif_preproc.py:59-73`、`pySrc/blif_graph_util.py:18-23`；lib 中 759 行 timing/power 全部未读 |
| 3 | NAND2X1 为 W=0.205u 的 4 管结构 | ❌ **W=0.5u**，且引脚序为 `VCC Y GND A B` | `stdCelllib/cellsAstranFriendly.sp:590-598`（已修订指南） |
| 4 | LEF 每单元一行 SIZE；NAND2X1=1.14×2.47 | ❌ **NAND2X1=0.76×2.47**（1.14 是 AND2X1）；行高 2.47 全库一致 ✅ | `stdCelllib/gscl45nm.lef:2132-2136, 411-414`（已修订指南） |
| 5 | .rul/.map 格式与前缀语义（S/E/W） | ✅ | `tech_freePDK45.rul:8` 等抽查成立；另有指南未提的 R=电阻类规则（`:21/:39`） |
| 6 | GDS UNITS 不可信，按日志标定 | ✅ | `gui/gds_model.py:3-11,22,187-189`；含"well bbox 致 19% 膨胀"的注释（`:165-167`） |

## 第 2 层 · 解析与数据结构

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 7 | adder 解析得 710 节点 / 803 边 | ✅ **实跑复现** | `gen_graph_from_liberty_and_blif` 输出 `710 803`；NAND2X1 实例 192 个亦属实 |
| 8 | `bypassTypes=["DFF","bool"]` 阻断时序/未映射门 | ✅ | `pySrc/global_variables.py:2`；消费点 `blif_preproc.py:204-207,225-229,253-260`、`blif_pattern_growth.py:41,62,192,213` |
| 9 | 节点=实例、bool 门入图为 `bool-...` 虚拟类型 | ✅ | `blif_preproc.py:79-87,126-137,184-190` |

**⚠️ 解析鲁棒性**（正确输入下无影响，畸形输入不防御）：
- 库中找不到 `.subckt` 类型直接 `assert(False)`（`blif_preproc.py:123-124`）；
- 多驱动网静默覆盖 `predCell`（`blif_graph_util.py:82-84`），无告警；
- 扇出网有 `<10000` 硬编码截断（`blif_preproc.py:196-199`）；
- bool 门被静默排除，未映射逻辑占比无覆盖率报告（仅 `gui/flow_core.py:425` 有统计）。

**合理性**：Liberty 只取 direction 对"结构合并"够用且快，但 delay/leakage/电容
全丢——**这是后续 timing/power 感知优化的主要数据障碍**（见优化路线图 P1-7）。

## 第 3 层 · 编码

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 10 | 深度 1 BFS、类型名拼接成编码 | ✅（调用点确实 depth=1；函数默认 `depthLimit=2`） | `blif_preproc.py:212,250,261` |
| 11 | "编码相同⇒结构等价" | ⚠️ 是启发式非证明 | 编码只拼 `typeName`（`:215,233`）：引脚排列、跨边（reconvergent fanout）、根扇出、多输出形态全部不可见 |
| 12 | 线性时间分组 | ✅ | dict 按键分组 `:252-268`，无两两同构比较；仅取 top-30 编码进入聚类（`:284`） |

**❗ 新发现（合理性）**：**编码不对子节点排序**（源码无 sort，`:222-235` 按
`inputNets` 迭代顺序拼接）。根节点的多个输入类型不同时（如 `[XOR2X1,NAND2X1,OR2X1]`
vs `[XOR2X1,OR2X1,NAND2X1]`），同构实例会得到不同编码 → **系统性漏匹配、频次被
低估**。adder 现有结果靠网表生成顺序一致而幸免。这是挖掘层最值得修的算法缺陷
（优化路线图 P0-1）。

## 第 4 层 · 聚类与生长

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 13 | 簇数×簇大小排序 | ✅ | `blif_graph_util.py:136-153`（`np.lexsort`） |
| 14 | 特征码 `XNOR2X1_c0o0`、一次只吸收最高频一类 | ✅ | `blif_pattern_growth.py:51-53,70-73,104` |
| 15 | 演化链 `[NAND2X1,NAND2X1,OR2X1]→+XNOR2X1_c0o0→+OAI21X1_c2o0` | ✅ | `outputs/adder/bestRecord-adder`、`COMPLEX9.sp:55`（60 occurrences）、`COMPLEX10.sp:67`（59 occurrences） |
| 16 | trace 是唯一身份、`dumpedPaterns` 以 trace 为键 | ✅ | `blif_graph_util.py:90-91`、`blif_pattern_growth.py:124`、`main.py:78,112,123` |

**⚠️ 指南未披露的三个事实**（已在指南补注）：
1. **COMPLEX10 实际是负收益**（`bestRecord-seperateadder:5`：saveArea **−56.05**）——
   "先长再看亏不亏"的策略代价的实证；
2. `cellOrderId` 来自 `cellsContained` 枚举序，同类型兄弟（两个 NAND2X1）的
   c0/c1 分配任意，跨簇不保证指向同构位置——特征码可能把同一真实特征拆成两类，
   频次被稀释；
3. 实例唯一归属的 enforcement 是**破坏式**的：邻居已被别的模式占用时直接
   `disabled=True` 踢掉旧簇（`blif_pattern_growth.py:118-120`），无收益比较。

## 第 5 层 · 导出 SPICE

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 17 | 四步：前缀隔离/内部重连/端口内化/确定性写盘 | ✅ 全部属实 | `pySrc/spice.py:109-113,116-122,136-144,128-132`；VCC/GND 不前缀（`:33-35`） |
| 18 | COMPLEX1.sp 头部逐字一致 | ✅ | `pySrc/outputs/adder/COMPLEX1.sp:1-2,63-64`（54 occurrences） |
| 19 | PYTHONHASHSEED 确定性有测试钉住 | ✅ | `tests/unit/test_determinism.py:41-43`（seed∈{0,1,7} 三次 md5 相同）；"内容不变不写盘"由 `spice.py:165-172` + `test_spice.py:65` 锁定 |
| 20 | W/L 原样透传，折叠留给 ASTRAN | ✅ | `spice.py:150-151` 仅文本拼接 |

## 第 6 层 · 面积度量

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 21 | 三个面积来源统一返回宽度 | ✅ | `astran.py:31-46`（find "Cell Size (W x H)"）、`gds_analysis.py:43-49,59-75`（LEF/日志取宽） |
| 22 | 0×0 版图剔除 | ✅ 三道防线 | `main.py:154-158,180-181,318-322` |
| 23 | 基线与产物同为 2.47µm 行高 | ✅ | `originalAstranStdCells/NAND2X1.Astranlog`（0.76×2.47）与产物同由 `runAstranForNetlist` 生成 |
| 24 | 节省公式 = 出现次数×(基线宽度−新宽度) | ✅ | `main.py:176-193`；分母为全设计基线宽度和（`main.py:72`） |

**⚠️ 代码隐患（已记入 AUDIT_REPORT）**：
- `astran.py:45-46`：日志缺失时 `assert(False); return 123`——`python -O` 下
  assert 被剥离，**静默返回 123µm 假宽度**；
- `gds_analysis.py:18-21` 注释仍写"基线 H=3.2/本地 2.6"，与现行 2.47µm 常量
  矛盾（文档漂移，行为正确）。

**❗ 新发现（合理性）**：**节省求和无重叠去重**。`setCluster` 直接覆盖
（`blif_graph_util.py:60-63`），不同模式的簇可共享单元；`main.py:185-188` 对
top-5 候选的节省直接求和，共享部分被重复计收益（方向：高估）。反向的保守因子
（0×0 剔除、门限 bypass）部分对冲，但净方向偏乐观（优化路线图 P0-2）。

## 第 7 层 · ASTRAN（详见 [LAYER7_ASTRAN.md](LAYER7_ASTRAN.md)）

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 25 | .run 含 rowheight13/grid0.19/supplysize0.26/nwellpos | ❌ **nwellpos 实为 1.235**（=2.47/2，指南写 1.0825 过期）；❌ 示例**漏 `set celltemplate "Tapless"`** | `astran.py:58-63,74-86`、`outputs/adder/COMPLEX1.run:4-8`（已修订指南） |
| 26 | 几何与 GSCL45 CoreSite 一致 | ✅ | LEF `SITE CoreSite SIZE 0.38 BY 2.47`（`gscl45nm.lef:411-414`） |
| 27 | autoflow 七阶段 | ⚠️ 实为六阶段 + 独立 export 命令；place 是 **Threshold Accept**（SA 的确定性变体）非教科书 SA | `autocell2.cpp:140-169`、`thresholdaccept.h:86-197`、`designmng.cpp:331-381` |
| 28 | ILP 压缩：坐标变量+间距约束+宽度最小化 | ✅ | 变量/析取/big-M=20000/目标权重详见深潜文档 §3 |
| 29 | 300s 封顶、FEASIBLE 即成功 | ✅ | `tools/gurobi_cl/gurobi_cl.py:255,258-276`；超时后可再延 900s（仅 NO_SOLUTION_FOUND） |
| 30 | option-3 析取在证明 INFEASIBLE 时去掉重试 | ✅ | `gurobi_cl.py:298-300`；**实测现行几何下未触发**（adder 四个单元全部首解可行）——`AGENTS.md` 的"expect the log to show"系 1.0825 旧几何残留（已修订） |
| 31 | 无 srand、结果确定 | ✅ | 全库无 `srand`；`rand()` 用 C 默认种子，序列固定 |

另核实：适配层 inf 系数显式丢弃（`gurobi_cl.py:85-94`）、0.0 系数保留但数学
no-op；表达式重命名+定义约束在 C++ 侧（`compaction.cpp:469-512,605-611`）；
`ASTRAN_DUMP_FAILED_LP` 实现于 `compaction.cpp:689-708`（非适配层）；
一次一个单元靠架构串行（CLI 顺序循环 / GUI 单 worker），无锁文件。

## 第 8 层 · 集成

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 32 | 贪心主循环（topThr=5、超最佳才继续、生长 top-1） | ✅ 与伪代码逐句吻合 | `main.py:89-239` |
| 33 | 初始候选池 Top-30 | ✅（在 `blif_preproc.py:284` 硬编码 `[:30]`，勿与 `cntThr=30` 混淆） | 同左 |
| 34 | 缓存契约两半（mtime + 内容不变不写盘） | ✅ | `astran.py:119-133`、`spice.py:165-170`、`tests/unit/test_layout_cache.py:17-41` |
| 35 | 失败隔离 + 增量写 bestRecord | ✅ | `main.py:140-168,198-213` |
| 36 | 流水线不清理过期产物 | ✅（CLI 无清理；GUI 侧有 `flow_core._clean_output`，默认关） | `main.py` 无 remove/shutil；`gui/flow_core.py:380-390` |

**⚠️ 代码隐患（已记入 AUDIT_REPORT）**：
- `main.py:247-248`：`bestRecord-seperate` 在逐模式循环**之前**以 `'w'` 打开，
  循环中途异常会留下空/半截文件；
- `main.py:92`：`cellIdsContained>=11` 用 `continue` 跳过但队首未弹出，存在
  死循环风险（依赖后续其他分支弹出，脆弱）。

**⚠️ 合理性**：贪心"单轮无改善即停"偏保守（候选池每轮重排+生长，先差后好的
模式族会被提前砍掉）；Top-30/topThr=5/ratioThr=0.05/cntThr=30/max_cells=11
均无消融依据，且 `tc_008` 有 ratioThr=0.025 特判（`main.py:46-47`）——阈值
泛化性存疑；mtime 缓存在时钟回拨/跨机拷贝/2 秒粒度 FAT 下会失效（内容寻址
才是正解）。

## 第 9 层 · GUI

| # | 指南声明 | 结论 | 证据 |
|---|---|---|---|
| 37 | Qt-free 核心（paths/artifacts/gds_model/flow_core） | ✅ 零 PySide6 引用（`state.py` 含 Qt 但本就不在清单内） | grep 验证 |
| 38 | flow_core 是 main.py 忠实移植 | ✅ 守卫逐项对应 | trace 去重 `flow_core.py:612-613`、0×0 `:647-664`、增量 bestRecord `:694-699,771-789`、串行 ASTRAN `:234-235`；唯一偏差：`benchmarkFailure` 死代码未移植（合理） |
| 39 | 取消机制（含杀进程树） | ✅ | `flow_core.py:181-183,266-268,308-316` |
| 40 | matplotlib 钉 Agg | ✅ | `gui/app.py:23-24` 在一切 Qt/pyplot 之前 |

**❗ 新发现（合理性）**：**没有任何测试断言 flow_core 与 main.py 输出等价**。
"faithful port"目前靠 code review 保证；main.py 已有三份控制流副本
（main.py / replay_separate_adder.py / flow_core.py），漂移风险实质存在
（优化路线图 P0-5）。

---

## 汇总

| 类别 | 数量 | 处置 |
|---|---|---|
| 指南数字/示例错误（❌） | 4（W=0.5u、引脚序、LEF 0.76、nwellpos 1.235+漏 celltemplate） | 已修订指南 |
| 代码隐患（⚠️ 待修） | 5：`astran.py:45` assert 假宽度；`main.py:247` bestRecord 半截；`main.py:92` 死循环风险；`blif_preproc.py:123` assert(False)；多驱动网静默覆盖 | 记入 [AUDIT_REPORT.md](AUDIT_REPORT.md)，未改行为 |
| 算法合理性风险（优化动机） | 6：编码顺序敏感漏匹配；生长宽度 1 且不知面积（COMPLEX10 −56.05）；收益无重叠去重；纯宽度代理无电气量；贪心停止脆弱+魔法数无依据；flow_core 无等价测试 | 展开为 [RESEARCH_AND_OPTIMIZATION.md](RESEARCH_AND_OPTIMIZATION.md) 路线图 |

*校验日期：2026-10-09。校验代理对每条声明直接阅读源码并抽样实跑，证据行号以
仓库当前 HEAD 为准。*
