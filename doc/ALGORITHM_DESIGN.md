# AutoCellLibX × ASTRAN 算法方案

> 面向 **算法架构师** 与 **ASIC/后端工程师** 的完整技术方案。
> 目标：读完本文，架构师能据此评估/改造算法，工程师能据此复现、集成与排障。
>
> - 文档版本：2026-09-27
> - 配套文档：[doc/PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)（目录/模块详解）、[doc/AUDIT_REPORT.md](AUDIT_REPORT.md)（缺陷审查与修复记录）、[doc/LESSONS_LEARNED.md](LESSONS_LEARNED.md)（方法论经验）、[AGENTS.md](../AGENTS.md)（工程不变量）
> - 所有插图由 [figures/gen_figures.py](D:/AutoCellLibX/doc/figures/gen_figures.py) 生成，可用 `python doc/figures/gen_figures.py` 重新生成。

---

## 0. 30 秒速览

**一句话**：AutoCellLibX 在一个已经做完技术映射的门级网表里，挖出**频繁出现、结构相同**的子电路（"模式"），把每个模式**合并成一个新的复杂标准单元（COMPLEX cell）**，再用 ASTRAN 在晶体管级别把它**自动布局布线**出来；合并后的单元因为共享扩散区、省去单元间互连，比"一堆独立单元并排"更省面积，从而让整个设计的总面积下降。

![系统总览](D:/AutoCellLibX/doc/figures/sys_overview.png)

系统由三部分组成（颜色即上图泳道）：

| 组件 | 角色 | 位置 | 语言 |
|---|---|---|---|
| **AutoCellLibX 前端** | 读网表 → 挖模式 → 生长 → 评估 → 导出复杂单元网表 | `pySrc/` | Python |
| **ASTRAN 后端** | 把一个单元的晶体管网表综合成晶体管级版图（GDS） | `tools/astran/` | C++ |
| **LP 求解器适配层** | 把 ASTRAN 的压缩模型交给开源求解器 CBC | `tools/gurobi_cl/` | Python |

三者**通过文件解耦**：前端吐 `.sp` 网表和 `.run` 脚本 → ASTRAN 执行并吐 `.gds` 版图和 `.Astranlog` 日志 → 前端从日志读回宽度做面积评估。没有共享内存、没有 API 绑定，替换任何一端都不影响另一端。

> **当前实测效果**（基准 `adder`，详见 §7）：选出一个 5 单元复杂单元 `COMPLEX10`，记录节省 **106.2 µm²（相对 ASTRAN 同高基线 13.25%，相对 GSCL 库 11.44%）**。论文在 31 个基准上平均节省 4.49%。

---

## 1. 动机与问题定义

### 1.1 为什么要"合并标准单元"

通用标准单元库为了"什么设计都能用"，每个单元都是**独立、自包含**的：有自己的扩散区、自己的电源接触、单元之间靠金属线连接。这在通用性上很好，但对一个**特定设计**而言是浪费的——很多总是成组出现的小单元组合（比如全加器里的 `NAND2+NAND2+OR2`），如果能为它专门做一个单元，就能：

1. **共享扩散区（diffusion sharing）**：相邻晶体管的源/漏可以合并，省掉接触孔和间距；
2. **省去单元间互连**：原来要走金属层的内部信号，变成单元内部的短线；
3. **扩大后端解空间**：布局布线器面对一个"更大但更优"的单元，可能比面对"更多个小单元"收敛得更好；
4. **缩小后端问题规模**：门数变少、且有预定义的相对位置约束。

这正是论文（[arXiv:2207.12314](https://arxiv.org/abs/2207.12314)）的出发点。难点在于：**选哪些子电路来合并**，需要理解目标设计的特点（模式挖掘）；**合并后的单元长什么样**，需要满足设计规则的晶体管级版图（布局综合）。AutoCellLibX 负责前者，ASTRAN 负责后者。

### 1.2 形式化问题

- **输入**：
  - 门级网表 $N$（BLIF 格式，已完成技术映射，节点是标准单元实例）；
  - 标准单元库 $L$（Liberty `.lib` 提供引脚/方向，单元级 SPICE `.sp` 提供晶体管级实现）；
  - 工艺规则（`tech_freePDK45.rul`）。
- **输出**：一组新的复杂单元 $\{C_i\}$（每个含晶体管级网表 `.sp` + 版图 `.gds`），作为初始库 $L$ 的扩展。
- **目标**：最大化总节省 $\text{saveArea} = \sum_i \big(\sum_{c \in \text{pattern}(C_i)} w(c) - w(C_i)\big) \times \text{occurrences}(C_i)$，其中 $w$ 是单元宽度（§3.7 解释为什么用宽度）。
- **约束**：单个复杂单元含单元数 $< 11$；模式出现频次/覆盖率要过阈值（避免为罕见模式浪费版图时间）；版图必须满足工艺设计规则（DRC）。

### 1.3 系统边界（什么在范围内、什么不在）

| 在范围内 | 不在范围内（需另行处理） |
|---|---|
| 挖掘频繁子电路并评估面积收益 | 逻辑综合 / 技术映射（由 Yosys 预先完成） |
| 生成复杂单元的晶体管级版图 | 版图与目标库的行高精确对齐、GDS 层号重映射（见 §10） |
| 面积收益估计与组合选择 | 时序/功耗签核、DRC/LVS 正式验证、顶层布局布线 |

> 给 ASIC 工程师的提醒：当前生成的复杂单元行高为 **2.6 µm**，而 GSCL45 目标库行高为 **2.47 µm**，且两者 GDS 层号体系不同。**生成的版图是"算法正确的版图"，但还不能直接并入商业库做流片**——需先做行高标定和层映射（见 §10）。面积数字用于"相对比较哪些模式值得做"，这一点是可靠的。

---

## 2. 系统总览

### 2.1 端到端流水线

前端（Python）是"决策者"，后端（ASTRAN）是"执行者"，求解器是后端的"外援"。完整的数据流和控制流如下（这正是 §0 总览图的展开）：

1. 前端读入网表 + 库，构建有向图，挖掘出**初始模式种子**（§3.3）；
2. 进入一个**贪心迭代**：每轮把当前最高频的模式导出成 `.sp`，交给 ASTRAN 生成版图，读回宽度算收益；
3. 同时把最高频模式**生长**（吸收一个邻居单元）成更大的候选模式，回到第 2 步（§3.4）；
4. 当某一轮的总收益不再超过历史最佳，停止，把最佳组合写入 `bestRecord-*`（§3.5）；
5. 后端 ASTRAN 对每个复杂单元执行 `autoflow`：折叠 → 布局 → 布线 → ILP 压缩 → 导出 GDS（§4）。

### 2.2 目录速查

```
AutoCellLibX/
├── pySrc/                    # 前端算法（Python）
│   ├── main.py               #   主流水线：挖掘→生长→评估→导出 的编排
│   ├── BLIFPreProc.py        #   解析 liberty/BLIF、构图、初始聚类
│   ├── BLIFPatternGrowth.py  #   模式生长算法
│   ├── BLIFGraphUtil.py      #   数据结构 + 模式子图可视化
│   ├── spice.py              #   复杂单元 SPICE 网表拼装
│   ├── Astran.py             #   调用 ASTRAN + 读回宽度（接口层）
│   └── outputs/<bench>/      #   每个基准的产物（COMPLEX*.sp/gds/png、bestRecord-*）
├── tools/
│   ├── astran/               # 后端版图综合（vendored C++ 源码 + build/bin/Astran）
│   └── gurobi_cl/            # LP 求解器适配层（gurobi_cl.cmd → gurobi_cl.py → CBC）
├── stdCelllib/               # PDK 与单元库（gscl45nm.lib/.lef、cellsAstranFriendly.sp）
└── benchmark/blif/           # 技术映射后的门级网表（24 个基准）
```

### 2.3 运行入口

```bash
cd pySrc
python main.py                          # 跑完整流水线（当前配置 benchmark=["adder"]）
python regenerate_cells.py COMPLEX1     # 只重生成指定单元的版图，不重跑挖掘
```

> 工程细节（构建 ASTRAN、跑测试）见 [BUILDING.md](../BUILDING.md)。本文聚焦**算法与接口**。

---

## 3. 前端算法：AutoCellLibX 模式挖掘

前端把"在一个大图里找值得合并的高频子图"这个 NP-hard 问题，用一套**编码 + 贪心生长**的启发式方法降到工程可解。它刻意避开了"通用频繁子图挖掘（FSM）"的指数复杂度，改为**利用标准单元的特性做定向生长**。

### 3.1 输入解析与图建模

`BLIFPreProc.genGraphFromLibertyAndBLIF` 做三件事：

- **解析 Liberty**（`.lib`）得到每种单元的引脚名与方向，构建 `StdCellType`；
- **解析 BLIF** 网表，把每个 `.subckt` 实例建成一个 `DesignCell`，把每条信号线建成一个 `DesignNet`（记录它的驱动单元和负载单元）；
- **构建有向图** `BLIFGraph`（networkx `DiGraph`）：**节点 = 单元实例**，**有向边 = 驱动单元 → 负载单元**（沿信号流向）。每个节点打上 `type`（单元类型名）标签。

![门级图建模](D:/AutoCellLibX/doc/figures/graph_model.png)

两个对后续很重要的细节：

- **`bool-` 虚拟单元**：BLIF 里未被映射的布尔函数（真值表）会被当成 `bool-<真值表>` 类型的虚拟单元加入图中；
- **`bypassTypes = ["DFF", "bool"]`**（`globalVariables.py`）：含 DFF（时序单元）或 bool 的节点被标记为 `stopType`，**不参与模式聚类**——时序单元和未定型的布尔门不适合被合并进组合逻辑复杂单元。

### 3.2 顶点编码：把"子图结构"变成一个可比较的字符串

频繁子图挖掘的核心难题是"判断两个子图是否同构"。AutoCellLibX 用一个**深度受限的树编码**绕开了通用图同构：

`extractAndEncodeSubgraph_Tree(cells, root, depthLimit)` 以某个单元为根，沿输入**反向**做广度优先遍历（默认深度 1），把访问到的单元的**类型名按序拼接**成一个编码串。

> 例：以一个 `OR2X1` 为根，它的两个输入前驱都是 `NAND2X1`，那么这棵深度-1 的树的编码就是 `"[NAND2X1, NAND2X1, OR2X1]"`。

**编码串相同 ⇒ 子图结构等价**（在这个编码粒度下）。这样"找同构子图"就退化成了"按字符串分组"，代价从指数降到线性。编码就是该模式的身份标识，贯穿后续所有环节（它就是后面反复出现的 `patternExtensionTrace`）。

### 3.3 初始模式挖掘与聚类

`heuristicLabelSomeNodesAndGetInitialClusters` 对每个非 bypass 单元都算一次编码，然后：

1. 按编码串**分组**：同编码的所有实例聚成一个 `DesignPatternCluster`，同一编码的所有簇构成一个 `DesignPatternClusterSeq`（模式序列）；
2. 按出现**频次排序**，只保留 **Top-30** 作为初始候选；
3. 用 `sortPatternClusterSeqs` 按 **`簇数 × 簇大小`** 降序排列——优先考察"既大又频繁"的模式。

![模式挖掘与聚类](D:/AutoCellLibX/doc/figures/pattern_mining.png)

> 为什么不用 GNN？仓库里其实有一支 GNN（`GNNModel.py` 是 GIN 风格的 GraphCNN，`BLIFGNNTraining.py` 做节点嵌入，用来辅助聚类），但当前主流程把它注释掉了（`main.py` 第 3 行），用确定性更强的启发式编码替代——见 §3.9。

### 3.4 模式生长：一次只吸收"同一类"邻居

挖到初始模式后，`growASeqOfClusters` 负责把模式**长大**——这是 AutoCellLibX 相对传统 FSM 的关键改进，它巧妙地处理了"子图重叠"问题（满足技术映射约束）。

**做法**：对当前模式的**所有实例**，统计它们边界上的邻居，并按"邻居类型 + 它在模式里的相对连接位置"打上一个**邻居特征码**：

- 输入侧邻居：`typeName_c<i>i<j>`（连到模式内第 i 个单元的第 j 个输入）；
- 输出侧邻居：`typeName_c<i>o<k>`（模式内第 i 个单元的第 k 个输出）。

然后**只吸收出现次数最多的那一类邻居**（`sortedNeighborCode[:1]`），把这类邻居并入各自的簇：

- `patternExtensionTrace += "+" + 邻居特征码`（编码变长，模式变大）；
- `clusterTypeId = patternNum`（新模式分配新 id）；
- 被吞掉的旧簇标记 `disabled` 并剔除，未扩展的旧模式保留在池里。

![模式生长](D:/AutoCellLibX/doc/figures/pattern_growth.png)

**为什么"一次只吸收一类"？** 因为同一个模式的不同实例，其边界上"结构等价"的邻居才应该被一起吸收；按特征码分组保证了吸收后产生的新模式仍然是结构同构的、且互不重叠。这正是论文里说的"carefully handle the overlaps between pattern subgraphs to meet the technology mapping constraint"。

**核心循环伪代码**（`main.py` 主循环 + `BLIFPatternGrowth`）：

```
clusterSeqs = 初始模式序列(Top-30)，按 簇数×簇大小 降序
loop 最多 topThr(=5) 轮:
    for 前 topThr 个候选模式序列:
        if 已导出过(按 trace 去重) 或 簇大小≥11:  跳过
        if 覆盖率不足 (size×cnt < ratioThr×总单元数 且 cnt < cntThr):  停止
        导出 COMPLEX.sp → ASTRAN 生成版图 → 读回宽度
        if 版图无效(宽=0):  排除该模式, 继续
        saveArea += (原单元宽度和 − COMPLEX宽度) × 簇数
    if 本轮 saveArea > 历史最佳:  记录 bestRecord
    else:  停止该基准
    生长 top1 模式(吸收一类邻居) → 新序列回池 → 重排 → 下一轮
```

把这段伪代码对应到 `main.py` 的实际控制流，就是下面这张流程图（含去重、覆盖率检查、版图有效性检查与最优记录分支）：

![前端主循环流程](D:/AutoCellLibX/doc/figures/frontend_pipeline.png)

**关键阈值**（`main.py:35-37`）：

| 参数 | 值 | 含义 |
|---|---|---|
| `topThr` | 5 | 外层轮数上限 / 每轮考察的候选数上限 |
| `ratioThr` | 0.05 | 模式覆盖率下限（`size×cnt ≥ 5% × 总单元数`） |
| `cntThr` | 30 | 模式出现次数下限 |
| 单元数上限 | < 11 | 单个复杂单元最多含 10 个原始单元 |

### 3.5 候选评估与贪心组合

每轮把若干候选模式都送去生成版图，用**实际版图宽度**算收益，做贪心选择：

$$\text{saveArea} = \sum_{\text{选中模式 } i}\Big(\underbrace{\sum_{c\in\text{pattern}_i} w_{\text{ASTRAN基线}}(c)}_{\text{原方案：这些单元各自并排}} - \underbrace{w_{\text{ASTRAN}}(C_i)}_{\text{合并后版图宽度}}\Big)\times \underbrace{|\text{clusters}_i|}_{\text{出现次数}}$$

只有 `saveArea > 0` 的模式才进入组合；本轮总 `saveArea` 超过历史最佳才写入 `bestRecord-<bench>`，否则停止（收益递减即收手）。

![面积评估与组合](D:/AutoCellLibX/doc/figures/area_eval.png)

> **为什么收益来自"合并"？** 见 §1.1：共享扩散区、省掉单元间金属互连。注意这里的"差值"必须是**同一行高**下量出来的宽度（§3.7 的不变量）。

**第二轮（逐模式明细）**：主循环结束后，对每个检测到的模式，`main.py` 用 `..._BasedOn` 变体**只沿着该模式的轨迹生长**，单独评估每个模式自身的覆盖与收益，输出 `bestRecord-seperate<bench>` 明细表（见 §7）。这一步用于分析"哪个模式贡献最大"，不参与组合决策。

### 3.6 SPICE 导出：把多个单元"拼"成一个复杂单元

`spice.exportSpiceNetlist` 把一个模式簇里的所有单元的子电路拼接成一个 `.subckt COMPLEX<n>`：

1. **加前缀隔离**：给第 `k` 个单元的所有内部信号和晶体管名加 `cl<k>#` 前缀，避免不同单元间的命名冲突；
2. **内部连线重连**：若单元 A 的输入来自网络内另一个单元 B 的输出，就把 A 的那个引脚名替换成 B 的输出引脚名（`replaceInputPin`）；
3. **求外部端口**：收集所有接口引脚，删去"完全内部化"的输出（即它驱动的所有负载都在本簇内），剩下的就是复杂单元的对外端口；
4. **写文件**：端口列表用**插入有序映射**（dict）汇总，保证端口顺序确定（见 §3.8）；只在内容真正变化时才写盘（让 `.sp` 的修改时间成为可靠的缓存失效信号，见 §5.4）。

> 真实产物（`outputs/adder/COMPLEX1.sp` 开头，端口顺序为插入序）：
> ```spice
> .subckt COMPLEX1 cl2#Y GND VCC cl1#B cl1#A cl2#A cl2#B cl2#C
> Mcl0#0 VCC cl1#Y cl0#a_2_6# VCC PMOS W=1u L=0.05u
> ...
> * pattern code: [XNOR2X1,XOR2X1,OAI21X1]
> * 54 occurrences in design
> * each contains 3 cells
> ```

> ⚠️ **端口顺序会改变版图，而不只是格式**。ASTRAN 的布局对 `.subckt` 引脚顺序敏感：实测把端口改成"规范序（VCC GND 在前 + 字典序）"后，`COMPLEX0` 从 2.4 → 2.0 µm（更好），但 `COMPLEX10` 从 3.8 → 8.4 µm（明显更差）。没有一致最优，所以**保持插入序**，任何重排端口都必须逐单元实测（见 [AUDIT_REPORT.md](AUDIT_REPORT.md) §5.10）。

### 3.7 面积度量：用"宽度"当代理，且必须同高

这是本仓库最重要的不变量（AGENTS.md 第 1、10 条）：

- **面积 ∝ 宽度**。同一标准单元库的行高是固定的，所以比较"宽度"就等价于比较"面积"。三个面积来源——ASTRAN 基线、ASTRAN 生成的复杂单元、GSCL 库——**都返回宽度**（分别从 `.Astranlog` 的 `Cell Size (W x H)` 和 LEF 的 `SIZE` 读取）。
- **比较必须同高**。宽度只有在行高一致时才是合法代理。早期曾把"H=3.2 µm 的基线"和"H=2.6 µm 的产物"直接比较，导致一个候选的增益从 **+6.5% 翻转成 −19.5%**。现在基线（`originalAstranStdCells/`）和产物都用**同一套几何常量**（`Astran.py:54-59`）重新生成，保证同高。

### 3.8 确定性设计

整个 Python 流程必须是**可复现**的（AGENTS.md 第 9 条）：

- 任何进入产物（尤其进入缓存键）的遍历顺序都必须固定。`exportSpiceNetlist` 用插入有序映射而非普通 `set` 来汇总端口——否则 `PYTHONHASHSEED` 会让每次运行导出不同的网表，既打垮布局缓存又让结果不可复现（`COMPLEX` id ↔ 模式映射漂移）。
- `tests/unit/test_determinism.py` 会在不同 `PYTHONHASHSEED` 下比对导出网表的 md5，强制保证这一点。

### 3.9 （可选）GNN 分支

`GNNModel.py` / `BLIFGNNTraining.py` 实现了论文中可选的 GNN 嵌入路径（GIN 风格 GraphCNN，sum 聚合 + 可学习 ε，4 层、隐藏维 64），用节点嵌入来辅助模式聚类。当前主流程已注释掉它（`main.py` 第 3 行），改用确定性的启发式编码——原因有二：去掉 TensorFlow 依赖、提升可复现性。若要恢复，需把 `convertBLIFGraphIntoDataset` 的输出改回 TensorFlow 张量并恢复导入（见 [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md) §3.9）。

---

## 4. 后端算法：ASTRAN 晶体管级版图综合

前端决定"合并什么"，ASTRAN 决定"合并后的单元长什么样"。ASTRAN 是一个**晶体管级标准单元自动布局综合器**：输入一个单元的晶体管网表（`.sp`），输出满足工艺规则的版图（`.gds`）。

### 4.1 定位与输入输出

| 项 | 内容 |
|---|---|
| 输入 | 单元晶体管网表（`.sp` 的 `.subckt`）、工艺规则（`.rul`）、几何参数（`.run` 脚本 `set` 进来） |
| 输出 | GDSII 版图（`.gds`）+ 运行日志（`.Astranlog`，含最终 `Cell Size (W x H)`） |
| 求解器 | 压缩阶段把模型写成 `ILPmodel.lp`，调用外部 LP 求解器（本仓库用 CBC，见 §6） |
| 调用方式 | `Astran --shell <script.run>`，命令由 `DesignMng::readCommand` 分派 |

`cellgen` 这组命令映射到 C++ 的 **`AutoCell` 类**（`tools/astran/src/autocell2.cpp`）。我们脚本里用到的命令与实现对应关系：

| 脚本命令 | 实现（`tools/astran/src/`） |
|---|---|
| `load technology` | `Rules::readRules`（`rules.cpp`）解析 `.rul` |
| `load netlist` | `Spice::readFile`（`spice.h`）解析 `.sp` |
| `set rowheight/grid/...` | `Circuit::setRowHeight/setHPitch/...`（几何常量） |
| `cellgen select <c>` | `AutoCell::selectCell`（`autocell2.cpp:130`） |
| `cellgen autoflow` | `AutoCell::autoFlow`（`autocell2.cpp:140`） |
| `export layout <c> <f>` | `Gds` 写出器（`designmng.cpp` → `gds.cpp`） |

### 4.2 物理结构预备知识（给算法读者）

要理解后面的"折叠/布局/压缩"，先看一个标准单元在硅上的典型结构：

![标准单元物理结构](D:/AutoCellLibX/doc/figures/cell_structure.png)

- **上下两条金属轨**：VDD（顶）和 GND（底），宽度由 `supplysize`（0.72 µm）决定，负责供电；
- **N 阱**在上半区（`nwellpos`=1.14 µm 以上），里面是 **P 扩散区**，放 **PMOS**；
- **N 扩散区**在下半区，放 **NMOS**；
- **竖直的 Poly 条**是晶体管的**栅**，同时穿过 P 扩散和 N 扩散（同一根栅控制一对 P/N 管）；
- **水平的 MET1 轨道**在扩散区之间，用于单元内部互连；
- **行高 H = rowheight(13) × vGrid(0.20) = 2.6 µm** 固定，所以**单元宽度就是要优化的量**。

理解这张图后，ASTRAN 的核心目标就一句话：**在固定行高内，把所有晶体管摆下、连好，并让单元尽可能窄**。

### 4.3 autoflow 七阶段总览

`AutoCell::autoFlow` 用状态机强制按以下顺序执行（每步都对应上面物理结构的一个决策）：

![ASTRAN autoflow 七阶段](D:/AutoCellLibX/doc/figures/astran_autoflow.png)

> 失败重试：`autoFlow` 会在失败时把布线轨道数从 2 加到 4、把保守系数 `conservative` 从 0 加到 4 重试；全部失败才抛 `AstranError("Could not generate cell layout automatically")`。前端捕获后**只排除该单元**，不中断整个基准（见 §5.5）。

### 4.4 阶段详解

**① select（选中并展平）**
`selectCell` 选中目标单元，`getFlattenCell` 把层次化网表**展平**成纯晶体管网表（因为复杂单元的 `.sp` 里其实嵌套了原始单元的子电路引用）。

**② calcArea（几何初始化）**
根据 `rowheight × vGrid` 算出单元高度，确定 P/N 扩散区的 Y 范围、电源轨位置，并生成可用的水平金属轨道列表 `trackPos[]`。

**③ foldTrans（晶体管折叠）**
如果某个晶体管的**宽度超过扩散区的可用高度**（太"胖"放不下），就把它**拆成多条并联的"腿"**（`width → width/n`，共 n 条），既降低单个扩散区的占用，又保持总驱动能力不变。对**串联**的晶体管链，`seriesFolding` 会保证整条链被一致地拆分，让各腿在竖直堆叠中对齐。

![晶体管折叠](D:/AutoCellLibX/doc/figures/folding.png)

**④ placeTrans（晶体管排序/布局）**
决定 P、N 两排晶体管的**排列顺序**。目标是让"同一根栅信号控制的 P 管和 N 管"尽量对齐（栅对齐能共享 poly，省宽度）。算法是 **ThresholdAccept**（一种模拟退火的确定性变体，`cellnetlst.cpp:566`），通过交换/移动排序里的条目来扰动解，用下面的代价函数评估：

```
cost = localCongestion + 100 × ( congCost·maxCongestion      # 布线拥塞
                                + gmCost  ·gateMismatch       # 栅失配数
                                + ngCost  ·gaps               # 空隙
                                + rCost   ·routingLength      # 布线长度(网包围盒)
                                + wCost   ·width )            # 预估宽度
```

`autoFlow` 会先做一次便宜的试探性布局+布线来估价，再做"多次尝试取最优"的正式布局。

> 一个实现细节（也是历史 bug 源）：当 P、N 两排晶体管**数量不等**时，短的一排会用 `link=-1` 的 **GAP 占位**补齐到等长。任何按序号读晶体管的代码都必须跳过 GAP，否则会读到 `trans[-1]` 越界（NOR3X1 就是 P6/N3 不等，曾因此崩溃）。详见 [AUDIT_REPORT.md](AUDIT_REPORT.md) §5.9。

**⑤ route（单元内布线）**
用 **GraphRouter**（一个 Pathfinder 风格的迭代拆线重布迷宫路由器，`graphrouter.h`）把单元内部的信号连起来：每条网络先布线，若某资源被多条网络占用（冲突）就拆掉重布，历史代价随迭代累积以逼走拥塞；布完后再加 Steiner 点优化线长。布线的对象包括扩散区、poly 栅、MET1 轨道和 I/O 引脚。

**⑥ compact（压缩）** —— 这是面积收益的关键
布线后的版图是"合法但松"的。压缩把每个几何图元的左/右/上/下坐标都建成变量（`x_i_a, x_i_b, ...`），把"相邻图形间距 ≥ 工艺规则""不能重叠""对齐到网格"等建成约束，把**单元总宽度**作为优化目标，形成一个 **ILP/LP 模型**写出到 `ILPmodel.lp`，调用外部求解器求解后读回坐标：

![ILP 压缩](D:/AutoCellLibX/doc/figures/compaction_lp.png)

目标函数的写法：`width = width_gpos × hGrid`（把宽度吸附到网格），以权重 5000 最小化 `width`，同时叠加若干小的优先级项。模型规模：一个 30 管的复杂单元约 **1.9 万变量 / 3.2 万约束**（COMPLEX1 实测）。

> 求解日志（`COMPLEX1.Astranlog` 尾部）：
> ```
> -> Compacting layout...
> -> Calling LP Solver (18978 variables, 32004 constraints)
> -> Running command: ".../gurobi_cl.cmd" TimeLimit=3600 ResultFile=ILPmodel.sol ILPmodel.lp
> -> Solver status OptimizationStatus.FEASIBLE, objective 8.22586e+06
> -> Cell Size (W x H): 4 x 2.6
> ```

**⑦ export（导出）**
把最终几何按层映射表（`GDSIILTable.txt`）写成 GDSII，并在日志打印 `-> Cell Size (W x H): <宽> x <高>`——前端就是读这一行拿宽度（`Astran.loadAstranArea`）。

### 4.5 确定性、复杂度与排障入口

- **确定性**：ASTRAN 本身**没有 `srand()`**，同一二进制 + 同一网表 → 同一版图。所以任何宽度变化都来自代码/网表改动，而不是随机噪声——这对二分定位很有用。
- **耗时**：`autoflow` 的大头是布局（模拟退火）+ 压缩（LP 求解），单单元约 **5–10 分钟**。适配层给单次求解设了 300 s 上限 + 2% 相对 gap（这只影响"压得多紧"，不影响合法性，因为压缩作用于已合法版图）。
- **排障**：单元缺失或宽=0 时，`grep "no usable LP solution"` 与 `Cell Size` 日志行是第一线索（见 §5.5）。

---

## 5. 前后端接口契约

前后端**只靠文件交互**，因此"契约"就是一组文件格式与约定。理解它们，就理解了系统最脆弱也最容易出错的地方。

![前后端接口契约](D:/AutoCellLibX/doc/figures/interface_contract.png)

### 5.1 `.run` 脚本模板（前端 → ASTRAN）

`Astran.buildAstranCommands` 生成（真实示例 `outputs/adder/COMPLEX1.run`）：

```
set lpsolve "<repo>/tools/gurobi_cl/gurobi_cl.cmd"
load technology "<repo>/tools/astran/build/Work/tech_freePDK45.rul"
load netlist    "<...>/outputs/adder/COMPLEX1.sp"
set rowheight 13
set grid 0.2 0.2
set supplysize 0.72
set nwellpos 1.14
set celltemplate "Tapless"
cellgen select COMPLEX1
cellgen autoflow
export layout COMPLEX1 <...>/outputs/adder/COMPLEX1.gds
exit
```

**几何参数集中在 `Astran.py:54-59`**，是复现性的关键（AGENTS.md 第 2 条）：

| 参数 | 值 | 含义 |
|---|---|---|
| `ASTRAN_CELLS_HEIGHT` | 13 | 行高的轨道数 |
| `ASTRAN_HGRID/VGRID` | 0.20 / 0.20 | 网格间距（µm）；行高 = 13×0.20 = 2.6 µm |
| `ASTRAN_SUPPLY_SIZE` | 0.72 | 电源轨宽度（µm） |
| `ASTRAN_NWELL_POS` | 1.14 | N 阱下沿位置（µm） |
| `ASTRAN_CELL_TEMPLATE` | Tapless | 单元模板（无衬底接触柱） |

> 要换成别的行高（比如对齐 GSCL45 的 2.47 µm，即 13×0.19），**改这里并重新做 DRC 验证**，不要去改 ASTRAN 源码。

### 5.2 `.sp` 网表约定

- 端口顺序 = **插入序**（确定性的来源，见 §3.6）；
- 内部信号/晶体管用 `cl<k>#` 前缀隔离；
- 电源网络固定命名为 `VCC` / `GND`（ASTRAN 依此识别供电轨）；
- 文件只在内容变化时才写盘（mtime 可信）。

### 5.3 LP 模型与求解器契约（ASTRAN ↔ gurobi_cl）

- 命令行固定为：`"<solver>" TimeLimit=<t> ResultFile=ILPmodel.sol ILPmodel.lp`（`compaction.cpp:608`），工作目录即进程 cwd；
- `ILPmodel.lp` 是 CPLEX-LP 文本（`Minimize / Subject To / Generals / Binary / ...`）；
- `ILPmodel.sol` 是 `变量名 值` 的逐行文本，ASTRAN 读回并 `round()` 成坐标。

### 5.4 缓存契约（避免重复生成版图）

ASTRAN 很慢，所以前端缓存版图：**当 `COMPLEX<n>.gds` 缺失，或它比它的 `.sp` 更旧（网表已更新）时，才重新生成**（`Astran.astranLayoutIsStale`）。这条契约的两半必须同时成立：`exportSpiceNetlist` 幂等写盘（mtime 才能当"输入是否变化"的信号），`main.py` 据 mtime 判断失效。AGENTS.md 第 7 条专门记录了这条契约。

### 5.5 失败语义（必须"响亮"，不能静默）

- **求解失败**：求解器返回 `NO_SOLUTION_FOUND` 时，适配层会写一个全零解，ASTRAN 于是产出一个 **0×0 单元**。`main.py` 检测到宽度 ≤ 0 就**排除该模式**，绝不让它计入节省量（否则虚报收益）。
- **ASTRAN 完全失败**（5 次重试都不行）：抛异常，前端**只排除该单元**，不中断整个基准。
- **并发禁令**：**不要并行跑两个 ASTRAN**——`ILPmodel.lp/.sol` 写在共享的进程工作目录里，并行会互相覆盖，表现为随机的 UNBOUNDED / 0×0 / 秒退（AGENTS.md 已记录此坑）。

---

## 6. LP 求解器替换层：为什么是 CBC，难在哪

ASTRAN 原生调用的是商业求解器 **Gurobi** 的命令行 `gurobi_cl`。为了在开源环境复现，本仓库用 `tools/gurobi_cl/` 做了一个**同名兼容包装**：`gurobi_cl.cmd` → `gurobi_cl.py` → `python-mip` + COIN-OR **CBC**。难点不在"调用求解器"，而在 ASTRAN 生成的 LP 有三个"坑"，处理错就会静默产错版图：

1. **表达式混进变量名槽位**。ASTRAN 会把 `"b0_17_1 + b0_17_2 + b0_17_3"` 这样的**线性表达式**当成"变量名"写进 LP 列。CBC 的 CoinLpIO 读到这种列名会直接拒绝并回退成 `x0,x1,...`，导致整个模型和变量脱节（版图退化为 0×0）。**对策**：适配层自己解析 LP 文本，把表达式重命名为 `astranExprN` 并**补上显式定义约束** `astranExprN - b0_17_1 - b0_17_2 = 0`，保证模型语义等价。
2. **非有限（inf）系数**。ASTRAN 会成对写出同一表达式的定义约束，一条系数 `0.000000`、其孪生却是 `inf`（来自工艺规则 `A1M1=0` 导致的数值溢出，见 §6.3 of AUDIT_REPORT）。`inf` 的语义是"无界"，**对策是丢弃该项**；绝不能把它夹成大 M（1e9），那会把约束变成 `astranExpr = y + 1e9·x`，直接把模型做死。
3. **FEASIBLE 也是成功**。带 2% 相对 gap 时 CBC 返回 `FEASIBLE` 而非 `OPTIMAL`。若只认 `OPTIMAL`，就会写出空解、ASTRAN 读回全零、产出 0×0 单元。**对策**：`status ∈ {OPTIMAL, FEASIBLE}` 都算成功。

> **时间预算两段式**：CBC 在 ASTRAN 的大 M 模型（M=20000 µm）上"解得快、证得慢"。所以第一段 `GUROBI_CL_TIME_LIMIT`（默认 300 s）拿到可行解即停；只有**一个解都没有**时才追加 `GUROBI_CL_RETRY_LIMIT`（默认 900 s）。要可证明最优，请换真实 Gurobi。

---

## 7. 端到端算例：adder 基准

把上面所有环节串起来，看 `adder` 这个 32 位加法器基准的实际产物。

### 7.1 挖到的模式与版图

| 单元 | 尺寸（W×H，µm） | 晶体管数 | 模式码（patternExtensionTrace） |
|---|---|---|---|
| `COMPLEX0` | 2.0 × 2.6 | 14 | `[NAND2X1,NAND2X1,OR2X1]` |
| `COMPLEX1` | 4.0 × 2.6 | 30 | `[XNOR2X1,XOR2X1,OAI21X1]` |
| `COMPLEX9` | 3.6 × 2.6 | 26 | `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0` |
| `COMPLEX10` | 4.2 × 2.6 | 32 | `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0` |

每个模式还配有一张 `COMPLEX<n>.png` 子图可视化（前端用 networkx + graphviz/spring 布局绘制，见 §3.3）。

### 7.2 记录的结果

`bestRecord-adder`（最佳组合）：

```
106.2   <- 相比 ASTRAN 同高基线的总节省（µm² 等效）
13.25%  <- 占 ASTRAN 基线总面积的比例
89.68   <- 相比 GSCL 库的总节省
11.44%  <- 占 GSCL 总面积的比例
选中组合：COMPLEX10（59 次出现 × 5 单元）
```

`bestRecord-seperateadder`（逐模式明细，第二轮产出）：

| 设计总面积 | 节省 | 节省率 | 次数 | 模式大小 | 覆盖 | 单元 | 模式码 |
|---|---|---|---|---|---|---|---|
| 783.94 | 106.2 | 13.25% | 59 | 5 | 295 | COMPLEX10 | `…+XNOR2X1_c0o0+OAI21X1_c2o0` |
| 783.94 | 72.0 | 8.98% | 60 | 4 | 240 | COMPLEX9 | `…+XNOR2X1_c0o0` |
| 783.94 | 48.8 | 6.09% | 61 | 3 | 183 | COMPLEX0 | `[NAND2X1,NAND2X1,OR2X1]` |
| 783.94 | 0.0 | 0.0% | 54 | 3 | 162 | COMPLEX1 | `[XNOR2X1,XOR2X1,OAI21X1]` |

> 注（口径）：该表中"设计总面积"列是 **GSCL 库**总面积（oriArea=783.94），而"节省率"列是相对 **ASTRAN 基线**总面积（801.8）算的（工具输出如此，两者分母不同）。`bestRecord-adder` 里则把两个口径分别列出（106.2/13.25% 对 ASTRAN，89.68/11.44% 对 GSCL）。

### 7.3 结果解读与注意事项

- **怎么读**：模式越大、出现越多，节省越多；`COMPLEX10` 由 `COMPLEX9` 再吸收一个 `OAI21X1` 生长而来，覆盖了更大的子电路，所以单模式节省最高。`COMPLEX1` 节省为 0，说明这个模式合并后并不省（合并版图的宽度没比并排小），于是被排除在最佳组合外。
- **注意事项（重要）**：`COMPLEX<n>` 的 **id 是每次运行临时分配的，不稳定**——同一个 id 在不同运行里可能指代不同模式。因此 `bestRecord-*` 里的 id↔模式映射**只对当次运行有效**，不要拿它和磁盘上的文件死板对应（AGENTS.md 第 6 条）。此外，绝对的"每单元宽度"会随工具链版本（例如压缩约束的健全性修复）有 ±0.2 µm 级别的变化，所以**跨工具链版本对比宽度要谨慎**；但"哪些模式值得合并、节省量级多大"的结论是稳定的。

---

## 8. 复杂度与性能工程

| 环节 | 复杂度 / 耗时 | 工程手段 |
|---|---|---|
| 图构建 + 初始聚类 | 每个单元一次 O(度) 的树编码，近似线性 | 只保留 Top-30 模式 |
| 模式生长 | 每轮遍历当前模式所有实例的边界邻居 | 一次只吸收一类邻居；簇大小 < 11 截断 |
| ASTRAN 单单元 | **5–10 分钟**（布局退火 + LP 压缩） | 版图缓存（§5.4）；只给有前景的模式生成 |
| LP 求解 | 单模型最多 300 s（+900 s 兜底） | 2% gap；FEASIBLE 即接受 |
| 整体 | 论文：单基准 ≤ 1.1 小时、≤ 5 个复杂单元 | 贪心组合，收益递减即停 |

性能上的两条硬约束：**不要并行跑 ASTRAN**（共享 LP 文件，§5.5）；**改端口顺序/几何常量会改变版图**，必须逐单元实测（§3.6、§5.1）。

---

## 9. 工程不变量与已踩坑（给要改代码的人）

本节是"算法相关的"不变量速记，完整且带证据的版本见 [AGENTS.md](../AGENTS.md) 与 [AUDIT_REPORT.md](AUDIT_REPORT.md)：

1. **面积 = 宽度，且必须同高**（§3.7）。新增面积来源时，返回宽度。
2. **几何参数集中在 `Astran.py`**，不改 ASTRAN 源码（§5.1）。
3. **LP 里表达式要"重命名 + 显式定义约束"**，不能塌缩成自由变量；不要用 `Model.read()` 读这份 LP（§6）。
4. **FEASIBLE 算成功**；**inf 系数丢弃**；**0×0 版图排除**（§5.5、§6）。
5. **模式身份 = `patternExtensionTrace` 字符串**，去重必须比对 trace（比对整型 id 会恒真、等于没去重）。
6. **`COMPLEX<n>` id 每次运行都变**，别手改产物、别假设 id↔模式映射稳定（§7.3）。
7. **版图缓存的键是网表**：`.sp` 更新（mtime）就必须重生成 `.gds`（§5.4）。
8. **ASTRAN 与 Python 流程都要确定性**：同一输入 → 同一输出（§3.8、§4.5）。
9. **P/N 数量不等是 ASTRAN 的地雷**：读晶体管前跳过 `link=-1` 的 GAP（§4.4 ④）。

---

## 10. 可扩展方向

| 方向 | 现状 | 要做的事 |
|---|---|---|
| **与 GSCL45 行高精确对齐** | 当前 2.6 µm vs 库 2.47 µm | 把 `ASTRAN_VGRID` 调到 0.19（13×0.19=2.47），重做 DRC |
| **GDS 层号重映射** | ASTRAN 与 GSCL45 层号体系不同 | 用 `set technology gdsii` 或后处理统一，才能并入一个 GDS |
| **更强的求解器** | CBC 在超大模型上不遵守时间上限 | 换真实 Gurobi（环境变量已支持时限） |
| **GNN 引导聚类** | 已注释掉 | 恢复 TF 依赖与导入（§3.9） |
| **逻辑级子图优化** | 未实现（README TODO） | 在挖掘阶段引入逻辑等价变换 |
| **支持 ASAP7 等新 PDK** | 未支持 | 重新标定几何常量与工艺规则文件 |

---

## 11. 附录

### A. 关键文件清单（按职责）

| 文件 | 一句话职责 |
|---|---|
| `pySrc/main.py` | 主循环：挖掘→生长→评估→导出的编排 |
| `pySrc/BLIFPreProc.py` | 解析 liberty/BLIF、构图、树编码、初始聚类 |
| `pySrc/BLIFPatternGrowth.py` | 模式生长（吸收邻居） |
| `pySrc/BLIFGraphUtil.py` | 数据结构 + 模式子图可视化 |
| `pySrc/spice.py` | 复杂单元 SPICE 网表拼装 |
| `pySrc/Astran.py` | ASTRAN 调用 + 几何常量 + 宽度读取 + 缓存判定 |
| `pySrc/GDSIIAnalysis.py` | 基线/库单元宽度读取 |
| `pySrc/regenerate_cells.py` | 按名重生成指定单元版图（不重跑挖掘） |
| `tools/astran/src/autocell2.cpp` | ASTRAN autoflow 主流程（fold/place/route/compact） |
| `tools/astran/src/compaction.cpp` | ILP/LP 模型写出与求解器调用 |
| `tools/gurobi_cl/gurobi_cl.py` | LP 解析 + python-mip/CBC 求解 + .sol 写出 |

### B. 术语表（中英对照）

| 中文 | 英文 / 代码符号 | 说明 |
|---|---|---|
| 模式 | pattern / `patternExtensionTrace` | 一段频繁出现的子电路，身份是其编码串 |
| 模式簇 | `DesignPatternCluster` | 同构子图的一个实例集合 |
| 模式序列 | `DesignPatternClusterSeq` | 同一模式的所有簇 |
| 复杂单元 | COMPLEX cell / `COMPLEX<n>` | 合并后的新单元 |
| 折叠 | folding / `foldTrans` | 把过宽晶体管拆成多条并联腿 |
| 布局（单元内） | placement / `placeTrans` | 决定 P/N 晶体管排列顺序 |
| 布线（单元内） | routing / `route` | 单元内部信号互连 |
| 压缩 | compaction / `compact` | ILP 最小化单元宽度 |
| 扩散共享 | diffusion sharing | 相邻晶体管共享源/漏，省面积 |
| 行高 | row height（2.6 µm） | 固定，面积 ∝ 宽度 |
| 模拟退火变体 | ThresholdAccept | placeTrans 的优化器 |

### C. 数据格式速查

| 格式 | 用途 | 本文示例 |
|---|---|---|
| `.blif` | 门级网表（技术映射后） | §1.2 输入；`benchmark/blif/adder.blif` |
| `.lib` | Liberty 时序库（引脚/方向） | §3.1 解析 |
| `.sp` | 晶体管级网表 | §3.6 导出；§5.2 约定 |
| `.run` | ASTRAN 脚本 | §5.1 模板 |
| `.lp` / `.sol` | LP 模型 / 解 | §5.3、§6 |
| `.gds` | GDSII 版图 | §4.4 ⑦ |
| `.Astranlog` | ASTRAN 日志（含 `Cell Size`） | §4.4、§5.5 |
| `tech_freePDK45.rul` | 工艺规则 | §4.1；含间距/宽度/层映射 |
| `bestRecord-*` | 结果记录 | §7.2 |

### D. 配套文档导航

- 想快速了解**目录与模块** → [PROJECT_ANALYSIS.md](PROJECT_ANALYSIS.md)
- 想了解**缺陷审查与每处修复的证据** → [AUDIT_REPORT.md](AUDIT_REPORT.md)
- 想吸取**方法论经验**（为什么这些 bug 难发现） → [LESSONS_LEARNED.md](LESSONS_LEARNED.md)
- 想**改代码**（不变量、坑、工作流） → [AGENTS.md](../AGENTS.md)、[BUILDING.md](../BUILDING.md)

---

*本文插图均由 [figures/gen_figures.py](D:/AutoCellLibX/doc/figures/gen_figures.py) 以 matplotlib 生成，可重复再生成；算法描述以当前 `main` 分支代码为准。*
