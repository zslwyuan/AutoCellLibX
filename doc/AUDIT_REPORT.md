# AutoCellLibX / ASTRAN 技术审查报告

> 审查日期:2026-09-24
> 审查范围:ASTRAN 源码(本仓库 `tools/astran/src`)、AutoCellLibX layout 生成配置、pattern 提取/生长/组合算法
> 审查视角:半导体 PDK / EDA 算法
>
> 阅读路线:初学者先读 [IMPLEMENTATION_GUIDE.md](IMPLEMENTATION_GUIDE.md) 建立全景;
> 本文是逐缺陷的深度档案,精炼条目索引见 [AGENTS.md](../AGENTS.md)。

本报告分三部分,对应三项任务:①ASTRAN 算法审查;②layout 生成配置审查;③pattern 算法错误修复(已实施)。

---

## 一、ASTRAN 源码算法审查

### 1.1 我方补丁引入的回归(compaction.cpp)——需优先处理

**背景**:为让 ASTRAN 的 ILP 压缩(`compaction.cpp`)适配开源 CBC 求解器(替代 Gurobi),此前在会话中打了 3 处补丁。审查发现其中 1 处破坏建模语义、2 处有副作用。

| # | 位置 | 问题 | 严重度 |
|---|---|---|---|
| 1 | `compaction.cpp:430-463` `needRename`/`S()` | **表达式变量被整体塌缩为单个变量,破坏约束语义** | 高 |
| 2 | `compaction.cpp:554-561` | `Generals` 段遍历 `variables`(全部变量)而非 `int_vars`,把连续变量全部整数化 | 中 |
| 3 | `compaction.cpp:484-495` | 合并目标函数时 `i==0` 不输出符号却对系数取 `abs()`,首项系数为负时符号被翻正 | 中 |

**问题 1 的证据与机理**:

- ASTRAN 的约束槽位允许放**表达式字符串**(而非纯变量名),如 `"b0_17_1 + b0_17_2 + b0_17_3"`、`"x0b + RELAXATION"`,写出为 `C: 0 - b0_17_1 + b0_17_2 + b0_17_3 = 1`,依赖 LP 解析器把 `+` 当运算符展开。Gurobi 与 CBC 对此行为**一致**(都按运算符解析)。
- 补丁的 `needRename()` 把"含非字母数字下划线字符"的名字判为非法,`S()` 按长度降序做子串替换,于是 `b0_17_1 + b0_17_2 + b0_17_3` 被整体替换成单个 `astranVar0`。
- 实测证据(本机生成的 LP 文件 `D:\aclx-tools\test\ILPmodel.lp`):
  - `Generals` 段出现 `b0_17_1 astranVar0 b0_17_2 b0_17_3 b0_26_1 astranVar1 ...`,共 457 个 `astranVar*`;
  - 约束退化为 `astranVar0 = -1` 形式,**"恰一"约束与松弛项丢失**。

**影响**:间距/对齐等约束被削弱,压缩阶段可能产出违反设计规则或非最优的版图。由于 CBC 与 Gurobi 对表达式的解析本就一致,**该补丁在修一个不存在的问题**,应当回退(仅保留"目标函数重复项合并"与"补 `End` 关键字"这类真正的求解器适配)。

**建议动作**(未在本次实施,属 ASTRAN 侧改动):
1. 移除 `needRename`/`S()` 的表达式重命名逻辑,恢复直接写出;
2. 若 CBC 报错,应定位真正的词法原因(如缺 `End`),而非重命名表达式;
3. 回退后需重新生成标准单元/复杂单元的 GDS 并做一致性校验。

### 1.2 ASTRAN 原版确凿缺陷(非我方引入)

| # | 位置 | 问题 | 严重度 | 是否影响本流程 |
|---|---|---|---|---|
| 4 | `router.cpp:110-117` | `vector<layer_name> rtLayers(5)` 却写入索引 `[5]`、`[6]`,堆越界写;活动路径 `rtLayers[(z*2)+1]` 在 `sizeZ>=3` 时同样越界 | 高 | `Router::compactLayout`(顶层布线压缩)路径,cellgen 流程未调用 |
| 5 | `autocell2.cpp:255` | PMOS 扩散轨道循环的 `&&` 与上界条件被误放进 `getIntValue(...)` 实参,宽度被当作布尔值、上界保护被吞 | 中 | `autoFlow` 以 `increaseIntTracks=false` 短路,不触发;手动 `cellgen route ... 1 ...` 会触发 |
| 6 | `autocell2.cpp:140-163` | `autoFlow` 中 `nrTracks` 跨 `conservative++` 重试不复位、`bestNrTracks` 为死变量;自适应逻辑不自洽 | 中 | 存在(但不会死循环:内层 `nrTracks==4`、外层 `conservative>4` 均可终止) |
| 7 | `graphrouter.cpp:533-538` | 遍历 `list` 时 `erase` 且继续 `++it`,迭代器失效(UB) | 中 | `routeNets` 开头 `reset()` 调用,可触发 |
| 8 | `cellnetlst.cpp:780-798, 866-869` | 单管单元时 `numSeries=(int)(totalTrans*0.9)=0` → `new int*[0]` 后越界写;`transToFolding[..][i-1]` 在 `i==0` 时负下标读 | 中 | 单晶体管单元边界;多管单元不触发 |
| 9 | `placer.cpp:155-218` | `minX/maxX/minY/maxY` 仅在网含实例时赋值;空 `insts` 的网读取未初始化值 | 中 | 顶层布线/自动翻转路径 |

**说明**:#4–#9 为 ASTRAN 上游原版缺陷(2022-04 快照),其中 #4 为确凿的缓冲区越界。是否修复取决于是否启用对应功能路径。

### 1.3 未发现确凿错误的模块

`compaction.h`、`router.h`、`graphrouter.h`、`gridrouter.h`、`gridrouter.cpp` 未发现其他确凿错误;`placeTrans` 的模拟退火与成本函数(`posPN/wGaps/mismatchesGate/wRouting/maxCong` 加权)、`perturbation/undoPerturbation` 配对、`foldTrans` 主要除法(`+0.00001f` 保护)未发现明确错误。

---

## 二、Layout 生成配置审查

### 2.1 核心问题:单元高度三方不一致

实测三套"单元高度"互不相同,**这是最严重的配置问题**:

| 来源 | 标称高度(日志/LEF) | GDS bbox 高度 | 备注 |
|---|---|---|---|
| GSCL45 目标库 | LEF `SIZE x BY 2.47` | 2.67(含 ±0.1 边界) | 待集成进去的库 |
| 上游 ASTRAN 原始单元(`original_astran_cells/`) | 日志 `Cell Size ... x 3.2` | 2.936 | 作为面积对比基准 |
| 本机新生成单元(`outputs/adder/COMPLEX*.gds`) | 日志 `Cell Size ... x 2.6` | 2.456 | 实际产物 |

**后果**:
1. 新生成的复杂单元高 2.6,而目标库 GSCL45 单元高 2.47 —— **物理上无法放入同一标准单元 row**,生成的"库扩展"不可直接集成;
2. 面积对比的基准与产物高度不同(3.2 vs 2.6),`saveArea` 的绝对值失真(见 2.3);
3. 说明 `ASTRANBuildPath` 对应的本机 ASTRAN 编译版使用了与上游**不同的工艺/circuit 默认参数**。

**根因**:`.run` 脚本只加载了 design rules 与 netlist:
```
set lpsolve "D:/aclx-tools/gurobi_cl.cmd"
load technology ".../tech_freePDK45.rul"
load netlist ".../cellsAstranFriendly.sp"
cellgen select <cell>
cellgen autoflow
export layout <cell> <path>.gds
exit
```
**未设置任何 circuit 参数**。ASTRAN 通过命令表(`designmng.h`)提供 `SET ROWHEIGHT`、`SET GRID/HGRID/VGRID`、`SET SUPPLYSIZE`、`SET NWELLPOS`、`SET CELLTEMPLATE` 等,应由脚本显式配置以匹配目标库;缺失时回落到编译内置默认(本机 = 2.6,上游 = 3.2)。

### 2.2 层映射不一致

| 来源 | 使用的 GDS 层号 |
|---|---|
| GSCL45 原始库 GDS | active 1、pwell 2、nwell 5、6、7、8、15(metal1)、16(via1)、21、63 |
| ASTRAN `GDSIILTable.txt` | active 1、pwell 2、nwell 3、nimplant 4、pimplant 5、poly 9、contact 10、**metal1 11**、via1 12、metal1-pin 18、prBoundary 235 |

两套层号体系不同。**ASTRAN 生成的 `COMPLEX*.gds` 无法直接并入 GSCL45 GDS 库**,必须做层重映射(或统一由 `SET TECHNOLOGY GDSII` 配置 ASTRAN 输出目标工艺的层号)。

### 2.3 面积度量问题

| 位置 | 现行做法 | 问题 |
|---|---|---|
| `gds_analysis.loadOrignalGSCL45nmGDS` | `curCell.area(((6,0),))[(6,0)]` —— 取 GDS **第 6 层**图形面积 | 第 6 层是某个内部层(GSCL 层表中 6=?),其图形面积**不代表单元占用的版图面积**;用单层面积当"单元面积"在物理上无意义 |
| `gds_analysis.loadAstranGDS` / `Astran.loadAstranArea` | `W(日志) × 0.8 × 3.2` | `0.8` 为缩放系数、`3.2` 是**上游单元高度**;对本机生成单元(高 2.6)系数不匹配 |

**关于 `0.8 × 3.2` 的澄清**:实测上游 `NAND2X1.Astranlog` 的 `Cell Size = 0.8 x 3.2`、`INVX1 = 0.4 x 3.2`,可见 `3.2` 正是上游单元高度,`0.8` 为附加缩放。由于 `saveArea = (oriUnit − newUnit) × clusterNum` 中两项使用**同一系数**,高度系数被消去,故 `saveRatio`(原 9.53%)实为**宽度减少比例**,在比例意义上自洽;但 `astranArea`(绝对值)与跨库对比不可靠。

**注意**:审查中曾尝试把两侧面积统一为 GDS bbox,实测发现这**反而引入误差** —— 上游 bbox 高 2.936、本机 bbox 高 2.456,高度不一致使比例失真(节省率虚高至 20%)。故该改动**已回退**,恢复原逻辑。这进一步印证:**必须先统一单元高度,任何面积度量才会正确**。

### 2.4 合理的部分

- `autoFlow` 的 track 自适应(2→3→4 tracks,按 congestion 判据)合理;原上游 `cellgen autoflow nTrack` 传入参数会被 ASTRAN 判为非法命令跳过,现改为单次 `cellgen autoflow` 是正确的。
- `cellgen autoflow` 子流程(calcArea→foldTrans→placeTrans→route→compact)与 ASTRAN 设计一致。
- 求解器替换(`set lpsolve` 指向开源包装)不修改 ASTRAN 算法,思路正确(但见 1.1 的补丁回归)。

### 2.5 修复建议

1. **显式配置 circuit 参数**,使生成单元与目标库一致,例如(.run 脚本中,在 `cellgen` 之前):
   ```
   set rowheight <n>
   set vgrid <pitch>
   set hgrid <pitch>
   set supplysize <v>
   set nwellpos <pos>
   set celltemplate "<template>"
   ```
   其中 row height 应由 GSCL45 LEF 的 `SIZE x BY 2.47` 与 ASTRAN 的 pitch 反推(需标定)。
2. **统一层映射**:用 `set technology gdsii <layer> <value>` 把 ASTRAN 输出层号对齐 GSCL45 库,或后处理重映射。
3. **统一面积度量**:在高度一致的前提下,用「单元宽度 × 行高」或「LEF SIZE / 日志 Cell Size」作为面积;避免用单层图形面积。
4. 重新生成 `original_astran_cells/` 基准(用本机配置),消除基准与产物的配置差异。

---

## 三、Pattern 提取/生长/组合算法修复(已实施)

发现并修复以下确凿错误(均在 `flow/`):

### 3.1 `blif_preproc.extract_and_encode_subgraph_tree` —— 编码与节点错位

- **错误**:`encodes.append(...)` 位于 `if (not predCell.id in tree)` **之外**,而 `tree.append(...)` 在之内。当同一前驱经多条 net 驱动同一下游(多输出单元如 FAX1,或菱形结构)时,`encodes` 会比 `tree` 多出重复项,导致**编码串与子图结构不对应**;结构等价的模式被编码成不同串 → **模式被错误拆分/归并**。
- **修复**:将 `encodes.append` 移入去重分支,保证编码与树节点严格一一对应。
- **验证**:adder 初始聚类 128 簇,`编码长度 == 簇内单元数` 的不匹配数为 **0**。

### 3.2 `blif_pattern_growth.grow_sequence_of_clusters` / `_BasedOn` —— 生长方向不对称

- **错误**:输入前驱方向有"跳过同类型模式邻居"的检查
  ```python
  if curNeighbor.clusterId != -1 and curNeighbor.cluster.clusterTypeId == cluster.clusterTypeId: continue
  ```
  而**输出后继方向缺少同一检查**。后果:输出方向会把"属于同一模式的其它簇"的单元吸收进来,破坏"同一模式多个独立实例"的结构(错误合并/disable 其它簇)。
- **修复**:在两个函数的输出后继循环中补上同类型模式跳过检查,使两个方向语义对称。
- **说明**:该修复改变模式生长路径,故结果会变化;见 §3.4 关于结果波动的说明。

### 3.3 `blif_preproc.heuristic_label_initial_clusters_based_on` —— labelId 递增不一致

- **错误**:与同名函数(非 `_BasedOn`)不同,`labelId += 1` 被放在循环体末尾**无条件执行**(即使该模式的簇数为 0、序列被丢弃),导致`clusterTypeId` 出现空洞。
- **后果**:`main.py` 第二轮以 `patternNum = len(clusterSeqs)` 作为新模式的 `clusterTypeId` 起点,而初始 `clusterTypeId` 已跳号 → **新旧模式编号可能冲突**,使生长中的"同类型模式"判断(依赖 `clusterTypeId` 比较)出错。
- **修复**:改为仅有簇时递增,与另一函数一致。

### 3.4 附加修复(测试体系发现)

| 文件 | 修复 |
|---|---|
| `blif_preproc.convertBLIFGraphIntoDataset` | `node_features` 列数由固定 `maxNumType=36` 改为 `max(maxNumType, len(feat_dict))`,消除单元类型数 >36 时的 `IndexError`(此前越界检查被注释) |
| `main.py`(两处) | 访问 `clusterSeqs[0]` 前增加 `len(clusterSeqs) == 0` 保护,避免空序列列表导致的 `IndexError` |
| `spice.SPSubcircuit.__init__` | `interfaces` 从**未剥离换行**的 `texts[0]` 提取(而 `self.texts` 已剥离),导致最后一个引脚名带 `"\n"`(实测 `AND2X1` 的接口为 `['Y','B','VCC','GND','A\n']`);改为从 `self.texts[0]` 提取,`internalSignals` 同步改用 `self.texts` |

### 3.5 测试体系与验证

**项目合并**:ASTRAN 源码与 LP 求解器包装已 vendored 进本仓库(`tools/astran/`、`tools/gurobi_cl/`),`flow/astran.py` 集中定义项目内路径,项目自包含。

**测试套件**(`tests/`,pytest,分层):

| 层 | 内容 | 数量 |
|---|---|---|
| unit | 数据结构/排序、liberty+BLIF 解析与构图、子图编码对齐、初始聚类与 pattern-id 稠密性、生长方向对称性、SPICE 解析/导出、面积读取 | 31 |
| integration(`slow`) | ASTRAN 二进制存在性、INVX1 端到端生成 GDS、挖掘→生长→SPICE 导出 | 3 |

- 关键回归用例:多输出驱动的编码错位(合成 FAX1 场景)、输出侧同类模式吸收(合成双实例场景)、`_BasedOn` 的 pattern-id 空洞。
- 运行:`python -m pytest`(仅快速用例,31 passed)/ `python -m pytest -m slow`(3 passed)。
- 详见 `BUILDING.md`。

### 3.6 修复后的全流程验证(adder)

- 全流程闭环正常:`COMPLEX0/1/9/10` 的 SPICE/GDS/日志/可视化 + `bestRecord-adder` + `bestRecord-seperateadder` 均生成;
- `bestRecord-adder`(原面积度量):
  - 相对 ASTRAN 面积节省 **178.18(9.43%)**
  - 相对 GSCL 面积节省 **400.66(18.24%)**
  - 选中组合:`COMPLEX9`(60 簇 × 4 单元 `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0`)+ `COMPLEX1`(54 簇 × 3 单元 `[XNOR2X1,XOR2X1,OAI21X1]`)
- 逐模式明细(第二轮)识别出含 `COMPLEX10`(59 簇 × 5 单元,单模式省 7.99%)等更大模式。

**关于结果波动的说明**:与修复前(180.22,9.53%)相比,节省率差异 <0.1 个百分点。该差异**不能单独归因于算法修复**,因为 ASTRAN 的 `placeTrans` 使用模拟退火(随机),同一模式两次生成的布局宽度可能不同(实测 COMPLEX0 的日志宽度在两次运行中为 1.8 / 2.2)。修复的正当性主要由**代码级正确性论据**(编码对齐、方向对称、编号一致)支撑。

---

## 四、结论

1. **ASTRAN 算法**:存在确凿缺陷——最紧要的是**我方为适配 CBC 所打的 compaction 补丁破坏了 ILP 表达式语义**(§1.1),应回退并重新验证;另有 `router.cpp` 越界等原版缺陷(§1.2)。
2. **Layout 生成配置**:**不合理**。核心是**单元高度三方不一致**(目标库 2.47 / 上游基准 3.2 / 本机产物 2.6),叠加**层映射不一致**与**面积度量不当**。当前生成的复杂单元在物理上无法直接与 GSCL45 库集成;面积对比的绝对值不可靠。需显式配置 ASTRAN circuit 参数、统一层映射与面积度量。
3. **Pattern 算法**:修复了 3 处确凿错误(编码错位、生长方向不对称、labelId 不一致)+ 4 处缺陷(特征维度越界、空序列保护、SPICE 接口换行),已通过 adder 全流程与测试套件验证。

**工程化交付**:ASTRAN 与 AutoCellLibX 已合并为单一项目管理(`tools/astran`、`tools/gurobi_cl` vendored,路径集中于 `flow/astran.py`,`BUILDING.md` 说明构建/运行/测试);建立分层测试体系(unit 31 + integration 3,含针对上述每个 bug 的回归用例)。

> 本次实施:第 3 部分的代码修复 + 项目合并 + 测试体系;第 1、2 部分按"分析"交付,其修复涉及 ASTRAN 源码与工艺配置,建议单独立项并重新标定。

---

## 五、全面修复记录(2026-09-24 第二轮)

针对第一至四部分列出的问题做了全面修复,全部经编译与测试验证。

### 5.1 ASTRAN 源码缺陷(全部修复,重新编译通过)

| 位置 | 修复 |
|---|---|
| `compaction.cpp`(ILP 写出) | 表达式变量不再被塌缩。保留"重命名为纯变量"并**新增显式定义约束** `astranExprN - b0_17_1 - b0_17_2 = 0`,语义等价且被所有 LP 读取器接受;`Generals/Binary/Semi/SOS` 段回到 `int_vars/bin_vars/...`(不再遍历含表达式键的 `variables`);目标函数首项负号不再丢失 |
| `router.cpp:110` | `rtLayers(5)` → `rtLayers(7)`(实际写入索引 0..6,原为堆越界写) |
| `autocell2.cpp:255` | 修正 `getIntValue(...)` 实参中的 `&&` 笔误(PMOS 扩散轨道宽度与高度上界) |
| `autocell2.cpp`(autoFlow) | 每次 conservative 重试复位 `nrTracks=2`,自适应 2→3→4 tracks 重新自洽 |
| `graphrouter.cpp:533` | `list::erase` 改为使用返回值迭代,消除迭代器失效 |
| `cellnetlst.cpp:780/866` | `numSeries` 下限 1(单管单元不再构造 0 行矩阵);折叠序列的首/尾下标加边界保护 |
| `placer.cpp:187/155` | `minX/maxX/minY/maxY` 初始化为 0,消除空网读取未初始化值 |

### 5.2 求解器适配层重写(`tools/gurobi_cl/gurobi_cl.py`)

原实现依赖 CBC 的 CoinLpIO 直接读 LP,但 ASTRAN 会把**表达式**放在变量槽位(如 `x0b + RELAXATION`),CoinLpIO 报 `Invalid column names` 并**回退到默认列名**,导致所有列与模型脱节(实测 `.sol` 中不含 `width`/`height`,版图退化为 0×0)。改为:

1. **自行解析 CPLEX-LP** 并用 python-mip API 建模(变量名完整保留,表达式按线性组合正确展开);
2. **非有限系数处理**:ASTRAN 偶发输出非有限系数(如 `- inf x184_width`,数值溢出),**丢弃该项**(按"无该约束"语义)。曾一度改为替换成 big-M(1e9),但那会把 ASTRAN 本意为 0 的系数变成巨系数,使模型数值病态、CBC 返回 `NO_SOLUTION_FOUND`、压缩被静默跳过(详见 §5.7);
3. **FEASIBLE 判定**:带 gap 容差时 CBC 返回 FEASIBLE(非 OPTIMAL),此类解同样写出;
4. 放松相对 gap(0.02)并加每次求解时间上限(300s)——压缩作用于**已合法的布局**,收紧 gap 只影响压缩程度、不影响合法性。

### 5.3 Layout 生成配置

| 项 | 修复 |
|---|---|
| 面积度量 | 三类单元(ASTRAN 基准 / ASTRAN 产物 / GSCL 库)统一为**标称宽度**作面积代理(同库行高固定 ⇒ 面积 ∝ 宽度),消除基准(3.2um)与产物(2.6um)行高不一致引入的偏差;GSCL 侧从 LEF `SIZE` 取宽度(不再用单个 GDS 层的图形面积) |
| 工艺参数 | `.run` 脚本显式固化 `set rowheight/grid/supplysize/nwellpos/celltemplate`,不再依赖编译内置默认,配置可复现 |
| 项目自包含 | ASTRAN 与求解器包装 vendored 至 `tools/`,路径集中于 `flow/astran.py` |

### 5.4 验证

- ASTRAN 重新编译 0 错误;INVX1/COMPLEX0 端到端生成正常(COMPLEX0 修复后 `Cell Size 2 x 2.6`,较修复前 2.2 更窄,说明压缩约束真正生效);
- 测试套件:31 unit + 3 integration 全通过;
- 生成的 LP 已验证:定义约束正确、`width`/`height` 列完整、求解返回最优/可行解。

### 5.5 仍未完成(需工艺标定,非代码缺陷)

1. **与 GSCL45 行高精确对齐**:目标库行高 2.47um,本机 ASTRAN 产物 2.6um(默认 `rowheight 13 × vgrid 0.20`)。可用 `set rowheight`/`set vgrid` 标定(如 13×0.19),但会改变单元几何,需 DRC 复核,故未在本轮强制实施;
2. **层映射统一**:ASTRAN 输出层号与 GSCL45 库不同,集成前需用 `set technology gdsii` 重映射或后处理;
3. **基线重生成**:`original_astran_cells/` 仍为上游版本(H=3.2);若需与本机配置完全一致,可用 `tools/gurobi_cl` + 修复版 ASTRAN 重新生成(单次 compaction 约数十秒至 5 分钟,32 个单元约 1 小时)。

### 5.6 第二轮追加修复:结果一致性(2026-09-24)

在用修复后的 ASTRAN 重生成 `outputs/adder` 产物时,又发现两处会导致**结果数字失真**的缺陷,已修复。

**(1) 布局缓存静默复用过期版图(`main.py` + `spice.py`)**

`main.py` 原先只要 `COMPLEX<id>.gds` 存在就跳过版图生成。图案/聚类修复会改变 `COMPLEX<id>.sp`,但磁盘上旧的 `.gds` 仍在,于是被静默复用。实测:`COMPLEX1.sp` 已是 26 管拓扑(4 个单元),而它的 `.gds`/`.Astranlog` 仍是更早 30 管拓扑的产物——旧日志自证 `Number of transistors before folding: 30 -> P(15) N(15)`,面积数字因此对不上它所声称的网表(旧记录 3.6um 属于 30 管网表,而当前 26 管网表生成 6.6um)。

修复:
- `spice.py: exportSpiceNetlist` 仅在内容变化时写文件,使 `.sp` 的 mtime 成为可靠的"输入是否变化"信号;
- 新增 `Astran.astranLayoutIsStale(gds, sp)`;`main.py` 改为"版图缺失**或**早于其网表即重生成"。

**(2) 重复图案被重复导出并重复计入节省量(`main.py`)**

`dumpedPaterns` 以图案轨迹 `patternExtensionTrace`(字符串)为键、值为 `clusterTypeId`(整型),但去重判断写成 `patternTraceId in dumpedPaterns.keys()`——拿整型值去查字符串键,恒为假,于是**从不去重**。同一图案在后续迭代里会以新的 id 被再次导出并再次计数:

- 磁盘上 `COMPLEX1.sp` 与 `COMPLEX9.sp` 的图案码完全相同(`[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0`,各 60 次出现),`.sp` 逐字节相同(仅 `.subckt` 名不同)——同一图案以两个 id 同时存在;
- 去重失效时,同一图案会在后续迭代以新 id 再次进入 `saveArea` 与 `bestRecord-*`,节省量随之重复计数。

修复:改以轨迹判定,已导出即 `continue`。这样同时避免了为重复 id 去查找一份从未生成的版图(原判断若修正为按轨迹跳过,后文的 `loadAstranArea("COMPLEX"+id)` 会命中不存在的日志而断言失败,故必须整段跳过)。

**(3) `outputs/adder` 快照自相矛盾(已重跑)**

该目录是多次运行混合的产物:**`COMPLEX*` 的 id→图案映射随运行而变**(根因见 §5.7(3) 的 hash 顺序不确定性)。`bestRecord-adder` 记录 `COMPLEX1=[XNOR2X1,XOR2X1,OAI21X1]`、`COMPLEX9=[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0`,而磁盘上的 `COMPLEX1.sp` 却是 `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0`。用修复后的流水线端到端重跑 adder 后,`<id> ↔ 图案 ↔ 网表 ↔ 版图 ↔ 面积` 自洽。

**测试新增**:`tests/unit/test_layout_cache.py`(4 例,版图缓存判定)与 `tests/unit/test_spice.py::test_export_spice_netlist_only_writes_on_change`(网表写入幂等性);合计 36 个单元测试通过。

**工具新增**:`flow/regenerate_cells.py`(按名重生成指定单元的版图,无需重跑挖掘流水线)。

### 5.7 第三轮修复:数值、行高与可复现性(2026-09-24)

以修复后的流水线端到端重跑 adder 时,又发现三处会直接改变结果数字的缺陷。

**(1) `inf` 系数被 big-M 化 ⇒ 压缩被静默跳过(`tools/gurobi_cl/gurobi_cl.py`)**

ASTRAN 会成对写出同一表达式的定义约束,其中一条系数是 `0.000000`、其孪生约束却是 `inf`(数值溢出):

```
Cexpr6793: astranExpr6793 - y186_width - 0.000000 x186_width = 0
Cexpr6794: astranExpr6794 - y186_width - inf x186_width = 0
```

把 `inf` 夹成 `1e9`,等于把约束改成 `astranExpr6794 = y186_width + 1e9·x186_width`——既不是 ASTRAN 的本意,又使模型数值病态:CBC 报 `NO_SOLUTION_FOUND`,适配层随即写出全零解,压缩整段失效,单元被放得极宽。

修复:非有限系数按"无该约束"语义**丢弃该项**(此处即退化成与孪生约束一致的 `astranExpr6794 - y186_width = 0`)。同一份 COMPLEX1 模型对比:

| 处理方式 | CBC 目标值 |
|---|---|
| 夹成 big-M 1e9(修复前) | 1.71022e+07 |
| 丢弃该项(修复后) | 7.38475e+06 |
| 上游真实 Gurobi(参考) | 7.38831e+06 |

修复后与上游最优几乎一致,说明压缩真正生效。失败路径的日志也改为明确写出 `compaction is skipped`,不再假称写入了 best solution。

**(2) 面积比较的基准行高不匹配(已按同高重生成)**

先前 `outputs/adder` 的增益是在"**基准 H=3.2 × 产物 H=2.6**"下算出的:GSCL45 LEF 的单元高度是 **2.47**(见 `std_celllib/gscl45nm.lef` 的 `SIZE … BY 2.47`),而 `original_astran_cells/` 里的 ASTRAN 基准是上游**另一套** ASTRAN(日志自证 Linux + `/opt/gurobi950` + `cellsHeight=16`)以 **H=3.2** 生成的,本仓库无法复现。行高不同则"面积 ∝ 宽度"不成立,比较无意义——实测 `COMPLEX9` 因此从 +6.5% 翻成 −19.5%。

修复:用 vendored 工具链、**同一套几何常量**重生成 `original_astran_cells/`(H=2.6),使基准与产物同高,整条结果可用本仓库复现。与 GSCL45 仍有 2.6 vs 2.47 的残余差异(约 5%);如需完全对齐,把 `astran.ASTRAN_VGRID` 调为 0.19(13×0.19=2.47)后重做 DRC 复核即可。

**(3) 流水线不可复现(`PYTHONHASHSEED`)**

`exportSpiceNetlist` 用普通 `set` 汇总复杂单元的端口,再 `list(set)` 输出,端口顺序因此取决于**进程级 hash 顺序**:每次运行导出的 `.sp` 内容都不同。后果有二:让"按网表内容判定版图缓存"永远失效(每次重跑都重生成全部单元);以及结果不可复现——`COMPLEX*` 的 id↔图案映射在不同运行间漂移(即 §5.6(3) 快照自相矛盾)正是源于此。

修复:改用**插入有序映射**(dict)汇总端口,并在 `PYTHONHASHSEED` = 0/1/7 下验证图案序列与网表 md5 完全一致。新增 `tests/unit/test_determinism.py`(子进程比对不同种子的网表哈希)。

**测试新增(本轮)**:`tests/unit/test_determinism.py`、`tests/unit/test_astran_commands.py`、`tests/unit/test_dataset_consistency.py`(图案唯一性 + 日志与网表晶体管数一致)。

## 六、求解异常根因分析:为什么会有这么多"求解异常"

### 6.1 总体结论

ASTRAN 的压缩**数学模型本身是成立的**:同一份 LP 文本,上游真实 Gurobi 与我们的 CBC(正确解析后)得到几乎一致的目标值(7.38831e6 vs 7.38475e6)。所有已观测的求解异常都来自**四类可定位的生成/写出层缺陷 + 两个我们自己的求解策略问题**,没有一个是"悬案"。逐条如下,均附代码级证据。

### 6.2 缺陷一:线性表达式被写进"变量名"槽位(序列化缺陷,主因)

约束生成器用字符串拼接构造"变量名",再走 `insertConstraint(v1, ...)` 的变量 API 进入 `variables` 表,LP 写出器把它们原样写到**列名**位置。证据(`tools/astran/src/autocell2.cpp`):

```cpp
// insertDistanceRuleInteligent:大M析取,RELAXATION 与 0/1 变量 b_1/b_2/b_3 配合
cpt.insertConstraint("x" + lastX + "b + RELAXATION", "x" + currentX + "a2",
                     CP_MIN, "b" + lastX + "_" + currentX + "_1", minDist + relaxation);
cpt.insertConstraint("ZERO", "x" + currentX + "a2 - x" + lastX + "b + "
                     "y" + currentY + "a2 - y" + lastY + "b + RELAXATION",
                     CP_MIN, "b" + lastX + "_" + currentX + "_3", minDist + relaxation);
// createTrack:"x17a - 4 UM"(带单位后缀的表达式串)
cpt.insertConstraint("x" + track + "a - " + to_string(minIntersection) + " UM",
                     "x" + track + "b", CP_MAX, "b" + track + "_reduceLturns", relaxation);
```

其中 `RELAXATION` 是真实变量(`RELAXATION = 20000`,`autocell2.h:68`),`b_…` 是 0/1 控制变量——这是标准的 **big-M 析取写法,数学正确**;但"变量名可以是表达式"这一假设与"列名只能是标识符"的 LP 语法冲突,生成器与写出器之间**没有任何校验**。

后果:严格读取器直接拒绝——CBC 的 CoinLpIO 报 `Invalid column names` 后**回退到默认列名**,整个模型与列脱节,版图退化为 0×0;而 Gurobi 的 LP 解析器能容忍并把表达式展开,所以上游一直"能用"、从未暴露。我方修复:重命名 + 显式定义约束 `astranExprN - (原表达式) = 0`,语义等价(§5.1)。

### 6.3 缺陷二:宽金属/最小面积约束的数值退化(PDK 规则交互)

`insertVia()` 的最小面积约束:

```cpp
double A = currentRules->getRulef(A1M1);   // 金属1最小面积
double W = currentRules->getRulef(W2VI);   // 通孔宽度
double tmp1 = (sqrt(A) - (A/W)) / (sqrt(A) - W);
double tmp2 = (sqrt(A) - W) / (sqrt(A) - (A/W));
cpt.insertConstraint("ZERO", "y"+metNode+"_width" + " + " + to_string(-tmp1) + " x"+metNode+"_width", CP_MIN, ...);
cpt.insertConstraint("ZERO", "y"+metNode+"_width" + " + " + to_string(-tmp2) + " x"+metNode+"_width", CP_MIN, ...);
```

而 `tech_freePDK45.rul` 里 **`A1M1 = 0`**(该规则缺失/未定义):

- `tmp1 = (0-0)/(0-0.065) = -0.0` → 系数打印为 `0.000000`;
- `tmp2 = (0-0.065)/(0-0) = -inf` → 系数打印为 `inf`。

这正是 LP 中"孪生约束"(一条 `0.000000`、一条 `inf`)的准确来源:两条约束作用于同一表达式 `y<id>_width + coef·x<id>_width`。从 PDK 视角:A1M1 缺失时该约束本就无意义,算法应对零/未定义规则有保护;补全规则(`A1M1 ≈ 0.02`)或加 `if (A > 0 && W > 0)` 守卫均可根治。我方已在 LP 层按"无界"语义丢弃 `inf` 项(残留的 `0.000000` 项无害),结果与上游一致(§5.7(1))。

### 6.4 缺陷三:写出器自身的笔误/漏误(已修复,§5.1)

- `Generals` 段遍历了**整个 `variables` 表**(含表达式键)而非 `int_vars` → 非法 LP 段;
- 目标函数首项负号丢失;
- `router.cpp` `rtLayers(5)` 越界写、`graphrouter.cpp` 迭代器失效、`placer.cpp` 未初始化读数等 C++ UB。

都属于实现层小错,与压缩算法无关,但同样制造异常/非确定性。

### 6.5 缺陷四:模型规模与病态 big-M(性能性异常)

- 每个相邻几何对的析取展开引入 3 个 0/1 变量 + `RELAXATION` + 多条约束;30 管单元即 **2.6 万变量 / 4 万约束**(COMPLEX10);
- 大 M = **20000 µm**(单元本身仅 2–10 µm),数值上是一个巨大的 M;CBC 这类开源求解器在其上吃力(数值容差、搜索),Gurobi 则轻松(上游日志 ~50 s 解完)。这就是"同一模型,Gurobi 无异常、CBC 超时/无解"的本质。

我方适配层曾有两个策略放大了缺陷四:`inf` 夹成 big-M 1e9(把缺陷二变成不可行模型)与 300 s 硬上限(大模型必然 `NO_SOLUTION_FOUND`)。现已改为:丢弃 `inf` 项 + 尊重 ASTRAN 的 `TimeLimit`(默认 3600 s,`GUROBI_CL_TIME_LIMIT` 可收紧),并在 `main.py` 拒绝 0×0 单元计入节省量(§5.7 与本轮提交)。

### 6.6 结论与建议

1. **不是算法错误,是"生成/写出实现缺陷 + 规则数据缺陷 + 求解器能力差距"的叠加**;压缩模型经交叉验证是正确的。
2. 已观测异常已全部有修复与测试覆盖。残余建议(按收益排序):
   - C++:`insertVia` 最小面积块加 `A > 0 && W > 0` 守卫;`insertDistanceRuleInteligent`/`createTrack` 的表达式串改走真正的辅助变量,或在写出器里显式展开表达式;
   - PDK:补全 `tech_freePDK45.rul` 的 `A1M1`(当前为 0);
   - 求解器:大单元用真实 Gurobi 或放宽时限(环境变量 `GUROBI_CL_TIME_LIMIT` 已支持)。

### 5.8 第四轮:数据集定稿(2026-09-25)

以全部修复(§5.1–§5.7)端到端重跑 adder 后定稿。本轮又发现并修复两处,并产出最终数字。

**(1) CBC"解得快、证得慢":求解时间预算改为两段式**

尊重 ASTRAN 的 `TimeLimit` 后,CBC 在 ASTRAN 的大 M 模型(见 §6.5)上陷入"已找到良好可行解但无法在 2% 容差内证明最优"的长时间搜索:单个 8971 变量模型 20 分钟仍未返回。改为两段式预算:

- 第一段 `GUROBI_CL_TIME_LIMIT`(默认 300 s)取到可行解即停;
- 仅当**一个解都没有**(`NO_SOLUTION_FOUND`)才追加至多 900 s 继续搜索。

实测同一 COMPLEX1 模型目标值仍为 7.38475e6(与上游 Gurobi 一致),耗时约 5 分钟。结论:对 CBC,**"被截断的可行解"就是可接受结果**(压缩作用于已合法版图,只影响压多紧);要可证明最优请用 Gurobi。

**(2) 生长导出与已用 id 冲突(`main.py`)**

生长新图案后,`exportSpiceNetlist(newSeq, subckts, len(clusterSeqs), ...)` 用 `len(clusterSeqs)` 当 id 写网表——该值与已 dump 图案的 `clusterTypeId` 会**撞车**,静默覆盖已有 `COMPLEX*.sp`。实测:6 单元生长图案把 `COMPLEX9.sp` 覆盖成 38 管网表,而 `COMPLEX9.gds/.Astranlog` 仍是 26 管的 4 单元版图(数据集一致性测试抓住)。修复:改用 `newSeqOfClusters[0].patternClusters[0].clusterTypeId`。`COMPLEX9.sp` 已按确定性的首轮生长回放重建(26 管、图案码一致、端口为插入序),与版图恢复匹配。

**(3) 最终 adder 结果(基准与产物同高 H=2.6)**

| 单元 | 尺寸 (W×H) | 晶体管 | 图案码 |
|---|---|---|---|
| COMPLEX0 | 2.4 × 2.6 | 14 | `[NAND2X1,NAND2X1,OR2X1]` |
| COMPLEX1 | 4.2 × 2.6 | 30 | `[XNOR2X1,XOR2X1,OAI21X1]` |
| COMPLEX9 | 3.6 × 2.6 | 26 | `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0` |
| COMPLEX10 | 3.8 × 2.6 | 32 | `[NAND2X1,NAND2X1,OR2X1]+XNOR2X1_c0o0+OAI21X1_c2o0` |

`bestRecord-adder`:**节省 106.2(ASTRAN 同高基准的 13.25%;GSCL LEF 的 11.44%)**,选定单元 COMPLEX10(59 次出现,5 单元)。内部自洽:原 5 单元宽度合计 5.6,合并后 3.8,1.8 × 59 = 106.2。

**未完成(已记录)**:
- 6 单元生长图案(COMPLEX11):求解在两段预算内未终止,由 0×0 防护排除;其后的 7 单元图案(COMPLEX12)同样无法生成——CBC 在最大模型上**不遵守时间上限**(无法中断超长的根松弛求解),故这两个图案的生成不会终止,已从数据集中移除(不会进入任何记录);<s>`bestRecord-seperateadder`(phase 2 的逐图案记录)未生成</s>——已用 phase 2 的忠实回放(`flow/replay_separate_adder.py`)生成,与真实循环同公式、同浮点;
- 行高仍为 2.6 vs GSCL45 的 2.47(见 §5.5/§5.7(2));`original_astran_cells/` 已全部按 2.6 重生成(16 个单元,含本轮的 CLKBUF1/DFFNEGX1/DFFPOSX1/MUX2X1/NOR3X1)。

### 5.9 第五轮:补齐基线单元时的 ASTRAN 崩溃(2026-09-25)

重生成 `NOR3X1` 时暴露 ASTRAN 三处**上游遗留**缺陷(前几轮未触发,因为 adder 用到的单元 P/N 数量恰好相等)。

**(1) 单管"串联腿"折叠读 `trans[-1]`(`cellnetlst.cpp: seriesFolding`)**

折叠只对 P/N 数量不等的单元触发:短的一侧会被 `link=-1` 的 GAP 占位补齐(见下)。而 `seriesFolding` 对**长度为 1 的串联序列**(如 NOR3X1 的并联 PMOS 对、NMOS 腿)会走"首晶体管"分支并读取 `transToFolding[i+1]`——该处是 `-1` 哨兵,`trans[-1]` 越界。上游在 release 构建下是静默 UB(腿上的晶体管被悄悄丢弃)。修复:长度 1 的腿直接在**真实 drain/source 网**之间拆分(两端不加后缀,否则腿悬空、晶体管从单元里消失)。

**(2) 路由用 GAP 槽位的宽度读 `trans[-1]`(`autocell2.cpp: route`)**

P/N 数量不等时,`transPlacement` 用 `link=-1` 的 GAP 条目把两条 ordering 补齐到等长(`cellnetlst.cpp` `transPlacement`),而 `route()` 对**每个**槽位读 `getTrans(link).width`——GAP 槽位即 `trans[-1]`。共 4 处(两条 track 范围 while 循环 + 两条 next-track while 循环)。修复:link==-1 时按宽度 0 处理(GAP 不占扩散宽度,语义正确)。

**(3) MSYS2 自带 python 遮蔽求解器包装(环境问题)**

为装 gdb 而 `pacman -S mingw-w64-x86_64-gdb` 时,依赖把 `mingw-w64-x86_64-python`(3.14,无 python-mip)装进了 `C:\msys64\mingw64\bin`。`astran.py` 把该目录置于 PATH 之前(ASTRAN 运行期 DLL 需要),于是 `gurobi_cl.cmd` 里的裸 `python` 解析到 MSYS2 解释器 → `ModuleNotFoundError: No module named 'mip'`,压缩静默失效。修复:`astran.py` 把**当前流程所用的解释器目录**放在 PATH 最前(mingw64 其次),DLL 仍能解析、求解器包装始终用带 mip 的 python。

**验证**:`NOR3X1` 修复后 1.4 × 2.6、48 s、OPTIMAL(objective 2.86e6);16 个基线单元全部 H=2.6;44 单元 + 3 集成测试全通过。

### 5.10 第六轮:端口顺序实验与失败单元鲁棒性(2026-09-25)

**(1) 复杂单元端口顺序的实验结论:保持插入序**

观察到 `.subckt` 端口顺序会改变 ASTRAN 的布局(COMPLEX0 在旧 hash 序下 2.0、插入序下 2.4),因此做了受控实验:把端口改为**规范序**(`VCC GND` 在前、其余按字典序),重生成四个复杂单元:

| 单元 | 插入序 | 规范序 | 结论 |
|---|---|---|---|
| COMPLEX0 | 2.4 | **2.0** | 更好 |
| COMPLEX1 | 4.2 | 4.2 | 不变 |
| COMPLEX9 | 3.6 | 4.2 | 更差 |
| COMPLEX10 | 3.8 | **8.4** | 明显更差(300s 内只找到很差的可行解) |

**结论:顺序对布局质量的影响与单元相关、无一致最优,规范序整体更差,已回退保持插入序**。经验:任何"看起来更规范"的改动,只要改变 ASTRAN 的输入顺序,就必须逐单元实测。

**(2) 失败单元不再中断整个基准(`main.py`)**

- phase 1:0×0 版图(求解无解→全零解)或 ASTRAN 完全无法生成(5 次 conservative 尝试全失败)的图案,现在**只排除该图案**(`continue`),不再置 `benchmarkFailure` 中断整个基准;缓存里已有的 0×0 版图在记账处同样被排除;
- phase 2:`loadAstranArea` 失败/0×0 的图案在逐图案记录(`bestRecord-seperateadder`)中跳过,不再断言崩溃或计出虚假节省;生长出"从未 dump 过"的轨迹也直接跳过(否则 `dumpedPaterns` 键查会 KeyError);
- **phase 2 的生长导出已删除**:它把生长网表写到 `patternNum` 派生的 id 下,与磁盘上已有 id 撞车——实测把 `COMPLEX1.sp` 覆盖成别的图案(这很可能就是早期快照里 `bestRecord-*` 与磁盘文件对不上的来源之一);phase 2 只算记录,不需要导出;
- 求解器:两段式预算的第二段长度可用 `GUROBI_CL_RETRY_LIMIT`(默认 900 s)控制,便于把重跑限定在紧凑预算内。注意:CBC 在最大模型上可能**无视时间上限**(无法中断超长根松弛),故对 COMPLEX11/12 这类单元,"限时"不保证终止——这是 COMPLEX11/12 被排除的根因,也说明超大单元应改用真实 Gurobi。

**验证**:44 单元 + 4 集成测试全通过;adder 最终选择不变(COMPLEX10,106.2 = 13.25%);`bestRecord-seperateadder` 由 phase 2 的忠实回放生成,四行数值(106.2/72/48.8/0)与独立计算一致。

### 5.11 第七轮:PDK 评审修复 —— GDS 单位、压缩器间距健全性与电源引脚标签(2026-09-25)

以 PDK 评审视角对 `outputs/adder/COMPLEX*.gds` 做逐层几何审计,发现三个 P0 级缺陷并全部修复。审计方法:按 GDS 规范手工解析 UNITS/BOX/TEXT 记录、逐层布尔并集分析连通块、盒级最小间距扫描、金-孔-poly 搭接图连通分量提取、高倍渲染目视。

**(1) GDS UNITS 记录是乱码字节,几何被按 0.8× 解读(P0)**

`gds.cpp: generateUnits` 硬编码的 UNITS 双精度字节解码为 (8.17e-9, 7.98e-33) —— 物理上荒谬。写出器对内部坐标统一乘 2(`designmng.cpp` EXPORT_LAYOUT),内部单位为 1/MINSTEP=2.5nm,故一个 DBU 实为 MINSTEP/2=1.25nm;但乱码 UNITS 使任何遵守规范的读者无法按此解释,gdstk 等回退到 1nm DBU,把全部图形画成设计值的 80%(接触孔 52nm vs 规则 65nm、栅长 40nm vs 50nm、单元 3.36×2.08 vs 日志 4.2×2.6)。而面积度量读的是**日志**宽度(`gds_analysis._readAstranCellWidth`),与物理 GDS 相差 25%。修复:UNITS 字节改为 (0.00125, 1.25e-9)(`struct.pack('>d')` 计算的 IEEE 754),并注明推导。验证:重生成后 GDS 实测尺寸与日志完全一致(AND2X1 1.0×2.6µm、接触孔 0.065µm)。

**(2) 压缩器 a2/b2 端线变量无下界,对角间距约束被架空(P0)**

`createNode` 的端线机制只以单向不等式约束 a2/b2(`x_a2 ≤ x_a - minExt·b_endline`)。本工艺 S3==S1 ⇒ minExt=0,于是 a2/b2 完全无下界;`insertDistanceRuleInteligent` 的对角选项约束形如 `x_cur_a2 - x_last_b + y_cur_a2 - y_last_b ≥ 1.41·minDist`,LP 通过缩小 a2 即可任意满足 → 不同网络形状可以被排到 y 重叠 + x 间距 2 内部单位(0.005µm)。盒级扫描证实 20 个单元里 16 个 MET1、若干 POLY 存在此类真间隙(基准库同样命中,系工具链性问题)。修复:a2/b2 与 a/b 改为**等式**(`CP_EQ`,a2 = a − minExt·b_h,b2 = b + minExt·b_h),对角约束从此作用于真实边;顺带使 enableDFM 的 maxH/V 在 minExt=0 时归一为 0(此前其几何效果同样被 a2 自由度架空)。注意:约束变紧后 AND2X1 的求解从 10s 变为 ~230s(OR2X1 304s),这是模型健全化的代价。

**(3) 走线段/远距节点对无任何间距约束 —— 增加"规则洁净修复通道"(P0→防御)**

约束模型只对当前元素与**前两个**元素的节点对插入间距约束;垂直/水平走线段(createTrack)与外网图形之间没有任何约束。为此在 compact() 首次求解后加入迭代修复通道:读解出的坐标,检测同层不同网(MET1 用 Box 网名、POLY 节点/走线原本传空网名——已改为从路由图取真网名)盒对间距 < 规则者,插入四选一分离约束(右/左/上/下,二进制 + CP_MIN_VAR_VAL),重解,直至 0 违规(上限 8 轮)。实测 AND2X1/OR2X1 首 解即 0 违规(等式修复已消除真违规),通道作为结构性安全网保留;检测器把同网有缝对打印为 "same-net gap" 并跳过(连接经接触孔从别处达成,属合法)。

**(4) 电源引脚无标签 + 标签层错误(P1)**

ASTRAN 只给 IOgeometries 里的信号端口打标(route() 把 vdd/gnd 排除在外),GDS 从无 VCC/GND 文本;标签也写在 drawing 层 11 而非 pin 层 18。修复:compact() 在创建电源轨道处直接 `addLabel`/`setPin`(VCC/GND,轨道中心);designmng 导出标签层 MET1→MET1P(18)。验证:每个单元的全部端口(含电源)标签均位于层 18。注意 ASTRAN 内部把网名统一大写,故复杂单元端口 `cl1#A` 的标签文本为 `CL1#A`(上游固有行为,测试按大小写不敏感比较)。

**(4b) 修复通道判据精化:欧氏角距**

初版检测器按 `max(dx,dy) < rule` 判违规,把**合法的对角摆放**(如 dx=16、dy=21,欧氏角距 √(16²+21²)=26.4 ≥ 26)也当违规,塞入轴对齐分离约束后反而把模型逼成 INFEASIBLE(全零解级联)。修正为欧氏角距判据 `dx²+dy² < rule²`(与 `insertDistanceRuleInteligent` 的对角选项一致:sum ≥ 1.41·rule ⟹ 欧氏 ≥ rule),重生成后所有单元的修复通道在**第 0 轮即 0 违规**。

**(5) 回归防护与验证**

- 新增 `tests/unit/test_gds_quality.py`(纯标准库解析 GDS):UNITS 记录、GDS 尺寸 vs 日志、全部端口(含电源)在 pin 层 18 有标签、接触孔/金属/poly 最小宽度。全部检查基于提交产物,无需 ASTRAN。
- 终审 sweep(20 个单元,全部通过):UNITS=(0.00125,1.25e-9);GDS 实测尺寸与日志一致;端口标签齐全;MET1-接触-poly 搭接图连通分量 = 有 M1 的网数(AND2X1 6/6、COMPLEX1 15/15),无断线、无浮岛;修复通道全部 (0,0)。
- 全部 16 个基准单元 + 4 个 COMPLEX 单元以修复后的工具链重新生成;125 个单元测试(44 既有 + 81 新增)全部通过。
- **宽度变化**(设计单位 µm,H=2.6 不变):约束健全化后多数单元反而更紧 ——
  DFFPOSX1 5.4→3.6、DFFNEGX1 3.6→2.8、CLKBUF1 2.0→1.8、OR2X1 1.6→1.0、XOR2X1 1.8→1.6、AOI21X1 1.0→1.2、AOI22X1 1.2→1.4;
  COMPLEX0 2.4→**2.0**、COMPLEX1 4.2→**4.0**、COMPLEX9 3.6→3.6、COMPLEX10 3.8→**4.2**(四者合计 14.0→13.8);其余基准单元不变。
  宽度变小并非缩水:几何不再被 0.8× 出错解读,且间距全数满足 tech_freePDK45.rul。

**运维教训**:被终止的后台批量任务在 Windows 上会遗留内层 `bash` 循环继续拉起 ASTRAN;两个并行 ASTRAN 会覆写共享的 `ILPmodel.lp/.sol`,表现为随机的 UNBOUNDED/0×0/秒退。清树后必须整批重做受污染时段的单元。

### 5.12 第八轮:对齐 GSCL45 的工艺标定,与紧行高下暴露的两个压缩缺陷(2026-09-27/28)

前面几轮修好了 GDS 的*语义*(单位、层号、标签、间距模型),但几何*标定*仍停在 ASTRAN 的编译内置值(行高 13×0.20 = 2.6µm、导轨 0.72µm、VDD 3.3V),与目标库 GSCL45 不一致。本轮从库自身的约定完成标定,并借此把压缩器在紧行高下暴露的两个缺陷修掉。

**(1) 标定来源与改动**

从 `std_celllib` 提取的 GSCL45 约定:LEF `CoreSite SIZE 0.38 BY 2.47`、M1 pitch 0.19µm、abutment 导轨 0.13µm 高、宽度取 0.19 的倍数、`gscl45nm.lib` 标称电压 1.1V、`gds2_encounter.map` 的 stream 号(metal1=49、via=50、metal2=51、via2=61、metal3=62、via3=30、metal4=31、via4=32、metal5=33)。

- `flow/astran.py`:`ASTRAN_VGRID=ASTRAN_HGRID=0.19`(原 0.20)、`ASTRAN_SUPPLY_SIZE=0.26`(原 0.72;内部 `supWidth = max(supplyVSize, W1M1)/2 = 0.13` → 导轨高 0.13µm)、`ASTRAN_NWELL_POS=1.235 = H/2`(使 nwell/pwell 等高,与手工库一致;初版取过 1.0825,井高不等)。行高 = 13 × 0.19 = **2.47µm = GSCL45 site 高**。
- `tools/astran/build/Work/tech_freePDK45.rul`:金属/通孔层号改为 GSCL45 stream 号;`VDD 3.3 → 1.1`。
- `tools/astran/build_astran.sh`:链接后 `strip` 二进制 —— 360 的启动启发式(HEUR/QVM…Malware.Gen)会删除刚链接的 `Astran.exe`,strip 后不再误杀(替代此前"加信任列表"的说法)。

验证:全部单元的 GDS 实测导轨高 0.13µm、总高 2.47µm、pwell/nwell **等高**且分界在 H/2 = 1.235;6 个窄单元宽度与 LEF 手工版一致(INVX1 0.57、NAND2X1 0.76、NOR2X1 0.76、AOI21X1 0.95、OAI21X1 0.95、AOI22X1 1.14),其余为 ASTRAN 自身拓扑的合法布局(部分比 LEF 窄、部分偏宽,属生成器与手工库的风格差异,非标定问题)。

**(2) 宽度表(H = 2.47µm,单位 µm;面积代理为宽度;等井高几何)**

| 基准(LEF 对照) | 宽度 | 基准 | 宽度 |
|---|---|---|---|
| INVX1 (0.57 ✓) | 0.57 | MUX2X1 | 1.33 |
| NAND2X1 (0.76 ✓) | 0.76 | NOR3X1 | 1.33 |
| NOR2X1 (0.76 ✓) | 0.76 | XOR2X1 | 1.90 |
| AND2X1 | 0.95 | CLKBUF1 | 1.90 |
| NAND3X1 | 0.76 | XNOR2X1 | 1.52 |
| AOI21X1 (0.95 ✓) | 0.95 | DFFPOSX1 | 3.42 |
| OAI21X1 (0.95 ✓) | 0.95 | DFFNEGX1 | 3.23 |
| OR2X1 | 0.95 | AOI22X1 (1.14 ✓) | 1.14 |

| 复合单元 | 宽度 | 说明 |
|---|---|---|
| COMPLEX0 | 2.28 | 首解即可行,修复通道 0 违规 |
| COMPLEX1 | 4.37 | 首解即可行,修复通道 0 违规 |
| COMPLEX9 | 3.61 | 首解即可行,修复通道 0 违规(对比 1.0825 几何的 5.13) |
| COMPLEX10 | 5.89 | 首解即可行,修复通道 0 违规(对比 1.0825 几何的 6.27) |

**(3) 初版几何暴露的两个压缩缺陷(P0)**

在初版几何(nwellpos = 1.0825,井高不等)下,COMPLEX1 的压缩模型被 CBC **证明不可行**(52s 内给出 INFEASIBLE),`autoFlow` 的 `conservative` 0…4 全部失败;由此定位出下面两个独立缺陷。修复保留为回归守护;**最终等井高几何(nwellpos = H/2 = 1.235)下,四个复合单元全部直接求解成功,回退未触发**。

**(3a) 分离规则的第三个分支(q)在紧行高下不可满足。** `insertDistanceRuleInteligent` 给每对形状三个互斥的分离方式(右/上/对角右上),由选择子二进制 `b<A>_<B>_<opt>_<uid>` 门控;§5.11 把端线变量 `a2/b2` 由单边约束改为等式后,第三分支真正生效 —— 其中对角分支 `x_cur_a2 - x_last_b + y_cur_a2 - y_last_b ≥ d` 同时耦合两个坐标,对某些由放置器固定了相对次序的形状对不可满足。**加宽单元也没用**:实测 3 个内部轨道的同一模型同样 INFEASIBLE,说明不是水平空间不足。定位证据:用适配器自己的解析器建同一模型,逐族删除约束 —— 删除全部第三分支后模型在 901s 内给出可行解。
修复(在求解适配器,失败时触发):仅当模型被**证明 INFEASIBLE** 时,重建并仅丢弃第三分支(`_is_option3_disjunct`:含 `RELAXATION` 且引用 `…_3` 选择子),再解;ASTRAN 随后的**修复通道**按解出坐标强制真实间距,导出仍规则洁净。刻意**不**在超时(`NO_SOLUTION_FOUND`)时触发 —— 那是求解预算问题而非模型缺陷,应保留精确约束,让 `autoFlow` 的保守度/轨道升级复现同一结果(否则改一次预算就会悄悄改变某个单元用的是哪个模型)。对首解即可行的单元完全不触发(等井高几何下本轮 20 个单元全部首解可行,回退未触发;其价值是对 1.0825 一类几何的兜底)。该回退并非万能:在 1.0825 几何下实测,COMPLEX9 的 `conservative = 0` 在丢掉第三分支后仍被证明不可行(那里另有冲突源,未再深挖),该单元当时在 `conservative = 2` 求解成功。

**(3b) 修复通道的四选一分离约束缺少各自的大 M(潜伏缺陷)。** `compact()` 的修复通道对每个违规对插入四个二进制 `t1..t4`(和 = 1)与四条分离约束,但**漏写了 `+ RELAXATION` 项及 `rule + relaxation` 系数**。于是 `t_i = 0` 的分支仍部分生效(例如 t2=0 仍要求 `x_A_a ≥ x_B_b`),与 t1=1 的 `x_B_a ≥ x_A_b` 直接矛盾 —— 任何二进制赋值都不可行,重解恒为 INFEASIBLE,通道空转满 8 轮后带着原违规导出。因 §5.11 之后所有单元首解 0 违规,该缺陷一直未触发(COMPLEX1 之前也只有 0 违规)。
修复:四条约束改为 `"x…b + RELAXATION"` 且系数 `rule + relaxation`(与 `insertDistanceRuleInteligent` 的写法一致,本处 `relaxation == RELAXATION == 20000`)。重生成后 COMPLEX1 第 0 轮检出 6 对违规、第 1 轮即为 0。

**(4) 结果与回归防护**

- 等井高几何下四个复合单元全部首解可行、修复通道 0 违规:COMPLEX0 2.28、COMPLEX1 4.37、COMPLEX9 3.61、COMPLEX10 5.89(对比 1.0825 几何的 2.09 / 3.61 / 5.13 / 6.27);全部 20 个单元按最终几何重生成。
- 终审 sweep(20 个单元)全部通过:UNITS、GDS 尺寸对日志、端口标签(含电源)在 pin 层、MET1-接触-poly 搭接连通分量、无浮岛、修复通道末轮 0 违规。
- `tests/unit/test_gds_quality.py` 新增两项回归:`(a)` 每个单元日志的最后一条 "Spacing repair pass N: M violating pair(s)" 必须 M = 0;`(b)` 以 MET1-CONT-POLY 搭接图区分同网合并与真违规后,**不同网的 MET1 角距必须 ≥ S1M1M1**。全部 **189** 个单测通过(含 GUI 数据层测试)。
- 复现验证:同一二进制在同一几何下重跑 INVX1、COMPLEX1、COMPLEX9,逐层几何一致;对"首解即可行"的单元,二进制改动行为不变。

**(5) 已知取舍(仍开放)**

- 生成的 ASTRAN 行高与 GSCL45 site 一致(2.47µm),金属/通孔层号也已对齐;但**基础层**(active 1、poly 9、contact 10、well 2/3/4/5)仍用本仓库的 Cadence 式编号 —— 若要与 GSCL45 库的 GDS 直接合并,基础层仍需按需重映射(§5.5 的遗留项已缩小到基础层)。
- `supplysize` 由导轨高推得(0.26 → 0.13µm);`nwellpos = H/2 = 1.235` 取与手工库相同的等井高分界(仓库中没有 GSCL45 官方工艺文件可对;DRC 由 ASTRAN 的 `tech_freePDK45.rul` 约束保证)。
- 面积账(adder,等井高版图重算 `bestRecord-adder`):saveArea 22.8µm / 3.06%(GSCL 口径 45.6µm / 5.82%),选定模式 COMPLEX9。对比 1.0825 几何的 106.2µm / 13.24%:下降主因是等井高让多个基准变窄(XNOR2X1 2.09→1.52、DFFNEGX1 4.18→3.23、NOR3X1 1.52→1.33),复合单元相对其部件不再那么"省";COMPLEX10(5.89)甚至宽于其 5 个部件之和(4.94),节省为负。这是更真实的经济账,不是回归缺陷。
- 曾在 1.0825 几何下用 600s 预算尝试收紧 COMPLEX9/COMPLEX10(当时 5.13/6.27):COMPLEX10 有望变窄,但 COMPLEX9 在 `conservative = 1` 上由适配器回退进入"松弛后靠修复通道补 21 对违规"的昂贵路径,质量反而不如严格模型在 `conservative = 2` 得到的干净解 —— 未采用;等井高几何下两者已分别降至 3.61/5.89 且首解可行,无需再收紧。
- 运维:360 对 `build/bin/Astran.exe` 的启动误杀在 strip 之后仍会随其定义更新复发(strip 只解决了当次),最终以手工白名单解决;`build_astran.sh` 的 strip 步骤保留,`Astran.keep`/zip 备份可用于应急恢复。
- `compaction.cpp` 新增 `ASTRAN_DUMP_FAILED_LP=1` 时把失败模型写为 `ILPmodel.fail.lp` 的调试口(便于离线定位不可行,不设则行为不变)。

### 5.13 第九轮:结果页解释增强与客户安装包(2026-09-29)

**(1) 结果页(Results)解释增强** —— `gui/tabs/results.py` 重写为教学式页面,内容全部保留原有数据逻辑(行为不变,194 个单测通过):

- 阅读引导从 6 条扩到 7 条:先讲"这一页讲什么"(挖掘→合并→省面积的因果),再逐条讲六个数字、三张图与两个记录文件的读法;
- 三张图卡片内各加一段"图下说明"(并排宽度的来源、总节省 = 单位节省 × 出现次数、两个基准口径为何不可直接比较);
- 新增「术语表」卡片(KeyValue,11 个词条:模式/复杂单元/出现次数/覆盖/模式码/ASTRAN 基线/GSCL 基准/并排与合并宽度/单位与总节省/节省率/0×0 排除);
- bestRecord 卡片加"逐行格式说明"(第 1–4 行语义、入选模式元组字段、seperate 文件各列);
- 顶部六个 StatTile 各加 hint 行。构建验证:`QT_QPA_PLATFORM=offscreen` 下构造 ResultsTab 并 refresh 成功。

**(2) 客户安装包** —— 无网络环境下(无 PyInstaller/Inno Setup/NSIS 可用)制作单文件自解压安装器,全部脚本在 `tools/package/`:

- `make_stage.py` 装配 `dist/stage/`:流程本体(flow、std_celllib、benchmark/blif 去掉 BoomBranchPredictor 与 DCache 两个 >90MB 巨型网表、tools/astran/build、tools/gurobi_cl、doc)+ 从开发机 Python 3.11 复制的**裁剪运行时**(site-packages 按 `SITE_KEEP` 保留列表,2.9GB → 970MB);
- PySide6 只保留 QtCore/QtGui/QtWidgets(+QtSvg),按前缀去掉 WebEngine/QML/Quick/Multimedia 等(642MB → ~240MB);**坑**:初版把 `pyside6.abi3.dll`/`icu*.dll` 等非 Qt 前缀的支持 DLL 一并删了,`import QtWidgets` 报 DLL load failed —— 过滤必须以"Qt 前缀 + 白名单"为准,支持 DLL 全留;
- 运行时裁剪踩到的隐性依赖(按导入失败逐个补进 `SITE_KEEP`):sklearn 1.9 需要 `narwhals`,liberty-parser 需要 `sympy`+`mpmath`,python-mip 需要 `cffi`(+`pycparser`);cbcbox 只留 `cbc_dist*/bin+lib`(mip 通过 `cbc_lib_dir()` 找 `libCbc-0.dll`),实测 CBC 求解正常;
- `launcher.c` 编译为 `AutoCellLibX.exe`(自定位目录、PATH 前置 runtime、起 `pythonw -m gui`);**坑**:MSYS2 MinGW gcc 从 Git Bash 直调无法 spawn cc1.exe,必须经 `C:\msys64\usr\bin\bash.exe -lc` 驱动;
- `installer_stub.c` 是自解压 stub(静态 CRT + 静态 zlib):找自身尾部 ZIP(解析 EOCD/中央目录,deflate 解压),进度条对话框,解压到 %TEMP% 后跑 `setup.cmd`(robocopy 到 `%LOCALAPPDATA%\AutoCellLibX` + PowerShell 建桌面/开始菜单快捷方式),结束后清理;`make_installer.py` 把 stage 打成 ZIP 追加到 stub 后即为 `dist/AutoCellLibX-Setup.exe`;
- 交付文档 `README_DELIVERY.md`(客户视角:系统要求、安装/卸载、360 误报白名单步骤、目录结构、FAQ、数字口径)随包发布。

**(3) 验证路径(交付前必跑)**

1. `dist/stage` 内用自带 `runtime\python.exe` 导入全部流程模块 + PySide6,QApplication 可建,`probe_environment()` 全绿;
2. `from mip import Model` 实测 CBC 求解(OPTIMAL);
3. 安装器端到端:运行 `AutoCellLibX-Setup.exe` → 解压 → setup.cmd 复制 + 建快捷方式 → 从 `%LOCALAPPDATA%\AutoCellLibX` 启动 GUI;
4. 在安装副本上跑 adder 全流程(基线/版图均命中缓存,验证挖掘→记录闭环)。

已知取舍:安装包约 1GB(压缩后),因为内置完整 Python 运行时;大网表不随包(需 8MB+ 交互警告,文档说明可手工拷回);ASTRAN 的 360 误报无法自动规避,交付文档给出白名单步骤。

**(4) 安装器实现与验证过程中的踩坑(全部已修复并在 E2E 中验证)**

1. **360 实时防护(HEUR/QVM…Malware.Gen 启发式)** 会把 `dist/` 下每个新编译的 exe 隔离,包括**未附加任何数据的纯 stub**(行为指纹:解压→%TEMP% 写文件→拉起 cmd→递归删除,与恶意投放器重合)。无签名、无网络下载的 MinGW 产物必然中招;白名单(信任区)可解,但注意 360 的"主动防御/进程创建"与"木马查杀"是两层,都要放行。客户侧处理步骤已写入 `README_DELIVERY.md`。
2. **Git Bash 的 TEMP=/tmp(POSIX 路径)** 会被 `_wgetenv("TEMP")` 原样取到,拼出非法路径。stub 改用 `SHGetFolderPathW(CSIDL_LOCAL_APPDATA)` 取 Windows 真实临时目录(经二进制 dump 验证返回完整路径)。
3. **MSYS2/MinGW 链接的是旧 msvcrt.dll**,其 wprintf 族中 `%s` 按**窄字符串**解释(标准 C 是宽串)。stub 里所有宽字符串格式的 `%s` 必须写 `%ls`,否则路径被截成首字符(对话框只显示 "C")、调试日志写不进。`wsprintfW`(user32)的 `%s` 是宽串,不受影响。
4. **批处理文件里的非 ASCII 文本**:cmd.exe 按 ANSI 代码页(GBK)解析 .cmd,UTF-8 中文会把命令边界撕碎(报 `'P' 不是内部或外部命令`)。`setup.cmd`/`uninstall.cmd`/`make_shortcuts.ps1` 全部改为纯 ASCII,中文说明移到 `README_DELIVERY.md`。
5. **`%~dp0` 尾部反斜杠**:`"D:\...\dist\"` 的 `\"` 会让 cmd 吞掉引号、整个命令行粘连成一个参数(robocopy 报"未指定目标目录",错误码 16)。标准修法:`if "%SRC:~-1%"=="\" set "SRC=%SRC:~0,-1%"`。
6. **批处理里 `echo` 的 `|` 必须转义为 `^|`**(ASCII 重写时容易丢)。
7. **`SHFileOperationW` 的 FO_DELETE 在此环境静默不生效**(退出码被忽略,目录残留);改为自写 FindFirstFileW 递归删除,验证通过。
8. **site-packages 白名单漏项**:`_cffi_backend.cp311-win_amd64.pyd`(cffi 的编译后端)不在保留列表,全量重建 stage 时被丢弃,导致安装副本 `import mip` 失败("No module named '_cffi_backend'")。教训:每次增删 SITE_KEEP 后必须重跑"导入冒烟 + 一次 LP 求解"验证。
9. **卸载脚本的 `rd /s /q` 不能删除自己的工作目录**:先 `cd /d "%TEMP%"` 再删。

最终交付物:`dist/AutoCellLibX-Setup.exe`(stub,0.13MB)+ `dist/AutoCellLibX-Setup.dat`(312MB,10370 文件)。E2E 全链路验证:解压→安装到 %LOCALAPPDATA%→桌面/开始菜单快捷方式→临时目录清理→安装副本启动 GUI→完整 adder 流程(FINISHED ok,bestRecord 1.55%)→卸载清理干净。

### 5.14 第十轮:许可合规完善(2026-09-29)

**背景**:仓库只有 `LICENSE`(Apache 2.0 + 商业授权联系条款),但随包/仓库分发的第三方组件没有系统性的许可说明——尤其 ASTRAN 的 vendored 源码树里**没有任何许可文本**(无 LICENSE/COPYING/GPL 文件,头文件仅含 UFRGS 版权行),这对客户交付是合规缺口。

**新增文件**:
- `NOTICE`(仓库根):AutoCellLibX 版权声明(Apache 2.0 要求)+ 第三方归属摘要;
- `THIRD_PARTY_NOTICES.md`(仓库根):逐组件清单——ASTRAN(来源/版权头/无许可文本的如实记录/修改记录/wxWidgets LGPL 动态链接)、gurobi_cl 包装(自有)+ python-mip(EPL-2.0)+ CBC(EPL-1.0)、std_celllib(GSCL45=FreePDK45 系 Apache-2.0、sky130=Apache-2.0、gpdk45nm.m=Cadence 专有)、benchmark(EPFL 研究用、BOOM/Rocket/Gemmini BSD-3 系)、内置 Python 依赖全表(逐包许可证,并指向 runtime 内 dist-info 自带文本);
- `tools/astran/LICENSE.md`:ASTRAN 专项许可说明——如实陈述"源码无许可文本、版权归 UFRGS 作者、上游 github.com/aziesemer/astran、商业使用需联系其作者",不代替其作者授予权利;
- `README.MD` License 章节与 `README_DELIVERY.md` 新增「许可与合规」章节引用上述文件。

**合规要点(已核实,非猜测)**:
- `liberty-parser` 是 GPL-3.0-or-later(唯一强 copyleft 依赖,从 dist-info METADATA 核实),文档中明确标注并提供替换思路;
- `blifparser`=MIT、`gdstk`=Boost-1.0、`mip`=EPL-2.0(均从 dist-info 核实);
- 修改过的 ASTRAN 源码保留原版权头(Apache 2.0 §4(c) 的归属要求);`compaction.cpp` 等改动已在 §5.1/§5.9-5.12 记录;
- 安装包(make_stage.py)现在随包携带 LICENSE/NOTICE/THIRD_PARTY_NOTICES.md/tools/astran/LICENSE.md,客户安装目录可自查。

### 5.15 第十一轮:设计页解析慢与邻居深度不刷新(2026-09-29)

**症状**:① 设计页解析耗时久;② 换深度(1→2→3)结果不变。

**根因**:
- 解析慢的三层原因:(a) 每次解析都重新走 `parse_liberty`(liberty-parser + sympy 布尔函数),固定开销约 0.9s(本机),之前**无缓存**;(b) BLIF 解析与规模线性:div 1.7MB≈0.5s、log2 1.9MB≈0.6s,6MB+ 基准更久;(c) 大设计(8MB+)按设计即警告。用户重复点「解析设计」或来回切基准时反复付出全部代价。
- 深度不刷新的真 bug:`_show_neighbourhood` 的 BFS 里 `keep |= nxt` 之后才算 `frontier = nxt - keep`,永远为空——**深度 1/2/3 实际都只展开一层**;再加上深度 QSpinBox 没有连任何刷新信号,调深度完全无效果。

**修复**:
- `flow/blif_preproc.py`:`load_liberty_file` 增加 (路径,mtime) 键控的进程级缓存,返回浅拷贝隔离 `load_bool_gate_from_blif` 的 bool-* 注入(避免跨基准污染)。实测:第二次解析 0.93s→0.01s。
- `gui/tabs/design.py`:
  - BFS 重写:先 `nxt -= keep` 再并入,frontier 保持"本层新发现"节点;深度 1/2/3 实测节点数 2/3/3(修复前恒为 2);
  - `depth.valueChanged` 连接 `_show_neighbourhood`,调深度立即重绘;
  - `_parse` 按输入签名短路:同一基准且 BLIF/PDK 路径与 mtime 未变时直接显示 `state.designs` 缓存(不启动 worker)。
- `gui/flow_core.py`:`parse_design` 的 info 里写入 `_parse_sig`((blif 路径,mtime),(lib 路径,mtime)),供设计页比对。

**验证**:194 单测通过;offscreen 下缓存命中(worker 启动数=0)、BFS 深度单调增长;max/div/log2 首解析 0.0s/0.5s/0.6s。

### 5.16 第十二轮:无窗口 ASTRAN、解析提速确认与邻居探索修复(2026-09-29)

**症状**:① GUI 运行流程时不断弹出黑色控制台窗口;② 设计页解析"还是很慢";③ 邻居探索"不正常"。

**根因与修复**:
- ① 弹窗有三层来源,全部消除:(a) `flow_core._popen_astran` 从 GUI(pythonw,无控制台)启动 Astran.exe 时未带 `CREATE_NO_WINDOW`,每个单元运行都会开一个黑窗口(且持续整个运行过程)→ 现在 `CREATE_NEW_PROCESS_GROUP | CREATE_NO_WINDOW`;(b) ASTRAN 内部用 `_popen(cmd)` 调求解器,`cmd.exe` 本身也会闪窗 → compaction.cpp 新增 `astranPopenNoWindow`(CreatePipe + CreateProcessA + CREATE_NO_WINDOW + `_open_osfhandle`/`_fdopen`),两个求解调用点(379/612)替换,非 Windows 平台回退 `_popen`;(c) `gurobi_cl.cmd` 改用 `pythonw`(ASTRAN 只读 ResultFile=.sol,不读 stdout),`gurobi_cl.py` 加 stdout/stderr 为 None 时的 devnull 守护(print 不崩)。重建 ASTRAN 后 INVX1/NOR3X1 冒烟全部通过。
- ② 解析实测(安装副本,缓存生效后):adder 0.0s、arbiter 0.2s、log2 0.5s、BoomRob 0.8s、BoomRegisterFile 1.1s、GemminiMesh(6MB)1.9s、GemminiLoopConv(12MB,包内最大)4.5s。首解析的固定成本是 liberty(约 0.9s),已按 (路径,mtime) 缓存;BLIF 解析与网表线性,无法更快(纯 Python 解析器)。"很慢"的剩余解释:包内 >8MB 基准(GemminiLoopConv 等)首解析数秒级属正常。
- ③ 邻居探索两个缺陷:(a) 上一轮 BFS 重写丢了"收集时封顶"——常见类型深度 2 一层可收数千节点,spring 布局(UI 线程)卡死 → 恢复收集期 `MAX_NEIGHBOURHOOD` 上限(实测 div 深度 2 收 21 节点封顶);(b) INVX1 冒烟测试的 GDS 包围盒断言(bb<5 用户单位)在 GDS UNITS 校准提交后过时——GDS 的 UNITS 记录按设计不可信(AGENTS.md 不变式 1,查看器按日志校准),测试改为以日志 Cell Size 为权威 + GDS 非退化矩形检查。

**验证**:194 单测 + 3 集成测试全绿;新 ASTRAN 求解链路(无窗口 popen + pythonw 包装)在日志中 OPTIMAL、0.57×2.47µm、修复通道 0 违规。

### 5.17 第十三轮:全层实现校验(2026-10-09)

**范围**:对照 doc/IMPLEMENTATION_GUIDE.md 九层模型逐条校验方案与代码(独立代理分头取证,file:line 可溯),并运行完整单测(194 passed)。完整报告在 `doc/LAYER_VERIFICATION.md`,此处只登记缺陷档案。

**文档错误(已修订)**:
- 指南 L1:NAND2X1 的 SPICE 宽度写成 0.205µm(实为 0.5µm)、引脚序写成 `A B Y VCC GND`(实为 `VCC Y GND A B`);LEF 宽度写成 1.14(实为 0.76,1.14 是 AND2X1);
- 指南 L7:`.run` 示例 `nwellpos 1.0825` 为旧几何残留(实为 1.235=H/2),且漏 `set celltemplate "Tapless"` 行;"autoflow 七阶段"实为五阶段+独立 select/export 命令,place 是 Threshold Accept(退火变体)非教科书 SA;
- `AGENTS.md` option-3 条目:"COMPLEX1 needs the recovery at H=2.47"是 1.0825 旧几何残留——现行几何下 adder 四单元全部首解可行,重试一次未触发(已改为"安全网而非常态"的表述)。

**代码隐患(记录在案,未改行为)**:
1. `flow/astran.py:45-46`:日志缺 `Cell Size` 行时 `assert(False); return 123`——`python -O` 下 assert 被剥离会静默返回 123µm 假宽度(应改抛异常);
2. `flow/main.py:247-248`:`bestRecord-seperate` 在逐模式循环之前以 `'w'` 打开,循环中途异常会留下空/半截记录;
3. `flow/main.py:92`:`cellIdsContained>=11` 用 `continue` 跳过但队首未弹出,依赖后续分支弹出才不死循环(脆弱);
4. `flow/blif_preproc.py:123-124`:库中找不到 `.subckt` 类型直接 `assert(False)`;`blif_graph_util.py:82-84` 多驱动网静默覆盖 `predCell`,均无告警;
5. `flow/gds_analysis.py:18-21` 注释仍写"基线 H=3.2/本地 2.6"(现行 2.47),且两个 `load*GDS*` 函数名误导(实际读 LEF/日志)——文档漂移,行为正确。

**算法层面风险(转化为优化路线图的动机,详见 doc/RESEARCH_AND_OPTIMIZATION.md)**:
- 编码不对子节点排序(`blif_preproc.py:222-235` 无 sort):根节点多输入类型不同时,同构实例会得到不同编码→频次系统性低估(P0-1);
- 节省求和无重叠去重:不同模式的簇可共享单元(`setCluster` 覆盖),`main.py:185-188` 直接求和会重复计收益(P0-2);
- 生长宽度恒为 1(`blif_pattern_growth.py:104` 的 `[:1]`)且不知面积:COMPLEX10 实证负收益(−56.05,bestRecord-seperateadder:5)(P0-3);
- 唯一归属为破坏式 enforcement:占用冲突时整个旧簇被 `disabled=True`,无收益比较(`blif_pattern_growth.py:118-120`);
- flow_core 与 main.py 无任何等价测试,"faithful port"靠人工评审(P0-5)。

**验证**:194 单测通过(校验未触碰流程代码,仅改文档)。

### 5.18 第十四轮:隐患修复与 P0/P1 优化落地(2026-10-09)

**§5.17 五处代码隐患已全部修复(带回归测试,test_hazard_fixes.py 等)**:
1. `Astran.loadAstranArea` 缺日志时改为 `raise RuntimeError`(原 `assert(False); return 123` 在 `python -O` 下静默造假宽度);
2. `main.py` 两个 `>=11` 守卫由 `continue` 改为弹出队首(原写法空转整个迭代预算);`flow_core.py` 两处同步;
3. `main.py` 第二阶段 `bestRecord-seperate` 改为末尾才打开写盘(原开头 `'w'` 截断,中途崩溃留空文件);
4. `blif_preproc` 未知单元类型改抛 `ValueError`(含类型名与 lib 路径),`PIN=net` 畸形行显式报错;
5. `DesignNet.addPin` 多驱动网保留 last-wins 但发出 `RuntimeWarning` 并计数(`DesignNet.multiDriverCount`)。

**P0 优化(行为变化已标定)**:
- P0-1 编码规范化(`canonical_pattern_code`,根在前、子节点排序):trace 字符串因此对既有 outputs 快照改名(如 `[XNOR2X1,XOR2X1,OAI21X1]`→`[XNOR2X1,OAI21X1,XOR2X1]`),重生成时以新名为准。**大基准实测收益显著**(`flow/canon_impact.py`):BoomBranchPredictor 2721→1793 组(合并 737 个虚假分裂、回收 21541 个实例)、DCache 2084→1459(13503)、GemminiLoopConv 2829→1787(14588);adder 网表顺序本来就一致,数字不变。
- P0-2 节省重叠去重(`countUncoveredClusters`):同轮候选共享的簇只计一次;bestRecord 中 clusterNum 变为去重后计数。
- P0-3 束搜索+预估剪枝:`grow_sequence_of_clusters` 接受 `benefitEstimator`(新增 `flow/benefit.py` 的 ShrinkModel,按"尺寸→收缩率"在线标定、取保守 max);`growBeamWidth=2`(global_variables)/`cfg.grow_beam=2`(GUI)每轮生长前 2 个队首;≥10 单元的队首不再生长(其 11 单元后代在版图阶段必然被剔除)。COMPLEX10 型负收益(−56.05)在其首个观测后会被剪枝。
- P0-4 可布性第二指标(新增 `flow/routability.py`):从 .Astranlog 解析 `Rt. Density` 与 Pathfinder 尝试轮数,报告默认开启;硬门限 `routabilityDensityGate`/`cfg.max_rt_density` 默认 None(先测量后执法)。
- P0-5 flow_core≡main.py 等价测试:桩 ASTRAN(按 .sp 内容哈希定宽)比较两流程 bestRecord(见 tests/unit/test_flow_parity.py)。

**P1 优化**:
- P1-7 电气量(新增 `flow/electrical.py`):解析 liberty 的 `cell_leakage_power`/引脚电容/LUT 均值延迟代理;模式级汇总含 internal_nets(合并内化的网数=动态功耗节省代理)。report-only,不改选择准则。
- P1-8 PDK 注册表(新增 `flow/pdk_config.py`):freepdk45 与 astran.py 常量强一致(测试钉住);sky130(8×0.34µm)/gf180(14×0.28µm)为脚手架,.rul 未编写前 raise;`nwellPos` 恒取 H/2 防再次漂移。
- P1-9 端口顺序变体(新增 `flow/portorder.py`):确定性变体集(恒等/电源在前排序/反转/种子洗牌),只重写 .subckt 头部;评估走注入式 runner。
- P1-11 多行高(`pdk_config.multiRowVariant`):行高翻倍时 nwellpos 自动 H/2;跨 profile 比较必须按 宽×高 面积(不变量 10)。

**已知遗留**:P2(SMT/CP-SAT 引擎、LLM 约束注入、CFET/BSPDN)为研究级,未在本轮实现,见 doc/RESEARCH_AND_OPTIMIZATION.md。

**验证**:233 单测通过(新增 39 个)。

### 5.19 第十五轮:客户安装包缺 MinGW 运行库 DLL(2026-10-09)

**缺陷**:客户机运行安装包报 `libstdc++-6.dll 没有`(及 libgcc_s_seh-1.dll 等一串 MinGW DLL 缺失)。

**根因**:ASTRAN 工具链是 MSYS2/MinGW 构建、**动态链接** MinGW 运行库的。`objdump -p` 实测导入表:

- `Astran.exe` / `Cellgen.exe` / `astranrun.exe` 均导入 `libstdc++-6.dll`、`libgcc_s_seh-1.dll`(另有 wx 两 DLL);
- `wxbase32u_gcc_custom.dll` / `wxmsw32u_core_gcc_custom.dll` 额外导入 liblzma-5 / libpcre2-16-0 / zlib1 / libjpeg-8 / libpng16-16 / libtiff-6;
- libtiff-6 再拉 libdeflate / libjbig-0 / libLerc / libwebp-7 / libzstd,libwebp-7 再拉 libsharpyuv-0。

开发机上这些 DLL 来自 `C:\msys64\mingw64\bin`(在 PATH 上),所以本地一切正常;安装包 stage 只随 `copy_repo_dir("tools/astran/build")` 带了两个 wx DLL,MinGW 运行库一个没带。全 stage 扫描确认:除 ASTRAN 工具链外无任何二进制(含 runtime 的 cffi/mip/PySide6——均为 MSVC wheel)导入这些 DLL,故补在 build/bin 一处即可。

**修复**:把依赖闭包内的 15 个 DLL 拷贝进 `tools/astran/build/bin/` 随仓库入库(stage 装配整体拷贝该目录,后续打包自动带上):
libgcc_s_seh-1.dll、libstdc++-6.dll、libwinpthread-1.dll、liblzma-5.dll、libpcre2-16-0.dll、zlib1.dll、libjpeg-8.dll、libpng16-16.dll、libtiff-6.dll、libdeflate.dll、libjbig-0.dll、libLerc.dll、libwebp-7.dll、libzstd.dll、libsharpyuv-0.dll。
版本必须与现有 wx DLL 的 MSYS2 工具链匹配(mingw64 16.2.0);更换工具链后需重验导入闭包。

**验证**:重建 Setup.dat(11146 文件 / 323.4 MB),解包核对 `tools/astran/build/bin/` 内 17 个 DLL(2 wx + 15 MinGW)齐全;安装 zip 完整性校验通过。

**附带发现(打包流程)**:360 实时防护对 `dist/` 下新建 exe 的隔离是**延迟判定**——白名单里的交付名 `AutoCellLibX-Setup.exe` 也只在创建后存活约 4 分钟(12:48 写入存活至 12:52+ 被删),且**首次隔离后该文件名被列入写拦截**(cp 直接 Permission denied;`installer_stub.exe` 同名现象一致)。因此打包流程中 exe 只需在 zip 内完整即可:先重建 dat(zip 不被扫描),stub 从旧 zip 提取/临时目录编译,随即打包;不要依赖 dist 里的 exe 长期存活,也不要重跑 `make_installer.py`(其 build_stub 会写回被拦截的名字)。

### 5.19 第十五轮:P2 研究级合入(2026-10-09)

**阶段 0 版图合理性校验门(flow/layout_sanity.py)**:对生成 .gds 做结构检查(非退化、metal1 高度=行高、宽度网格对齐、层与电源标签齐全),标定方式与 GUI 查看器一致(16.5 units/µm、井区外扩不计入)。main.py/flow_core 默认开启剔除(`layoutSanityGate`)。真实 COMPLEX0/1/9 全部通过;等价测试桩同步升级为最小合法 GDS。

**yosys 重导入(用户指定优先级)**:① `electrical.py` 增 area 属性与逐引脚电容(`pin_caps`);② 新增 `timing_power.py`:解析 liberty 时序弧(cell_rise/fall、rise/fall_transition)与 internal_power LUT(delay_template_6x6:行=负载 pF、列=输入转换 ns),双线性插值(边缘钳位),并在模式 DAG 上做迷你 STA(逐网负载=被驱动引脚电容和、最坏弧级延迟、摆率传播、最长路径、翻转能量),已用库角点值验证;③ 新增 `yosys_import.py`:探测 yosys→`stat -json`→防御式解析 area/num_cells/histogram 并与流程的 lib 面积和交叉校验;本机无 yosys 时优雅降级。全部 report-only 接入 main.py 与 flow_core(pattern 事件带 timing_power)。

**阶段 1 宽度代理(flow/width_proxy.py)**:特征(单元数、晶体管数、基线宽度和)→Ridge 回归,训练语料=仓库既有 12 个 COMPLEX 版图。真实 LOO:MAPE 16.4%、R²=0.79——粗筛可用、精度有限;对 COMPLEX9(好)过估、对 COMPLEX10(坏)方向正确,故默认 report-only,生长估计器替换由 `useWidthProxyForGrowth` 显式开启。

**阶段 2 CP-SAT 压缩后端(tools/gurobi_cl/cpsat_backend.py)**:发现 ASTRAN 的压缩 LP 全整数(400 DBU/µm),CP-SAT 可精确消费(自适应缩放,整数模型 scale=1);`GUROBI_CL_SOLVER=cpsat` 启用,CBC 仍为默认;失败语义(全零 .sol)与 option-3 恢复纪律(仅证明 INFEASIBLE,超时绝不触发)与 CBC 路径一致;ortools 缺失时自动回退 CBC。对拍工具 `tools/gurobi_cl/compare_backends.py`。新增 `compare_backends.py` 与单元测试(小 LP 最优解、INFEASIBLE 检测、端到端 .sol、析取过滤)。

**阶段 3-5(文档化立项,见 doc/P2_MERGE_PLAN.md)**:LLM 出约束/TOPCELL 拓扑生成(待阶段 1 评估);SMT folding+placement 先作 ≤12 管参考实现给 ASTRAN 打分;CoP&R 的 AllSAT 可复用阶段 2 的 CP-SAT 通道;SO3-Cell 因求解成本(44 管 7.2h)与本流程预算不兼容暂缓;NVCell2/RL、DiSPlace/TransOpt、CFET/BSPDN 结论性不合入(架构不匹配或超出库扩展器定位)。

**验证**:263 单测通过;对拍结果见提交记录与 P2_MERGE_PLAN 状态。

### 5.20 CP-SAT 端到端版图实验(2026-10-09,沙盒,未触碰跟踪产物)

**方法**:同一 `COMPLEX1.sp`/`COMPLEX0.sp` 各跑两遍完整 ASTRAN(placement/route 确定,仅压缩求解器不同),`GUROBI_CL_TIME_LIMIT=180`,沙盒输出,版图过 layout_sanity 校验门。

**结果(决定性)**:

| 单元 | 后端 | 目标值 | 宽度 | 校验门 | repair pass |
|---|---|---|---|---|---|
| COMPLEX1 | CBC@180s | 1.895e7 | 9.31µm(49 格) | (异常组,日志 0 违例) | 0 |
| COMPLEX1 | **CP-SAT@180s** | **7.44e6** | **3.61µm(19 格)** | ✅ 通过 | 0 |
| COMPLEX1 | (历史 CBC@300s 跟踪产物) | — | 4.37µm | ✅ | — |
| COMPLEX0 | CBC@180s | — | 2.28µm(与历史一致) | ✅ 通过 | 0 |
| COMPLEX0 | **CP-SAT@180s** | — | **2.09µm(−8%)** | ✅ 通过 | 0 |

**解读**:COMPLEX0(小模型)上 CBC 精确复现历史宽度,CP-SAT 再压 8%;COMPLEX1(大模型)上 CBC@180s 的 incumbent 质量崩溃(9.31),而 CP-SAT 同期拿到 3.61——目标值差 2.5×。与文献共识一致(CBC 在 big-M 模型上"找解快、收敛慢"),也与对拍实验(ILPmodel 上 CP-SAT −0.11%)方向一致。层/标签计数两后端一致(active 57、poly 149、M1 409、标签 8),证实是同一电路的更紧打包。

**建议(未执行)**:将默认后端切为 CP-SAT(`GUROBI_CL_SOLVER=cpsat` 已可用,或改 gurobi_cl.py 默认值,ortools 缺失自动回退 CBC)。默认切换会改变后续所有生成单元的宽度,属策略决定,留给用户拍板;切换后建议整基准重生成并更新 outputs 快照。

**yosys 安装尝试失败**:MSYS2 pacman 数据库 PGP 签名损坏(ucrt64/clang64/msys 库),未做系统级修复;`yosys_import` 保持优雅降级,装好后直接可用(用户可在 oss-cad-suite 或修好 pacman 后获得)。

### 5.21 yosys 重导入打通:yowasp-yosys 与真实交叉校验(2026-10-09)

**安装**:MSYS2 pacman 数据库损坏无解后,改走 PyPI 的 **yowasp-yosys**(WebAssembly 构建,`pip install yowasp-yosys`,Yosys 0.69)——无需 MSYS2、无需下载 oss-cad-suite。首次运行被系统占用锁(360 扫描)短暂阻塞,重试即正常。

**适配(yosys_import.py)**:① `YOSYS_CANDIDATES` 增加 yowasp-yosys;② `runYosysStat` 改用 `stat -json` **stdout 模式**(YoWASP 沙盒无法写 %TEMP%,真 yosys 同样接受,单一路径);③ 解析器适配真实 0.69 schema:模块名 `\top`、直方图键 `num_cells_by_type`(保留 `cell_histogram` 兼容)、容忍日志前缀截取 JSON;④ 新增 `compareCellCounts`(直方图对拍)——因为 `read_blif` 的单元不绑定 liberty 单元,**yosys 侧 area 为空是机制性限制**,面积交叉校验由流程的 lib 面积和承担;⑤ main.py/flow_core 交叉校验打印升级。

**真实交叉校验结果(adder)**:
- yosys `num_cells=707` vs 本流程图 707 个库类型单元(710 节点 − 3 个 bool 常量)——**精确一致**;
- 直方图逐类型一致(NAND2X1=192、XNOR2X1=118、OAI21X1=72、OR2X1=71 等,与第二层校验的独立计数吻合);
- 流程 lib 面积和=2047.087;delay/power 由 `timing_power.py`(liberty LUT + 迷你 STA)承担,已在 §5.19 验证。
- 新增自跳过式真实用例 `test_run_stat_real_yosys_if_available`(有 yosys 时断言 707/192)。

**验证**:266 单测通过。

### 5.22 COMPLEX 单元的 Liberty 表征生成(2026-10-09)

**问题**:ASTRAN 重生成版图后,.sp 不需要重生成(挖掘产物、ASTRAN 输入、缓存契约看 mtime);但 COMPLEX 单元**在库中没有任何 .lib 条目**——库只覆盖 31 个基础单元,下游复用(重映射/STA/交叉验证)缺 delay/power/area。

**实现(flow/liberty_gen.py)**:对每个生成的 COMPLEX 单元输出 .lib 片段——
- **area** = 版图宽度 × 行高(锚定校验:NAND2X1 LEF 0.76×2.47=1.877200 与其 lib area 精确相等);
- **leakage** = 成员 `cell_leakage_power` 求和(管数不变);
- **引脚电容** = 接口输入引脚即基础单元引脚,直接取基础 lib 的 pin 电容(实测 COMPLEX1 引脚值与库逐位一致);
- **timing** = 成员 DAG 上的迷你 STA 在基础库 6×6(负载×摆率)网格上扫描,生成标准 delay/transition LUT(布局前估计:worst-arc、无线 RC,片段内注明);
- **power** = internal_power 表按成员 LUT 能量同网格扫描;
- **function** = 成员 liberty function 字符串按内部网全括号替换组合(空格=AND、+=OR、^=XOR、!=NOT),组合失败时留注释占位。

**接线**:main.py/flow_core 在校验门通过后写出 `COMPLEX<n>.lib`(写变化才落盘,不动 mtime 契约);与 .sp/.gds 同目录。

**局限与下一步**:时序/功耗为布局前估计(无寄生);签署级表征需 SPICE——.sp 已可直接喂 ngspice(未来校验通道);function 组合依赖基础 function 字符串,个别特殊单元(DS0000/P0002 形式)不可组合时降级为注释。

**验证**:269 单测通过(新增 test_liberty_gen.py:函数库解析、全词替换、真实簇生成+liberty.parser 回读)。

### 5.23 yosys 重跑求设计级面积收益:abc 阻塞分析与会计式落地(2026-10-09)

**abc 重映射路线被环境阻塞(两个独立原因,均已验证)**:
1. **yowasp-yosys 无法执行 abc**:wasm 进程无法派生外部 ABC 二进制——最小 AND 门设计的 `abc -liberty` 也在 "Extracting gate netlist" 后静默退出(exit 0 但无 stat 输出);对已映射 BLIF 则报 "Extracted 0 gates"(它只提门级逻辑,不碰已映射单元);
2. **MSYS2 pacman 深度损坏**:`pacman-key` 本身缺 makepkg 工具(parseopts 缺失),属安装级损坏;切换 TUNA/USTC 镜像后仍无法用,**镜像文件已还原**,未进一步动系统。oss-cad-suite(含 yosys-abc)为备选下载,未拉取(体积大、网络不稳)。

**方法论注意**:abc 按 function 映射且**不使用多输出单元**——adder 现有 4 个 COMPLEX 单元均多输出(2-3 个),即使 abc 可用也不会被选;这反过来说明本项目的收益是**物理性**(扩散共享/互连内化),非逻辑映射可得。

**会计式落地(yosys_eval.evaluateDesignSavings)**:基线=**yosys 独立直方图 × lib area**(直方图已与流程逐类型核对一致),收益=Σ 出现次数×(成员 lib 面积和−复合面积),复合面积=版图宽×行高。adder 实测:基线 2047.087;COMPLEX9(已采纳)=**+112.63(5.50%)**——比宽度口径的 3.06% 更高,因为 lib 面积含全矩形开销而复合版图打包更紧;独立参照 COMPLEX0 +28.6(1.40%)、COMPLEX1 +76.0(3.71%)、**COMPLEX10 −55.4(−2.71%,再次确认负收益)**。

**产物**:outputs/adder/COMPLEX{0,1,9,10}.lib 已生成并随快照入库(liberty_gen 的 .sp 重建路径,无需重跑挖掘);`runYosysMappedArea`/`buildExtendedLiberty` 已就绪,abc 环境修复后即可启用重映射对照。

**验证**:274 单测通过(新增 test_yosys_eval.py 5 例)。

### 5.24 yosys+abc 问题解决:手动解包 vendored 构建(2026-10-09)

**解决路径**(绕开 pacman 损坏与 yowasp 无 abc 两个故障):直接从 USTC 镜像下载 MSYS2 包 `mingw-w64-x86_64-yosys-0.51-2`(16.7MB),用 Python zstandard 解包到 **tools/yosys**(70MB,含 yosys.exe/yosys-abc.exe 与完整 share 树),补齐其 DLL 传递依赖(libffi/libgcc/libstdc++/libreadline+libtermcap/tcl86/zlib/libwinpthread)后**完全自包含**(无需 MSYS2 PATH)。`yosys_import.YOSYS_CANDIDATES` 把 vendored 路径列为第一探测项。

**验证**:最小 AND 设计 `abc -liberty` 正常映射为 AND2X1;完整 adder 综合(基线库)得到 707 单元、映射面积 2047.09(与会计式基线精确一致)。

**两个附带修复**:
1. **扩展库语法错误**:基础库文件末尾有游离 `}`(库闭合后再一个 `}`),`rfind("}")` 插入点错误——`buildExtendedLiberty` 改为花括号深度扫描找真正的库闭合;
2. **`#` 不是合法 liberty 标识符**:生成的 .lib 引脚 `cl1#A` 被 yosys 解析器拒绝——`libertyPinName` 统一映射为 `cl1_A`(注入安全:端口集合内一一对应),.lib 片段已重生成入库。

**扩展库综合结果**:extended 724 单元、映射面积 2039.11(基线 2047.09,−0.39%)——但 **abc 明确跳过全部多输出单元**(实测日志:"Detected 8 multi-output gates";我们 4 个 COMPLEX 全为 2-3 输出),complex_used=0,差异纯属 abc 重映射噪声。**结论性证据**:生成单元无法被 abc 逻辑映射复用,收益是物理性的(扩散共享/内化互连);要让综合器直接复用,应挖单输出模式。

**验证**:274 单测通过(真实 yosys 用例现跑 vendored 0.51)。

### 5.25 complex_used=0 归因修正:abc 按函数锥匹配,非"跳过多输出"(2026-10-09)

**用户质疑正确**:5.23/5.24 把 complex_used=0 归因于"abc 跳过所有多输出单元"是**错误结论**。受控实验推翻并找到真因:

| 实验 | 单元 | 设计 | abc 是否选用 |
|---|---|---|---|
| A3 | C2N 单输出,函数 !(AB),延迟 0.001,面积 0.5 | y=~(a&b) | ✅ 选 C2N |
| B3 | C2N 加第二输出 Y2(多输出) | 同上 | ✅ 仍选 C2N |
| C2O | 单输出,函数 ab+cd,延迟 0.1,面积 6.0 | y=(a&b)\|(c&d) | ✅ 选 C2O |
| 扩展库(延迟归零) | 真实 COMPLEX0/1/9/10,全部 4 张延迟表置 0.001 | adder 全综合 | ❌ 仍 0 用 |
| 扩展库(真实延迟) | 同单元 | adder 全综合 | ❌ 0 用 |

**真因**:abc 的 liberty 映射是**功能驱动的锥匹配**——它只从自己重新综合出的逻辑网络里找现成的函数锥,挑面积/时延最优的库单元;我们的 COMPLEX 函数(如 COMPLEX9 主输出 ab+cd,或 COMPLEX1 的 XNOR∘组合)在 abc 重新分解后的网络上**没有恰好匹配的锥**(综合会改变分解形状;`synth` 的 strash/if 分解与原始映射器不同),故不选。**与多输出无关**(B3 证伪),**与延迟无关**(归零实验证伪)。附带修正:实验 1 首次跑出"25 cells 无 C2N"是测试库合并错误的假象,非 abc 行为。

**推论**:让综合器直接复用生成单元,单靠"把 .lib 放进扩展库"不够——要么(a)在挖掘/生长时约束**单输出模式**且保持函数简单常见(如 ab+cd 这类),要么(b)按本流程的会计口径**预实例化替换**(COMPLEX9 直接替换 60 处 = 5.50%,这才是收益的正解)。(a)与 (b)可叠加。

**验证**:新增 test_yosys_eval 真实用例(自跳过):C2O 精确匹配实验固化,防回归。

### 5.26 综合复用路径打通:单输出+简单函数约束(2026-10-10)

**目标**:让生成的 COMPLEX 单元能被 abc 逻辑映射复用(AUDIT 5.25 的推论:abc 只选"函数锥匹配"的单元,adder 现有 4 个单元全多输出,0 用)。实现四件套:

1. **复用资格判定(flow/reuse.py)**:`reuseEligible(cluster)` = 单输出(仅一个逃逸成员输出脚)+ 函数 support≤4、逻辑深度≤4(深度只数"含运算符或≥2 操作数"的括号层,组合包裹不计)。组合函数复用 liberty_gen 的 `_composeFunction`。
2. **生长偏置(internalizeOnly)**:`grow_sequence_of_clusters(+_BasedOn)` 新增 `internalizeOnly`——只吸收"输出负载全部落在簇内"的邻居,吸收不新增逃逸输出,单输出性保持。
3. **流程接线**:main.py/flow_core 逐候选报告 reuse 资格;`requireReuseEligible`/`cfg.require_reuse_eligible` 可选门限(默认关,打开即只收单输出简单函数模式)。
4. **两个接口修复**(真 bug):① `_clusterInterface` 的 zip 截断改为按网名/位置配对,且"无网对象的外部输入"正确判为接口输入(修复前生成片段 inputs=0,abc 提前失败);② `_composeFunction` 成员引脚同名串扰——先做 `@@k@@pin@@` 唯一令牌化再单遍替换(修复前组合函数串入他成员的同名引脚)。

**端到端验证(真实 abc)**:单输出合成簇 [NAND2,NAND2,OR2](函数 ¬(ab)∨¬(cd),support 4/深度 4)→ .lib 片段 → 扩展库 → 设计 `y=~(a&b)|~(c&d)` → **ABC RESULTS: COMPLEX_SO cells: 1** ✓。另修 yosys abc 在 Windows 的临时目录混合分隔符问题(测试内 TMP/TEMP 正斜杠化)。固化测试:test_reuse 4 例(含真实 abc 端到端,自跳过)。

**现状与下一步**:adder 现有模式均多输出(测试钉住 top-10 全不合格),复用路径需在"复用模式"下重跑挖掘(`requireReuseEligible=True` + 生长 `internalizeOnly`),预期得到单输出简单函数的新模式族。280 单测通过。

### 5.27 双模式并存:物理库与综合复用库(2026-10-10)

**并存机制**:`AUTOCELL_REUSE_MODE=1` 时 main.py 切到复用模式——初始聚类 `singleOutputSeeds=True`(只保留接口逃逸输出=1 的种子,`_escapeOutputCount`)+ 生长 `internalizeOnly=True`(只吸收输出负载全在簇内的邻居)+ 输出目录隔离为 `outputs/<bench>_reuse`,物理模式快照不受影响;`requireReuseEligible` 门限兜底。

**加种子过滤的原因**:首轮实验证明 adder 初始聚类 top-30 **全部多输出**——单输出约束若只在生长/验收阶段,种子本身不合格就无从谈起;必须从种子开始。

**adder 对照实验结果(flow/reuse_experiment.py)**:

| 模式 | 挖掘结果 | abc 可用性 |
|---|---|---|
| 物理(现状) | 高频多输出模式(61×[NAND2,NAND2,OR2] 等),面积收益 5.50% | ✗ 0 用(锥不匹配) |
| 复用(新) | 单输出种子仅 5 个(最高频 2 次),合格 1 个:[XNOR2X1,AND2X1,OR2X1](x1,函数 !((A·B)^(C+D)),support4/深度4) | ✓ **REUSE PATH WORKS**(1 次) |

**权衡的诚实陈述**:单输出约束把 adder 的高频模式全部滤掉(61 次→最高 2 次),复用模式下这个基准几乎无挖掘空间——物理收益与可复用性在同一网表上难以兼得;复用库应面向"单输出、函数简单常见"的新挖掘目标(或接受低频),物理库保留现有多输出模式,两者并存供不同下游选择。

**过程修复**:① _BasedOn 分组仍用旧无序编码(与规范化 trace 前缀匹配失配)——补 canonical_pattern_code;② 实验手写片段引脚名必须与函数/验证设计同名(否则 abc 视为无效单元);③ 等价测试 spy 补新参数。

**验证**:281 单测通过;reuse_experiment 内置 abc 证明自跳过式。

### 5.28 架构重构:flow_core 消费 core.pipeline,第三份控制流副本消灭(2026-10-10)

- core/pipeline 增加 PipelineHooks 观察者接口(stage/log/pattern/metric/record/check_cancel/run_layout/result,默认 no-op,CLI 行为不变);路径全部参数化(liberty/spiceLib/blifDir 来自 FlowConfig,不再硬编码 gscl45nm)。
- gui/flow_core._mine/_phase2 改为委托 core.pipeline.runPipeline:_GuiPipelineHooks 桥接 GUI 事件面、取消、_generate_complex_layout 布局器(含 do_layouts 关闭时落盘宽度回退);ctx 状态经 result 捕获回填,页面继续可用。
- 等价测试(test_flow_parity)spy 重定向到 core.pipeline(GUI 与 CLI 现为同一实现),仍钉住两出口一致。
- 架构文档 ARCHITECTURE.md 更新;285 单测全绿。

### 5.29 架构重构:core/evaluate + core/external 门面(2026-10-10)

- core/evaluate.py 收编评估层:electrical/timing_power/routability/reuse/width_proxy/layout_sanity/benefit/liberty_gen/pdk_config 的公开面;core/external.py 收编工具层:ASTRAN 常量与运行面/gds_analysis/yosys_import/yosys_eval。
- core/pipeline 的依赖导入全部改走两个门面(blif_preproc/blif_pattern_growth/spice 星号导入保留,属 parse/seed/growth/export 层);test_facades 钉住"pipeline 绑定的对象与门面导出的对象是同一份"(杜绝双实现漂移)与"门面 Qt-free"。
- 验证:289 单测全绿(新增 4 例)。

### 5.30 性能层落地:CP-SAT 默认化与宽度代理训练管线(2026-10-10)

1. **CP-SAT 压缩后端设为默认**:`GUROBI_CL_SOLVER` 默认由 cbc 切为 cpsat(§5.20 双单元端到端证据:同预算下目标值优 2.5×、COMPLEX0 −8%);保留 CBC 显式可选与 ortools 缺失自动回退;失败语义(全零 .sol)与 option-3 恢复纪律不变。默认切换后,新生成的单元宽度将按 CP-SAT 口径(跟踪快照保持 CBC 产物直至重生成)。
2. **宽度代理训练管线化**(width_proxy.py):新增 `saveWidthProxy`/`loadWidthProxy`(Ridge 系数 JSON 持久化,加载补 n_features_in_ 与 ndarray)/`widthProxyModelStale`(模型 mtime vs 样本 mtime)/`trainOrLoadWidthProxy`(新鲜即复用,否则重训+持久化+LOO 报告);`core/pipeline` 改经该入口(输出目录 glob + 持久化路径 outputs/width_proxy.json,已加入 .gitignore);`core/evaluate` 门面导出全套。
3. **验证**:290 单测全绿(新增训练管线 roundtrip/复用/持久化一致 1 例);CP-SAT 后端 4 例保持;全量回归含等价测试。

### 5.31 CP-SAT 默认口径下的 adder 快照重生成(2026-10-10)

**动机**:§5.30 默认后端切为 CP-SAT 后,受跟踪快照仍是 CBC 产物——口径不对称。本轮重生成闭合。

**基线口径验证(关键)**:11 个库单元(NAND2/OR2/XNOR2/XOR2/OAI21/AND2/AOI21/NOR2/AOI22/NAND3/INV)在 CP-SAT 下宽度与 CBC 快照**逐位一致**(changed=[])——小单元上两后端同优,基线无需重生成,面积对比口径保持连贯。

**新快照(outputs/adder,全部过 layout_sanity 校验门)**:

| 单元 | CBC 旧宽 | CP-SAT 新宽 | 变化 |
|---|---|---|---|
| COMPLEX0 | 2.28 | **2.09** | −8% |
| COMPLEX1 | 4.37 | **3.61** | −17% |
| COMPLEX9 | 3.61 | **3.42** | −5% |
| COMPLEX10 | 5.89 | **4.37** | −26%,由亏转盈 |
| COMPLEX11(新) | — | 3.80 | 新生长模式 |

**收益重估**:bestRecord-adder 总节省 22.8(3.06%)→ **85.5(11.46% vs ASTRAN)**/108.3(13.81% vs GSCL)——COMPLEX10(54×4)首次入选且为正收益;宽度代理 LOO MAPE 16.4% 复现。快照整体(含 COMPLEX11 .sp/.lib/.gds 与 .png)作为一次连贯快照提交。

### 5.32 代码质量收尾:日志系统/重复消除/命名与文档约定(2026-10-10)

- **dfx/日志**:新增 `core/log.py`(getFlowLogger:进程级单例、级别过滤、时间戳、控制台 handler),pipeline 的关键里程碑输出(astranArea/yosys 交叉校验/宽度代理报告)改走日志,CLI 输出不变;测试用 StringIO handler 钉住机制与级别过滤。
- **大函数/重复**:core/growth 两函数的邻居分类块(各 ~50 行、4 层嵌套)抽为共享 `_collect_neighbor_features`(snake_case),行为不变(测试全绿)。
- **命名/文档**:ARCHITECTURE.md 新增"代码质量约定"——新代码 snake_case、公开 API 兼容保留、>80 行函数必拆、日志统一入口、≥6 入参改配置对象。
- **验证**:299 单测全绿(新增 test_log 3 例)。

### 5.33 多 agent 并行落地四件套:第二 PDK .rul / SMT 参考实现 / LLM 提示 / pin accessibility(2026-10-09)

用户汇报"多 agent 完成四项工作",验收发现本仓库无对应产物(工作区干净、无新分支/ stash,RESEARCH 文档里仍是"下一步计划"条目)——结论:那批工作不在本仓库。随后按用户指示在本仓库逐项实现并测试:

- **4.1 第二 PDK .rul**(tools/astran/build/Work/tech_sky130.rul、tech_gf180.rul):几何全部经主源 LEF 核对(skywater-pdk-libs-sky130_fd_sc_hd、gf180mcu_fd_sc_mcu7t5v0 的 tech/cell LEF)。**修正脚手架两处数字**:gf180 路由栅格 0.28→0.56(SITE GF018hv5v_mcu_sc7 0.56×3.92=7 轨)、供电 0.44→0.60(rails ±0.30);sky130 的 0.34/0.48 确认无误。未核实规则行继承 freePDK45 并标注 PLACEHOLDER(ASTRAN 内部规则非权威,权威是 PDK DRC deck)。pdk_config 新增 `loadTechnologyRul` 解析器(确定性),sky130/gf180 状态 scaffold→draft(opt-in 语义保留),test_pdk_config 8 例全绿(含"文件存在且可解析"钉住)。
- **4.2 SMT 联合 folding+placement 参考实现**(flow/smt_cell_placer.py,P2-13 落点,8 单测):CP-SAT 建模,串联链=内节点度 2 识别,链成员同行+首尾相接(共享扩散);折叠受腿宽制造上限约束(无上限时折叠永远无收益,ceil 只会加宽);NoOverlap2D;目标 min(1000·宽度+腿数)。关键修正:单行/极性模型给 COMPLEX0 4.75µm,与 ASTRAN 2.09 差一倍——ASTRAN 每极性用两排扩散堆叠,参考模型必须同样支持两行/极性(2.47µm)。简化项如实记录(平行组共享、扩散断、行粘性未建模),宽度是理想化下限。
- **4.3 多模态 LLM Agent 资源整合**(flow/llm_hint_provider.py,P2-15 落点,9 单测):Hint 协议+离线确定性提供方+OpenAI 兼容多模态提供方(文本网表+GDS 截图→JSON,任何失败降级 [] 并记日志)+内容寻址缓存(sha256)+`suggestHintsBatch` 线程池并行。env 门控 `AUTOCELL_HINT_MODE`(默认 off),core/config 加 hintMode,core/pipeline 在 SPICE 导出点挂提示日志(仅报告)。测试:离线确定性、门控、缓存命中免网络、LLM 故障降级、批量并行保序、from_env 读 hintMode。
- **4.4 pin accessibility 度量**(flow/pin_accessibility.py,5 单测):按 §三 论文(ISPD'23/DAC'24/FastPass/DATE'23/ISCAS'24)的可检查结论实现 on-track(引脚中心落轨道网格)/blocked(多晶跨引脚金属)/crowd(同轨列引脚数),单元分=均值;与 GDS 查看器同一 log 校准纪律。合成 GDS 精确定住 1.0/0.5/0.9 与离轨 −0.5;COMPLEX0 实测 0.500(VCC/GND 轨 x=1.045 离格,VCC 多晶阻塞 0.00)。调试记录:loadCellGeometry 曾丢失图层信息导致"金属1自身+轮廓被判为 poly 阻塞"(A 引脚 1.0→0.5 误报),修复为保留 (layer, pts)。
- **RESEARCH 文档膨胀事故**:5623712 的"刷新"把 doc/RESEARCH_AND_OPTIMIZATION.md 写成 28MB/32.4 万行——同一 14 行状态块重复 2.2 万次(唯一行仅 710),原 17KB 文献综述被覆盖。恢复 1ba428a 版本为基底,重写状态表(新增 SMT/LLM/pin-accessibility 行)、新增 §三(12 篇 pin accessibility 论文+整合说明)、§四(四项工作证据)、§五(更新版下一步 9 项),旧三/四/五 重编号为 六/七/八。教训:文档生成脚本必须校验输出大小/唯一行占比,写回前 diff。
- **验证**:新增 30 单测(SMT 8 + LLM 9 + pin-accessibility 5 + pdk 4 新增/改写 + 既有 4),全量回归见提交记录。

### 5.34 全面命名整改:模块/标识符/文件夹三级 snake_case(2026-10-10)

**动机**:1ba428a 只重命名了 13 个核心入口;仓库仍残留约 650 个 camelCase 标识符、
11 个 camelCase 模块文件、4 个 camelCase 文件夹,与 ARCHITECTURE 的 snake_case 约定
不一致。本节记录三级整改(每步全量单测绿,行为零变化)。

**修复(三个提交)**:

1. `ca6caa7` 模块文件名:`Astran.py→astran.py`、`BLIFPreProc.py→blif_preproc.py`、
   `BLIFGraphUtil.py→blif_graph_util.py`、`BLIFPatternGrowth.py→blif_pattern_growth.py`、
   `GDSIIAnalysis.py→gds_analysis.py`、`GNNModel.py→gnn_model.py`、
   `BLIFGNNTraining.py→blif_gnn_training.py`、`globalVariables.py→global_variables.py`、
   `resultAnalysis*.py→result_analysis*.py`、`replay_seperateadder.py→replay_separate_adder.py`
   (typo 一并修复);导入、模块对象引用(GUI flow dict 的 "Astran" 字符串键、
   `monkeypatch.setattr(Astran, ...)` 目标)、文档同步改写。
   **坑**:第一版正则用 `Astran\.(?=[A-Z_])` 只匹配大写属性,漏掉
   `Astran.buildAstranCommands` 这类"模块.小写函数"引用,6 个测试立刻抓出。
2. `d205c21` 标识符 633 条(91 文件):机械 snake_case + 语义/typo override——
   `loadOrignalGSCL45nmGDS→load_original_gscl45_gds`、`dumpedPaterns→dumped_patterns`、
   `cluserSeq→cluster_seq`、`colorArrtibute→color_attribute`、
   `cellIdsContained→cell_ids`、`cellsContained→cells`、
   `stdType2{GSCL,Astran}Area→{gscl,astran}_area_by_type`、`*2Obj/*2Cnt→by_name/by_type`、
   `drawColorfulFigureForGraphWithAttributes→draw_graph_figure`、`ori*→orig*`、
   `Que→queue`、`SeqsId→idx`。
3. `9532d0c` 文件夹:`pySrc→flow`(与 FlowConfig/flow_core/get_flow_logger 的既有词汇
   一致)、`stdCelllib→std_celllib`、`originalGSCL45StdCells→original_gscl45_cells`、
   `originalAstranStdCells→original_astran_cells`;80 个代码/文档文件路径替换,
   conftest `in_pysrc→in_flow`;基线 .Astranlog/.run 与 outputs/ 数据文件只随目录
   移动、内容不动(它们是历史产物)。

**有意不改(白名单,均有据)**:Qt 信号/方法名(Qt 惯例 camelCase,重命名会破坏
override 与 connect);注释/文档里引用的 ASTRAN C++ 标识符(`foldTrans`、
`seriesFolding`、`nGraphRouter` 等,改了就与 C++ 源对不上);matplotlib kwargs
(`shrinkA/shrinkB`);**bestRecord-* 文件格式 token**(`patternCode`、`saveArea`、
`clusterNum`、`designOverallArea`…作为受保护字面量保留,committed outputs 字节
不变,重生成 diff 为空);数据文件名(`cellsAstranFriendly.sp`、`gscl45nm.lib`)。

**抓到的真缺陷**:test_flow_parity 跳过表头行的条件是格式耦合字符串
`"patternCode" in line`,机械替换误改为 `"pattern_code"`,解析器把表头当数据行、
断言失败。全库 grep 确认保护名单之外这是唯一一处格式耦合字面量,已还原。

**钉住**:`test_naming` LEGACY 名单从 11 个扩到约 130 个(模块名 + 入口函数 +
数据模型属性 + 流程全局);死代码 GNN 模块(`gnn_model`/`blif_gnn_training`,
TensorFlow 依赖缺失无法导入)与 test_naming 自身排除在扫描外。

**证据**:324 个单测 ×4 轮全绿;`git diff flow/spice.py` 确认导出模板字面量未动
(.sp 重生成字节相同);残留 camelCase 扫描只剩 11 个、全部位于 bestRecord 格式
字面量/死注释内。

**并行协作记录**:整改开始时另一会话正在仓库内落 P2 批次(llm_hint_provider/
smt_cell_placer/pin_accessibility);等待其提交(ac2e4c4)后窗口期内完成全部三批,
避免全库改名与在写文件冲突。

### 5.35 完整 SMT 引擎:折叠+扩散共享+摆放+布线的联合 SAT 编码(2026-10-10)

用户指令"做完整的 SMT 引擎项目,写完整的 SAT 编码"。在参考实现(smt_cell_placer,
仅宽度下限打分)基础上,新增 flow/smt_engine/ 包(六模块:netlist/layout_model/
route_model/gds/verify/__init__),把布局与布线全部编入 CP-SAT:

- **布局编码(layout_model)**:折叠(腿宽制造上限)+串联链共享扩散(内节点度 2)+
  平行组强相邻(网对交替朝向,共享端恒同网)+扩散断间距(异网端同行析取)+每极性
  两行+栅对齐软目标+**接入点列互斥**(分 P/N/G 三区:同区异网禁同列、跨区 P/N
  同列合法——真实 GSCL45 NAND2X1 正是 P/N 端同列)。
- **布线编码(route_model)**:每列**双区竖段**(N 区轨 0..4 + P 区轨 2..5,同列
  P/N 竖段 y 区间分离不短路;跨区同网合并成一条);**几何覆盖**(竖段覆盖判定用
  railY 的 min..max y 区间而非索引区间——GND 轨 4 在底部,[0,4] 索引覆盖全部
  轨但几何只覆盖轨 0/1,这正是真实 GND 竖段不堵上轨的原因);栅接触=水平段与
  poly 交叉(竖段与 poly 平行无法接触);连通=接入列区间被竖段/段全覆盖+相邻
  覆盖列必有桥接段;交叉安全=异网竖段几何覆盖段轨即禁(信号与电源竖段都查)。
- **输出与自检**:gds.py 产出诚实 GDS 头(1um/1nm,与 ASTRAN 假 UNITS 相反),
  层号沿用 ASTRAN stream map,可被 layout_sanity(units_per_um=1.0)与
  pin_accessibility 直接消费;verify.py 从解重算几何全量复验(块相接/重叠/断
  间距/接入覆盖/栅接触/交叉/连通),模型与检查器共用同一几何语义。

**调试记录(每一条都是模型语义 bug,verify 或二分抓出)**:
- 内节点判定只数源漏端子→把"既当栅又当源漏"的网(cl2#a_2_54#)误判为扩散共享
  点,强制三器件错误相接;修正为含栅端子计数==2。
- 平行组朝向按原始 drain/source 序交替→共享端异网短路;修正为网对交替
  (L0=min 网,奇偶翻转),与端子序无关。
- 共享端过滤:纯内节点(n1)不进接入点与互斥(扩散共享已电气完备)。
- 腿宽量化 round→ceil(1.0µm 管 round 成 5 列=0.95µm<实际宽,非法)。
- 栅中心列与块端列同列(小器件量化伪影)→同器件栅/端不互斥,布线交叉安全兜底。
- 段端点"至少一端同网竖段"过强→删除(栅接触/pin 是合法悬空端);浮段由目标排除。
- 交叉安全 gt/lt 误伤(空列 gt+lt≥1 恒假)→covers 布尔与 owner AND 后判禁。
- 竖段覆盖用索引区间(lo≤t≤hi)→几何覆盖表(railY min/max),否则 GND 竖段
  [0,4] 堵死全部轨。
- 同列 P/N 端互斥过严→双区竖段(N/P slot 独立,同列共存合法)。
- cov 覆盖布尔对空 allowed 表→全 forbidden 禁空变量域→模型必然不可行;
  按 slot 物理可覆盖轨(nCover={0,1,4}/pCover={2,3,5})裁剪,不可覆盖对不建
  cov 变量、段检查跳过。
- 假接入点:rails 推导按"列被器件覆盖"而非"端所属器件"→链成员内部列被误算
  成 Y 的 N 轨接入点(列 2 的 MnA 扩散是 n1 不是 Y);diffusion_access_points
  改为返回 (col, device) 端级信息,轨由端器件推导。

**适用边界(如实)**:≤8 管单元(INV/NAND2 级)全链闭环——NAND2 6 列、verify 0
违例、pin accessibility 0.933、sanity 通过;14 管 COMPLEX0 布局 OPTIMAL
19 列(3.61µm)但联合布线模型不可行(4 轨+一列双竖段的资源限制,真实版图靠
更多层/迭代布线)。引擎对不可布单元干净报告(route INFEASIBLE),绝不静默。

### 5.36 SMT 引擎第三轮:井边界合并修复 P/N 半区断连 + poly 层跳线 + 轨道级精确连通(2026-10-10)

在 §5.35 引擎上继续实现 poly 层跳线(§五 待办 2)时,verify 抓出一个
**出货级硬伤**:双区竖段模型里 N 区竖条(y ≤ 0.994)与 P 区竖条(y ≥ 1.476)
被井边界隔开 0.48µm,永不相交——任何跨半区网络(NAND2 的 Y、所有输出)在
GDS 里都是两个电学孤岛。§5.35 的模块 docstring 声称"跨区同网合并成一条",
实现从未做到,而列图连通检查把它当连通放行。

**(1) 井边界合并(reachB):同网双槽列的两根竖条强制延伸到井边界
(y = H/2)重叠 0.07µm 合并**——这是跨半区网络的唯一 N↔P 接合点,与真实
GSCL45 单元一致(竖条从 P 扩散直通 N 扩散穿过井边界区)。异网双槽列(NAND2
的 GND|VCC 同列,真实特征)只允许一根延伸,否则在 y = H/2 处重叠短路。
GDS/verify 同步:竖条按 reachB 延伸绘制,检查器复验合并与互斥。

**(2) 连通性从"列图"升级为"轨道级精确物理图"**:旧模型与检查器以列为
节点,把同一列的所有 N 侧/ P 侧存在混为一个节点——轨 0 段与轨 1 段在无竖
条的列上相邻(不同 y,物理断链)被误判连通。新模型:段按 (轨,列) 建图、
竖条按几何覆盖接入其轨、双槽合并、栅条纹合并所有交叉;SAT 侧补"转换约束":
段在列 c 结束 + 另一轨段在列 c 开始,必须发生在 join 列——同网双槽竖条
(两端桥均须 M1,竖条只触 M1)或该网栅条纹(左端桥须 M1:poly 段止于列
边缘,够不到列中心的栅;右端桥任意层——M1 接触/poly 合并都成立);转换
列遍历范围含跨度末列(曾漏 cmax,桥在末列无约束)。

**(3) poly 层跳线**:段级 M1/poly 层选择变量(目标加 15/段,偏好 M1)。
合法域:两端列该轨无源区(poly 过有源=晶体管;唯一例外是交叉列的同网
栅)+ 交叉列(左列)所有栅必须属于该段网(poly-poly 交叉短路,同网合并);
CP-SAT 自动机(每 网×轨)约束每条 poly 连段必含同网栅——栅合并是 M1↔poly
唯一接合点,模型无 M1-poly 接触;层邻接规则:同网相邻段不得换层(无线头=
断线)、异网相邻段不得同层(顺带补上旧模型漏掉的 M1-M1 邻接短路检查)。
GDS 输出 poly 矩形;gate-contact 循环原死分支(route.col_owner 已不存在)
改为:仅 M1 段画接触、poly 段直接合并、无任何段时抛错。

**(4) 确定性**:ortools 并行搜索在等代价最优解间随机选取——同模型两次
运行路由不同(复现:同进程两次 synth 得不同 hseg)。按 AGENTS.md 不变量
9 固定 `num_search_workers=1`(layout 与 route 两求解器),并修正模型构建
中若干 set 迭代无序(diffusion/power 接入点、bar-connect 循环)。

**边界实证(如实)**:规则结构上旧"≤8 管"边界已消失——NAND3/4/5/6
(6/8/10/12 管)全部全链闭环,verify 0 违例,且均为 M1-only(pj=0);
14 管 COMPLEX0 布局 OPTIMAL 19 列(3.61µm)仍不可布(不规则结构,冲突
列全部有源,poly 也无处落)。poly 跳线端到端实证:构造"四轨全被 GND/VCC
竖条封死+栅网必经"单元(手放:MnL 行1 三腿、MpX 行0、MpR 行1)——M1
模型 INFEASIBLE,跳线模型 7 段 poly OPTIMAL + verify 0 违例。

**测试**:新增 5 例(同网双槽合并 reachB/异网双槽互斥/pj 合法域三违例/
pj 必用单元端到端/M1 最优不变),引擎测试 16 例,全量 340 通过。

### 5.37 参考实现收紧:平行组扩散共享 + 扩散断距 + 批量对照表(2026-10-10)

用户指令"§五 第 2 项:SMT 批量评分对照,把平行组扩散共享与扩散断距建模
进参考实现后收紧下限,直到 SMT 相比 ASTRAN 有明显收益为止"。

**(1) 参考模型(smt_cell_placer)收紧为块级结构**——与引擎同构:
- `find_parallel_groups`(同型同网对)+ `build_diffusion_blocks`(链/组/
  单管,定向成员:链从外网走内节点、组按网对交替 L0=min、单管 source
  左/drain 右)——与 `smt_engine.netlist` 的块结构逐字段一致(有单测
  固定 parity);
- 组内成员强相邻(同排 + end==start,共享扩散),与链同一约束;
- **扩散断距**:同极性同行块对,触端异网时两个方向取析取,最小一列
  gap(ASTRAN wGaps);
- `find_series_chains` 补"内节点不得同时是栅"检查(与引擎一致,COMPLEX0
  的 cl2#a_2_54# 类节点);
- 求解器固定单线程(`num_search_workers=1`,并行搜索在等代价最优解间
  随机选取——与引擎同因同修,AGENTS.md 不变量 9)。

**(2) 批量对照表(`--dir` 全快照)与新鲜度检查**:
- 对照行:smt 宽度 vs `.Astranlog` 记录的 ASTRAN 宽度 + ratio;
- 新鲜度改为**晶体管计数比对**(日志 "Number of transistors before
  folding" == .sp 器件数)。宽度地板启发式(astran ≥ max(P,N)/2)被否决:
  实测 ASTRAN 器件足印约 1–1.4 列/器件(与 .sp W 无线性对应——0.5µm 与
  1.0µm 器件画成 ~0.225/0.26µm 扩散),重生成 COMPLEX0 复现 2.09µm
  证明旧日志本就是新鲜的;§5.6 的 COMPLEX1 30 vs 26 类陈旧只有计数
  能抓住。

**(3) 实证(如实)**:
- **明显收益已出现**:multiplier/COMPLEX0(22 管)SMT 3.99µm vs ASTRAN
  5.51µm——窄 27.6%(精确打包揭示退火/压缩余量,正是打分器的意义);
- 小单元(≤14 管)SMT 偏宽:每器件 0.19 网格量化(0.5µm→3 列)vs ASTRAN
  ~1 列/器件足印——参考宽度在规则小单元上是保守上界,在复杂单元上是
  下界;对照表如实标注;
- adder 快照用 vendored ASTRAN 重生成全部 5 单元(~57 分钟,串行)——
  **逐单元复现旧宽度**(COMPLEX0 2.09 / COMPLEX1 3.61 / COMPLEX9 3.42 /
  COMPLEX10 4.37 / COMPLEX11 3.8):快照日志本来就是新鲜的(§5.6 的
  COMPLEX1 30 vs 26 陈旧属于更早快照,已在此前的重跑中消除);
  `.gds` 由当前 `.sp` 重写,快照自洽。另:重生成还顺带确认了 ASTRAN
  器件足印约定——0.5µm 与 1.0µm 器件画成 ~0.225/0.26µm 扩散(约
  1–1.4 列/器件),与 .sp W 无线性对应,这就是小单元 SMT 偏宽的根因。

**测试**:参考实现 13 例(新增平行组结构/引擎 parity/组共享验证/断距代价/
新鲜度),全量 345 通过。

### 5.38 全面 layout 正确性检查:异网 gate 同列 poly 短路 + 浮空栅接触(2026-10-10)

用户指令"全面检查 layout 正确性"后对引擎、参考实现与 ASTRAN 快照做了
系统性检查,抓到并修复两处真实 layout 缺陷(均为旧代码遗留的模型语义
缺口,verify 之前未覆盖):

**(1) 异网 gate 同列 = poly 短路(layout_model)**:接入点列互斥的
G-G 分支原先无条件放行("poly stripes may share a column")——同网
栅条合并成一根直 poly 合法(栅对齐软目标的收益),但**异网**栅同列
就是两根重叠 poly 条合并=短路,GDS 会画成一条。修复:异网 G-G 强制
gate 列互斥(带 leg 存在性 jlt 字面量,与 P/N 分支同模式)。测试:
跨极性强制 A/B 栅同列 → 模型 INFEASIBLE。

**(2) 浮空栅接触(route/verify/gds 三处统一)**:栅接触语义原来是
"段 (t, c-1) 或 (t, c) 都算穿过栅列 c"——但栅条在列**中心**
(c+0.5)·g,段 (t, c-1) 止于列边缘 x=c·g,根本不接触栅——GDS 画
出的接触只连 poly、浮空于 M1。实测 NAND2 解里 A@col1 与 B@col4 都
用了这条宽松边。修复:三处统一为"段必须真正跨过栅列中心"——
SAT 的 gate-access 只认 (t,c)(M1 接触或 poly 合并都算)、verify 的
栅访问检查与 BFS 的栅边同步收紧、gds 只画穿过段的接触。测试:手工
构造"仅宽松边"路由 → verify 拒收。

**ASTRAN 快照全量体检**:13 个 COMPLEX 单元(adder 5 / ctrl 1 /
max 3 / multiplier 4)全部通过 layout_sanity(0 违例),pin 分
0.325–0.536——快照 layout 正确性确认。

**测试**:引擎 18 例(新增 2),全量 347 通过。

### 5.39 外来 Verilog 一键入胞工具链:lint 预检 + 可续跑并行队列 + 展平/验证/驱动(2026-10-12)

用户场景:只给一个 Verilog 模块,要求按"高频子块 merge"路线用
ASTRAN 评估面积收益。首轮全程手工跑通(综合→验证→划分→展平→逐块
版图)后,将其中四类人工踩坑固化为工具:

**(1) `flow/astran_lint.py`(预检,毫秒级)**:复刻 ASTRAN spice.h
解析契约——晶体管行必须 M 开头(本次实证:`g0#M0` 前缀导致整网表
加载中止、"Cell not found");C/D 开头器件被静默跳过、X 开头变
实例;模型名须字面 PMOS/NMOS;`L={param}` 经 atof 得 0;`+` 续行
整行被忽略(W/L 必须在 M 行);`.END/.MODEL` 截断、嵌套 .SUBCKT 拒收;
缺 VCC/GND(默认电源网)与 >40T 单 cell(超出已验证 36T 区间)给警告。
对库文件 cellsAstranFriendly.sp 与既有 COMPLEX*.sp 冒烟全过。

**(2) `flow/astran_queue.py` + `run_astran_for_netlist(work_dir=)`**
(断点续跑 + 安全并行):"禁止并发"的根因是 LP 文件落在进程 cwd;
现每 cell 独立 cwd(`<outdir>/.lpwork/<cell>/`,已加 gitignore),
并行不再互踩——**AGENTS.md 并发不变量据此修订**(仅经队列时允许)。
manifest(`.astran_queue.json`)记录 sp_mtime/宽度/耗时,`--resume`
按既有缓存契约(sp 未变 + gds 在)跳过已完成 cell;lint 作为硬门,
0×0 结果一律记失败不静默。ASTRAN 另在 .gds 旁重写 GDSIILTable.txt
(designmng.cpp:336,内容确定性),并行时同内容覆写,风险已记录。

**(3) `flow/gate_flatten.py`(划分+展平)**:解析 yosys 映射网表
(含 `\name[0]`/`$` 转义网名)、按连通性贪心聚类到晶体管预算内
(默认 ≤36T,即历史已验证上限)、发射 M 前缀正确的晶体管级 .subckt;
输出端口按"网被块外消费或是模块输出"推导,全程确定性(不变量 9)。

**(4) `flow/logic_verify.py`(验证模板化)**:yosys 分别导
gold(综合后)与 gate(abc 映射后,`write_blif -gates`)两种 BLIF;
`.names` 按覆盖表语义、`.gate` 按 liberty `function` 字符串求值
(解析器支持 `! * + ^` 与**相邻即与**的 liberty 习惯、多输出 cell
的懒引脚求值避免 YS/YC 伪组合环);≤20 输入穷举、否则种子随机采样。
对真实 gscl45nm.lib 与 yosys 产物验证通过(含反相 MUX 语义)。

**(5) `flow/verilog2cells.py`(一键驱动)**:串起六步(synth→
verify→partition→flatten→lint→queue→report.md+PNG);基线宽度按
lib 面积 ÷ 2.47µm(不变量 10 等行高)。toy 模块(4 门)全链实证:
映射 4 cell、穷举 8/8 等价、36T 单块 lint 干净。

**过程中第二次踩到 360 查杀**:布局跑到一半 Astran.exe 被隔离
(二进制凭空消失,日志 "拒绝访问"),按预案从同目录 Astran.keep
恢复——已是第三次发生,AGENTS.md 计数已更新。

**测试**:新增 42 例(lint 19 / queue 8 / flatten 8 / verify 7,
另有 verilog2cells 冒烟 2 例中面积解析 1 例免 yosys)。

### 5.40 一键链补强:宽度代理预筛 + liberty 闭环 + GUI 页签(2026-10-12 第二批)

承接 §5.39,把"外来 Verilog → 自定义 cell"链路的三个缺口补齐:

**(1) 划分预筛(verilog2cells --partition-search)**:候选划分(预算
8/16/24/36/48T)先用仓库 WidthProxy(outputs 基准语料,n=13,ridge on
n_cells/n_transistors/base_width)预测总宽度再动手——toy 实证:预测
4.65µm vs 实测 4.37µm(误差 6.4%)。语料不足或 sklearn 缺失时安静降级
回默认预算。报告含预测 vs 实测对照表。

**(2) liberty 闭环(block_liberty.py + --liberty-closure)**:为每个
合并块生成 .lib 片段——函数经成员 liberty function AST 代入组合
(懒引脚求值防多输出伪环)、面积=实测宽×2.47(不虚构)、输入电容按
扇出求和、max_capacitance 抄驱动成员——合并进基础库后 abc 重映射
**原始 Verilog**(不走 BLIF:read_blif 产 $lut 而 abc 只认 $_AND_ 系,
曾静默"nothing to map",基线面积全 0,此为本次实证排掉的第二个集成
坑)。toy 实证:genlib 成功加载 BLK0(26th cell),abc 按每输出锥全
面积计价未选用(0% 收益,诚实记录)——多输出块在闭环里天然吃亏,
单输出块(CC_MAJ 型)才有得赢,这正是既定"单输出+简单函数"方向
的旁证。

**(3) 缓存契约修复(不变量 7 的镜像个案)**:verilog2cells 重跑时
无条件重写 BLK*.sp → mtime 失效 → --resume 恒失效(一次完整 22 分钟
重跑实证)。修复为"内容不变不重写"(与 export_spice_netlist 同契约),
修复后全链重跑 1.4s(0s 复用版图)。

**(4) GUI 自定义模块页签(gui/tabs/custom_module.py)**:文件选择/
选项(jobs、预算、resume、partition-search、liberty-closure)/运行
取消(worker 线程 + should_cancel 钩子直插队列逐 cell 检查点)/日志
复用 LogView/结果报告渲染 + 版图复用 GdsCanvas。主流程运行中禁用
(主流程仍共享进程级 LP cwd,队列的 per-cell cwd 只护队列客户)。

**过程中抓到 GUI 启动级回归(非本批引入,d205c21 批量改名误伤)**:
rowCount()/selectedRows() 被一并改成 snake_case(row_count()/
selected_rows()),patterns/pdk 表与 layouts 图层面板一碰数据即崩。
三处修复(patterns.py、gds_canvas.py、pdk.py 共 5 个调用点),并对
gui/ 全量做了两轮 Qt 方法族 grep 清扫 + offscreen 实例化冒烟(9 页
全部通过)。**教训已固化进 AGENTS.md 坑清单:批量改名不得覆盖 Qt
API**。

**测试**:新增 16 例(block_liberty 7 / queue 取消 1 / 驱动钩子 1 /
verilog2cells 冒烟 1 含面积解析);全量 396 通过(6 个 test_smt_engine
失败属并行会话在途改动,与本批零依赖)。

**§5.40 勘误（用户质询触发）**：liberty 片段面积原按"实测宽×固定 2.47"计——该系数虽源自 astran 几何常量，但在 geometry 覆盖（GUI/脚本）下会静默失真。已改为**实测宽×实测高**（同一 `Cell Size (W x H)` 日志行解析，队列 CellResult.height 通道，常量仅兜底），默认几何路径数值不变（toy BLK0 仍 10.7939µm²）,并对实测行高偏离 2.47 的运行输出"基线不等高"警告（不变量 10）。

## §5.41 ASTRAN 去 GUI 化（console 化）+ compaction 模型 JSON 通道（2026-10-15）

本节记录 ASTRAN→Python 替换计划的前两个阶段（多 agent 并行落地，集成验收）。

**(1) wxWidgets GUI 全量剥离（阶段 0）**：ASTRAN 从 wxApp 改为纯 console
二进制。删除 11 个 GUI 文件对（icpdApp/icpdfrm/wxinterface/wxcircuit/
wxrules/wxabout/wxautocell/wxpreferences/wxfp/wxicons，−6408 行）与
`bin/wx-config` shim；新增 `src/main_console.cpp` 复刻原 `--shell` CLI 契约
（含 `astran> read <script>` 序列与 REPL，EOF 退出为唯一有意偏离）；
`util.h` 的 wxExecute/Redirector、`router.h` 的 wx/process.h 摘除；
`build_astran.sh` 去 wx 前置，`-mconsole` 链接 + strip 保留。二进制
1.53→1.04 MB，仅依赖 MinGW 运行时。`Cellgen.exe`/`astranrun.exe` 仍链
wx DLL，`build/bin` 的两个 wx DLL 必须保留（打包勿清理）。

**对拍方法学与一个重要发现**：新旧二进制在 3 个 cell（AND2X1/INVX1/
COMPLEX0）上对拍，`ILPmodel.lp` 逐字节一致、日志归一后一致、宽度一致。
但 **GDS 逐字节一致在生产 shim 下不可达——旧二进制对自己也不可达**：
生产 CP-SAT 后端 8 线程 + 时限是时序敏感的，`ILPmodel.sol` 逐次漂移
（旧vs旧实测差 230–328 字节）。这**不是去 wx 引入的**（既有问题，不
变量 8 在"求解后端"这一层早已不成立）。用钉死 1 线程的测试 shim
（`flow/_stage0_check/gurobi_cl_det.cmd`，仅测试用）后三 cell 的 .sol 与
GDS（时间戳归零后）全部逐字节一致；`GUROBI_CL_SOLVER=cbc` 在固定 LP 上
亦确定。**遗留决策（证据已给、未擅自切换）**：是否把生产后端钉为
1 线程或默认 cbc——钉死会改变再生成快照的宽度，属全局行为切换，留
待用户决策。

**(2) compaction 模型 JSON 通道（阶段 1 + 集成）**：见 fd3525c 提交说明。
集成补齐了 `compaction.cpp` 的调用点（LP 写毕后调 `astranDumpModelJson(fn)`，
env `ASTRAN_MODEL_DUMP` 门控、永不抛出）与 Makefile 规则，重建二进制后
e2e 实证：AND2X1 全流程下 dump 出 3774 变量/6430 约束的 model.json，
shim 消费 JSON 路径（日志出现 "(JSON model path)"），与 legacy 路径
产出**相同 SHA256 的 .sol**、相同宽度 0.95×2.47；env 未设时行为不变。

**(3) M2 落地 + verilog2cells 引擎选择（阶段 2）**：见 cce34b3 提交说明
（7-track 域 + M2/vias、4 个引擎缺陷修复、`--engine auto|smt|astran`、
透明回退、全量 430 绿）。

**(4) 大 cell 引擎设计（阶段 3）**：`doc/STAGE3_BIGCELL_ENGINE.md`
（SA move set 忠实移植 + Pathfinder 拥塞协商路由 + CP-SAT 窗口分解，
`--engine` 阶梯中置，~18–22 人周）。其中勘正一处长期误记：项目史料的
"36T → 3.61 µm" 实际对应 30T 的 COMPLEX1；36T 的 COMPLEX10 为 4.37 µm。

## §5.42 bigcell 引擎三轮迭代：槽位几何模型 + 介面视图（2026-10-16）

阶段 3 实施进入"测试→验证→替换"循环。第一轮 17-cell 全量基准
（100 分钟，flow/_stage3_check/bench_int1）只关闭 2/17（精确档小
cell），但失败全部收敛为具体缺陷：

**(1) verify 镜像假阳性（f3ece2c 修复）**：place_sa 的 mirror_block
翻转块的暴露端（成员反转+左右交换，电学等价），place_row 按镜像朝向
正确共享 VCC 而省断列，但 verify 的 _nets_touch 从网表重建未镜像的
基础块——每个镜像对都误报"diffusion break missing"。verify_cell 增
可选 blocks 视图参数（默认行为不变），engine 传入 SA 精炼排序的朝向
感知块列表。**教训：镜像状态是布局的事实，任何从网表重建朝向的消费方
都是过时视图。**

**(2) route_grid 两缺陷根修（07364ae）**：宽度<b 布局宽实为路由失败后
返回 0 宽空壳而 verify 按布局取列——failed_result 携带真实宽度；终端
冲突在 build 期就发生：_build 用朝向盲的基础分解导出访问点，镜像块被
外推进邻块的列并在 cl0#Y 的扩散上预建了 VCC 电源条（ctrl/COMPLEX0 上
是"通过 verify 的潜伏短路"）。_die_orientation 从布局重建介面视图
（多成员块按 start_cols 降序判镜像；单成员翻转由 place_row 邻接间隙
不动点恢复；不可分辨处回退 pristine）。adder/COMPLEX0 修复后 FEASIBLE。

**(3) rung 2 停滞定性为 (a) 类——决定性证据**：冲突 plateau 不是调
参问题：CP-SAT solve_routing 在全部四个精确布局上证明 INFEASIBLE，
即不存在词汇合法的布线；移植代码对 graphrouter.cpp:92-434 审计忠实。
remedy 在布局链——槽位模型（下一节）正是为此。

**(4) 槽位几何模型（c0017a1，宽度对拍门达标）**：从 ASTRAN 自己的
GDS 逆向（gdstk，16.5 单位/µm 校准，prBoundary 与日志逐 cell 吻合）
并经 autocell2.cpp:1103 等源码锚定：W 画纵向（有源条 y 高 = W，1.2µm
行半预算），水平占位为槽位序列（一列 = 触点|栅|触点三元组，触点在列
边、栅在列心），相邻块面对网络相等共享触点槽，宽度 = 列数×0.19 +
0.385。旧 IR 把 W 画横向列是 ~3× 宽度差的根源。规则与实测在
doc/BIGCELL_SLOT_GEOMETRY.md。14 个有 GDS 基线的 cell 宽度比全部
落入 [0.80, 1.26]（半数 1.00-1.01），GDS 跨进程字节级一致，
layout_sanity 全清。

**待办**：verify 的 diffusion_access_points 仍从基础分解导出（镜像
cell 的访问点假阳性未清）；route_grid 需设计笔记 §8 四项槽位适配
（边列访问点/多槽暴露/介帧偏移/W+2 横向列）才能关闭槽位 cell——
两者在 die-view-router 轮处理。全量 542 绿 + 1 诚实 skip。

## §5.43 speculate 环 + 槽位路由器：首个 ASTRAN 同口径 Python cell（2026-10-16）

**(1) speculate 朝向选择（bbd4535）**：bd3fda4 证明库 NAND2X1 的纯代价
最优朝向结构性不可布（双电源访问挤在输入栅边 0，唯一合法交叉节点即输
出 Y 的 P/N 合并点）而镜像朝向 1 次尝试即布通。据此落地 doc §2.2 的
speculate 环：确定性 top-K 候选池（SA 最优/flip-both/flip-P/N/介面镜
像/euler 种子/代价排序的逐块翻转组合，1024 上限，内容键去重）→ 300 次
预算试布 → 首 FEASIBLE 胜出，否则最低 (冲突, 代价) 兜底。sa_refine 本
体零改动；NAND2X1 端到端闭合（FEASIBLE + verify 清 + 0.765µm
GDS/sanity 清），INVX1/NAND2 无回归，8T 全链 19.2s。

**(2) GDS 写侧两缺口（8f9c35d）**：T3 走廊栅接触方块（规则与路由器逐
项一致，几何诚实性有证明）+ 门-only 网络引脚标签。GDS 文件按 1nm 数据
库单位存坐标，测试断言须用 5.01e-4µm 容差 + 条带包含而非 1e-9 中心相
等——记入坑清单。

**(3) 共享介面视图 + 路由器槽位适配（bd3fda4）**：die_view.py 成为
smt_engine 一等公民（route_grid 与 verify 消费同一推导）；路由器按设
计笔记 §8 适配槽位模型（边轴网格 x=0.2375+c·0.19、W 高条带覆盖、门-only
网络无幻影引脚端子）。

**(4) 第三轮 17-cell 基准（77 分钟，bench_int3）**：链条全程工作——
rung3 槽位布局把 ctrl/COMPLEX0 从 12 列压到 6 列（同口径），路由失败
为诚实 plateau（最优 3 冲突：cl0#B/cl0#Y/cl1#Y 走廊/电源墙类，镜像组
合穷尽）。**能闭合的库 cell 不在基准集内**（基准只走 outputs/，INVX1/
NAND2X1 在 std_celllib）——基准集需补入库 cell。COMPLEX 系的残余冲突
类是下一轮目标：路由器轨道模型升级 / 分解变体 / 精确窗口修复
（doc §2.4 rung-1-as-window-fixer）。

**当前替换快照**：INVX1（0.575µm）、NAND2X1（0.765µm）、NAND2-inline、
INV-inline 四个 cell 纯 Python 闭环（verify+sanity 清，宽度比 ~1.0）；
宽度对拍 14/14 带内 [0.80, 1.26]；全量 586 绿 + 1 诚实 skip。


## §5.44 metal2 纵向自由度：节点级 via + M2 跨道段 —— COMPLEX plateau 崩塌（2026-10-15）

**缺陷与证据**：ce6ae7d 的结构诊断证明 plateau 冲突下界 == 实测最优
（ctrl/COMPLEX0 W=6: 3 冲突），且 CP-SAT 在同词汇上 INFEASIBLE——缺失
的自由是 ASTRAN 的 metal2 z 层（router.cpp:53-55：任意节点 via-up 4、
M2 纵向 11），而 RouteResult 词汇里 via 要求两侧同轨段、M2 无纵向边。

**词汇扩展（4 文件加法式）**：RouteResult 增 `m2v`（(col,t1,t2)->net，
M2 占据单列跨轨道区间）与 `m2via`（(track,col)->bool，节点级 via），
默认缺省——精确引擎 solve_routing 输出与全部旧构造点字节不变。
verify.py BFS 遍历新元素（span 经节点 via 接 M1 点、经 M2 段端点同层
合并），并检查 span/节点 via 的占用几何（异网 span 重叠、异网 M2 段
端点、M1 落点归属）。两个渲染器（smt_engine/gds.py、gds_cells.py）加
法式绘制（M2 列条带原语 + via1 方块），layout_sanity 清。

**路由器两阶段（关键决策）**：单阶段自由度会把已闭合 cell 的谈判引向
更差的局部最优（adder 复现 deck 236→594 代价回归被测得）。route_cell
改为两阶段：phase 1 = 原词汇逐字节（无 M2 纵向弧、both-side via 规则、
强制 dual fill），闭合即原样返回；仅 phase-1 停滞才以全新相位 2 网格
（M2 纵向弧 + 节点级 via + M2 桥式 dual fill 跳过 + 阻挡者标记）重布。
实测字节不变：INVX1、inline NAND2、库 NAND2X1（旧镜像朝向）、
CONTESTED、adder 复现 deck、exact NAND3（代价 56==56）。

**同网 dual 规则放宽**：M2 span 是第二条 N<->P 交叉路径，verify 的
"同网 dual 必须达 T3"由 BFS 连通性判定取代（精确引擎模型仍强制合并，
字节不变）；路由器 _solidify 在该列自身 M2 run 跨 T3 时跳过强制扫描。
没有这条，ctrl/COMPLEX0 的 cl0#a_2_6# 对齐栅@col0 的四个交叉轨道全部
被 cl0#Y 的强制 dual 条带封死——M2 无法抬升 M1 栅接触，单元不可布。

**结果**：ctrl/COMPLEX0（spans={(5,0,4):cl0#Y}+4 节点 via）、
max/COMPLEX5、adder/COMPLEX0、multiplier/COMPLEX4、NAND3X1（镜像候选）
路由 FEASIBLE + verify 清 + layout_sanity 清；闭合排布的结构诊断报告
零 contest。multiplier/COMPLEX5 为诚实事后 plateau：相邻对齐栅列
（cl1#Y@7 / cl1#A@8）唯一幸存交叉轨道同为 T3，共享节点 (T3,8)——
M2 抬不动 M1 栅接触，8 轨加宽可解（非本轮范围）。试布下界从 4 降到 1
（固定池）/变体池直接 FEASIBLE。全量 640 绿 + 1 skip。

## §5.45 第五轮基准：29/49 闭合，同口径中位比 0.83（2026-10-16）

M2 自由度（c4b3e9c）+ 取最窄政策（eb77d6e）+ 分解变体的首次联合对拍
（bench_int5，18276s ≈ 5.1h，49 cells）：

**闭合 29/49（59%）**，verify 29/29 清。同口径（bigcell-full，槽位模
型）11 cell 全部 ≤1.10：NOR2X1 **0.50**、COMPLEX5(6T) 0.67、NAND3X1
0.75、AND2X1/OR2X1 0.80、AOI22X1 0.83、COMPLEX0(8T) 0.86、
COMPLEX0(14T)/COMPLEX4(14T) 0.91、CLKBUF1 1.10——**中位 ~0.86，
Python 已窄于 ASTRAN**。multiplier/COMPLEX5(16T) 在 M2 轮被判
"beyond M2"，本轮经窄化政策的变体链闭合（诚实记录：关闭路径待
attempt 明细归档确认）。

**报告口径勘误**：bigcell-grid cell 用的是精确布局（横向腿 IR），与
smt-exact 同属旧语义——报告标注从"bigcell-* 可比"修正为"仅
bigcell-full 可比"。

**暴露的政策缺口（下一轮）**：rung 1 闭合仍立即返回未做候选比较
——NAND2X1/INVX1 以 smt-exact（1.50/1.67，旧 IR）闭合，而槽位链
给 0.765/0.575。取最窄政策应覆盖 rung 1。

**未闭合 20 cell 画像**：22-36T 大 COMPLEX（COMPLEX1/7/9/10/11/20、
multiplier/COMPLEX0）+ 时序/复杂库 cell（DFFNEG/DFFPOS/DFFSR/LATCH）
+ XOR/MUX 类（XOR2/XNOR2/MUX2X1）+ FAX1/HAX1/TBUFX2。两条已知升级
路径：runtime（两阶段对失败 cell 双倍代价——结构诊断可预言跳
phase 1；变体预算随规模收缩）与 8th track/门接触 M2 上浮
（multiplier/COMPLEX5 类）。

**运行时发现**：第五轮 5.1h（第四轮 2.9h）——M2 两阶段 + 变体链的
代价随 M2 闭合率上升而放大，优化方向明确且不阻塞正确性。

## §5.46 第六轮：runtime 调优 + 三类诊断 + die_view 树块修复（2026-10-16）

**(1) rung-1 纳入取最窄（a443dd5）**：第五轮的 NAND2X1/INVX1 比值
1.50/1.67 是政策产物——rung-1 闭合立即返回。现作候选处理，同布局的
rung-2 自动跳过。

**(2) runtime 调优（c275413）**：phase-1 stall 在结构诊断预言走廊竞
争/笼蔽时直接跳过（closure-safe：phase-1 cage 图是 phase-2 的子图，
诊断只夸大可达性——报告的需求即 phase-1 词汇的已证下界）；变体 SA 预
算随 P×N 规模线性收缩至 120 块上限的 euler 底线。重 cell 段
136.4s→74.4s（−45.4%），multiplier/COMPLEX0 的 40s phase-1 stall 消
除，布局与基线字节一致。零既有测试钉改动。

**(3) 20 cell 三类诊断（75599a5）**：时序类前提错误——分解对反馈环
完全正确（walk_next 只走未访问；环恰在栅共享网络/degree-4 枢纽处切
割，电学正确），真墙是同网络双访问列的条带全覆盖 + 窄器件单轨接触；
**8th track 被证明无价值**（7 cell × 4 宽度配置全 INFEASIBLE——双列
+电源条覆盖整个轨间带，省下一次四文件扩展）；真杠杆 = 精确模型的
M2 双柱交叉（verify 已接受、build_routing_model 无法表达）+ 布局侧
回避被笼蔽栅接触（census 给出廉价静态谓词）。

**(4) die_view 树块修复（6b35cee）**：22-36T 类的 rung-3 全部
"terminal clash" 是一个缺陷——pristine 重建对树块排布不一致（定点
静默保持 pristine），合法 trail 被读成幻影冲突。die_orientation 现在
自检（器件级邻接：0 间隙面网相等/断列不等，(row,is_p) 条带键）——通
过则历史重建字节不变（闭合 cell 指纹钉死），失败则 trail 重建（每器
件 S/D 未知量的约束路径分量 DP + 字典序贪心）。**判决：幻影冲突是一
个缺陷且已消灭，但该类不闭合——余下全是真实 7 轨词汇墙（栅接触落在
电源条跨度内、走廊 T3 竞争），下一杠杆在布局侧。** blocks 接线的引
擎侧 diff 已交付但必须等 verify 转发 block_objs（router==verifier 是
绑定不变量）。

**下一轮杠杆（按优先级）**：布局侧回避电源笼蔽栅列（place_sa 代价/
选择加 census 谓词）→ 精确模型 M2 双柱交叉（时序/XOR 类）→ 验证
侧 blocks 转发后接通引擎 diff。全量 667 绿。

## §5.47 双盆地与幻影闭合判决（2026-10-20）

**(1) §5.45 的重要勘误**：bench_int6 的 29→27 不是回归——四个"损失"
闭合（CLKBUF1/2/3、COMPLEX4）是**前 6b35cee die 视图的幻影**：把
round-5 树（c4b3e9c）抽出重跑，胜者全是 parallel_phase 类排布，而
parallel_phase 重排并联对使 pristine 重建在器件邻接上失败——round-5
树上 router 与 verifier 共享同一个镜像（错误）视图，自洽但非所画
die。旧闭合从未真实存在；**诚实轨迹 = 25（幻影折减）→ 27（第六轮），
+2 而非 −2**。教训：router==verifier 自洽不等于正确——两者必须同时
对齐真实 die。

**(2) 双盆地落地**：sa_refine_routable(cage=True) 双重 refine
（steered 领跑；cage=False 的 legacy 最优以 best-legacy{,-flip-both,
-die-both} 进固定池）；无 cage-free FEASIBLE 胜者时惰性第三阶段加
variant legacy 孪生（现有闭合的池/试布/选择零改动）；选择保持试布
裁决、盆地盲；顺带修掉 select_orderings 在 caged-FEASIBLE 胜者上的
`feasible[1]` KeyError 潜伏崩溃（旧钉从未触达）。

**(3) 证据**：COMPLEX4 双盆地链达 round-5 宽度（10 列 1.90µm）且
路由 floor=1 冲突、walled=0——距闭合一个杠杆；CLKBUF1/2/3 达
2.09/2.28/3.04µm（floor 13/10/14）；COMPLEX1 回退项全面占优
（floor 136→125、宽 22→17）；max/COMPLEX1、TBUFX2 增益保持；ctrl
M2 指纹不变。700 绿。

**(4) 已知路由/验证契约缺口（下一杠杆）**：COMPLEX4-align3 的
true-view 路由通过但 verify 失败（"diffusion access cl2#Y@1: no
stripe"）——verify 需把 block_objs 转发进 die_view（G2 交付的引擎
1 行 diff 随后解锁）。精确模型 M2 双柱交叉仍是 COMPLEX10/时序/XOR
类的杠杆。

## §5.48 真视图试布：COMPLEX4 闭合（2026-10-20）

**(1) 契约缺陷**：select_orderings 的试布路由是 blocks-less 的——树
块排布按 pristine 重建的虚构 die 打分，而真实路由看的是朝向感知视
图。multiplier/COMPLEX4 的候选池里有**两个真视图闭合者**
（parallel_phase-flip-both 0.7s / -align3 20.6s，均 verify 清），但其
blocks-less 试布 floor（3/6）排在 die-both（虚构 floor 2）之下，永远
选不中。

**(2) 修复**：试布契约尾随 blocks 关键字携带**候选自己的视图**
（_router_accepts_blocks 逐选择探测一次，注入式假路由器自动回退
blocks-less——测试契约保持）；选择报告携带真视图的 cage/conflict。

**(3) 验收**：COMPLEX4（14T）经全生产链闭合——布局 16s、路由 0.7s
FEASIBLE、verify 清、10 列 = 1.90µm（预测的 round-5 宽度；flip-both
胜出）。抽检 NAND2X1 w=2 / max/COMPLEX1 w=9 / ctrl-COMPLEX0 w=6 全
闭合+确定。

**(4) 过程记录**：agent K 实现后死于 API 静默失败（本会话第三次），
协调者验收其遗产并补完——其跨进程测试的辅助脚本把 CLKBUF1（库内虚
拟源，无独立 deck 文件）的子ckt**文本**传进了 path 槽
（FileNotFoundError）；修复为物化成真实临时文件。716 绿。

**(5) 剩余（按诊断证据排期）**：精确模型 M2 双柱交叉
（COMPLEX10 的网络连通性笼蔽 / 时序类双访问列 / XOR 类）；
verify 转发已就位后 COMPLEX10 可重试窗口修复；provenance 秒数清理；
rung-2 旧 IR 的 "switches layer" 契约缺口。

## §5.49 精确模型 M2 双柱交叉：词汇落地与判决（2026-10-20）

**(1) 词汇落地（additive，默认字节等同）**：`build_routing_model`/
`solve_routing`/`solve_window_routing` 新增 `m2_spans=False` 形参。开启时
模型获得：每 (net, column) 一条可选 metal2 区间（半开轨域
[start, end)，NoOverlap per column——`RouteResult.m2v` 的精确模型形态）、
节点过孔 `nv`（M1 点 = 条带覆盖或 M1 段端点；`RouteResult.m2via`）、双柱
规则松弛（"两 bar 都到 T3" → "T3 合并 OR M2 span 交叉连接两半"——xover
要求同一 span 上两半各有一个 bar 锚点过孔，BFS 可证连通）、跨半/门列
track 变换的 M2 join 形式、以及访问连接的诚实化（`dual` 位让位于
`merged = dual∧rt3n∧rt3p` 与 `xover`）。代价取启发侧 provenance
（router.cpp:53-55：span 11/轨步、节点过孔 4）。**默认路径字节等同**：
COMPLEX0 槽位全模型 proto 文本哈希 HEAD 前后同为
`201ea3e1…`（716 套件全绿佐证）。verify.py/gds.py **零改动**——c4b3e9c
的 BFS 遍历与渲染约定恰好覆盖精确模型可发出的全部几何（新测试钉住）。

**(2) 判决表（本轮决定性证据；槽位全模型，60s 单 worker，verify 门）**：

| cell | placement→route W | baseline | +M2-dual |
|---|---|---|---|
| adder/COMPLEX10 (36T) | 27→28 | INFEASIBLE 7.1s | INFEASIBLE 9.3s |
| max/COMPLEX20 (18T) | 13→14 | INFEASIBLE 1.6s | INFEASIBLE 2.1s |
| XOR2X1 (12T) | 8→9 | INFEASIBLE 0.3s | INFEASIBLE 0.5s |
| XNOR2X1 (12T) | 8→9 | INFEASIBLE 0.3s | INFEASIBLE 0.5s |
| MUX2X1 (10T) | 6→7 | INFEASIBLE 0.2s | INFEASIBLE 0.4s |
| TBUFX2 (10T) | 7→8 | INFEASIBLE 0.3s | INFEASIBLE 0.5s |
| LATCH (12T) | 8→9 | INFEASIBLE 0.3s | INFEASIBLE 0.5s |
| DFFNEGX1 (22T) | 17→18 | INFEASIBLE 1.0s | INFEASIBLE 1.6s |
| DFFPOSX1 (22T) | 16→17 | INFEASIBLE 1.0s | INFEASIBLE 1.5s |

**M2 双柱交叉一个杠杆不闭合九个诊断格中的任何一个**（全部秒级证明，
非超时）。正向对照证明词汇真实可用：INVX1 槽位链 col-1 双柱**禁止 T3
合并**时，baseline INFEASIBLE → m2_spans OPTIMAL，解码恰为手工钉住的
span (1,2,4)+节点过孔 (2,1)/(4,1)，verify 清、GDS/layout_sanity 清。

**(3) 唯一新闭合（数据，非行为变更）**：TBUFX2 在**精确引擎自身布局**
（W=18, 6 网）上 `m2_spans=True` 由 INFEASIBLE（0.9s）转 **OPTIMAL**
（16-20s，2 span + 4 节点过孔，verify 清，×2 确定，layout_sanity 清）——
但 W=18 越过 rung-1 边界（14），且 3.42µm vs ASTRAN 1.33µm（2.6×，带宽
外，精确 IR 把 W 画在横向）。故**不抬 EXACT_MAX_WIDTH_COLS**（LATCH
W=17、XOR/XNOR W=21、MUX W=17、DFF W=31/32、COMPLEX20 W=30 在其精确
布局上 m2_spans 仍全 INFEASIBLE——抬了也一无所获）。

**(4) 残余诊断图（族消减，全部 CP-SAT 证明）**：7 轨域上族消减——
(a) XNOR2X1/MUX2X1/XOR2X1/TBUFX2/LATCH 的**绑定族是 crossing-safety**
（M1 落点供给）：单独去族即 OPTIMAL（verify 恰好只报穿越违例）；其中
MUX/XNOR 的门接触规则单独去族也 OPTIMAL。违例穿越落在 power bar 的
**强制覆盖带内**（GND 条带必盖 T0-T2、VCC 必盖 T4-T6），且**加轨无效**：
把空闲轨插入 T2-T3 / T3-T4 强制带以外、加到 k=12（每侧多条）仍全
INFEASIBLE——下一步杠杆**不是轨数，而是布局轴**（把有争议的线的穿越
点移出条带柱；与启发侧 structural note 的"剩余自由度是布局本身"一致，
place_sa true-view/variant 轴）。(b) DFF×2、adder/COMPLEX10、
max/COMPLEX20 比 crossing-safety 还深一层（去 CS、去 presence 各自及
组合仍 INFEASIBLE；无空门轨、无越界访问等平凡伪影已排除）——下一层
消减对象是 gap-bridge/transition/join 形式、E5 层规则与 via/M2-run 规则，
命名工具：CP-SAT `sufficient_assumptions_for_infeasibility` 核心提取。

**(5) 生产化清单**：窗口修复器（rung 2.5/3.5）接 `m2_spans=True` 是纯
增益（现有窗口的闭合解不携带死 span、INFEASIBLE 判决不变、未来双柱
笼蔽窗口可解）；WINDOW_MAX_COLS=12 **不抬**（双柱重区在全宽下都不
闭合，加宽窗口不可能翻格）。engine.py 只读——diff 交付于
`flow/_stage3_check/_m2_engine_diff.patch`。测试：tests/unit/
test_exact_m2_dual.py（8 项：默认无 span、双柱 M2 闭合/无则失败、
渲染+sanity 端到端、窗口 span 创建/保留 span 合并+禁入、LATCH 判决钉、
进程内×2 + 跨进程 PYTHONHASHSEED 0/1）+ test_smt_engine.py 1 项
（solve_routing 公共 API 形态）。725 绿（716+9，零钉翻转）。

## §5.50 交叉级普查：XOR/MUX/LATCH 类的墙在分解空间中纠缠（2026-10-20）

**(1) 词汇与谓词齐备（fd4fee3 + 645d952）**：精确模型 M2 双柱交叉词汇
落地（九 cell 探针全 INFEASIBLE，阳性对照 INVX1 逐点吻合）；census
从"接触可逃逸"扩展到"交叉可逃逸"（锚定多晶硅逃逸是承重修正——未锚
定形式在已证不可布布局上返回 0），与 drop-CS 真值 5/5 吻合。

**(2) 判决：穷举级否定**——XOR2X1 的 589,824 个排布（4 变体全排列×
翻转）普查：交叉干净的存在 5,672 个但全部带笼蔽 ≥2，**(crossing=0,
cage=0) 排布不存在**；MUX/TBUF 同构；LATCH 需两 census 同时归零——
不可达。该类在当前分解空间中两堵墙纠缠：避交叉必笼蔽，避笼蔽必竞争
交叉。所有 floor 桶胜者 ≤0.7s 证明 INFEASIBLE。

**(3) 选择政策**：census 作为证据 + 平局裁决（FEASIBLE-caged 档
(cage, crossing, index)、对齐决赛者同名次位）；回退排名与 SA 代价
字节冻结（尝试把 crossing 放进回退排名打破三个 (floor,cost,index)
钉——回退）。全部既有闭合与五个类 cell 的选择字节不变。

**(4) 剩余类的工具已点名**：CP-SAT
sufficient_assumptions_for_infeasibility 核提取（需在
build_routing_model 加 assumption 字面量——尚未存在）；第三个墙族
观察在案：网络连通性笼蔽（census 清、路由器 walled——TBUFX2 (3,0)
即此类）。

**战略快照**：机械杠杆阶梯（词汇/谓词/试布/变体/对齐）已系统性穷举，
每轮以 CP-SAT 证明收尾。剩余 ~19 cell 需要：假设核提取定因（新工具）
→ 针对性词汇/布局改动，或接受其暂驻 ASTRAN 回退档。诚实闭合 ~30/49。

## §5.51 假设核提取：剩余 cell 全部是排布墙（2026-10-21）

**(1) 工具**：build_routing_model 的 23 个约束族全部包成 CP-SAT
assumption 字面量（assumptions=False 默认字节不变，COMPLEX0 proto
hash 201ea3e1 不变）；INFEASIBLE 时 sufficient-assumptions 命名绑定族。

**(2) 核表（全部不可约-certified；88 个 drop 见证全部 verify-dirty
——零可干净松弛，option-3 先例不复现）**：普遍基底 = pwr（电源覆盖
带，布局强制）+ csP（交叉安全）+ gate——TERMINAL/DRC 族，任何词汇都
无法可靠松弛；两种连通性形状 H（bridge/tjoin）/ V（pres/pjanchor）。
`dual` 仅出现在 TBUFX2-exact 的核里——恰是 m2_spans 唯一关闭的
cell，完美自洽。九个槽位 cell 判决：**排布墙**（最廉价修复族 = 布
局谓词，或 ASTRAN 回退档）；深类非独立机制——同一堵墙、连通性成员
可见。

**(3) 战略结论**：机械杠杆阶梯（词汇/谓词/试布/变体/对齐）+ 诊断工
具（探针/窗口证明/假设核）已系统性穷举。剩余 ~19 cell 在当前分解/
变体空间中已被证明无 (crossing=0, cage=0) 排布（XOR2X1 589,824 穷
举）或核表绑定。它们留在 ASTRAN 回退档，除非：研究级的新排布空间
（超出当前 folding/变体维度），或接受现状。诚实闭合 ~30/49，全部
verify+sanity 清、同口径宽度中位 0.86、跨进程字节确定。**替换的架
构、质量与诊断基础设施完整；覆盖率的最后一步是研究问题而非工程问
题。**

## §5.52 第七轮基准：正式快照与剩余 cell 的证据化终态（2026-10-21）

**bench_int7（49 cells）**：28 ok / 21 unsupported / 0 errors；verify
28/28 清；同口径中位比 **0.82**（n=14）。int6→int7 净增
multiplier/COMPLEX4（1.90µm，真视图试布 + blocks 转发的直接成果），
零损失。诚实轨迹：12%（起点）→ 25（int5 幻影折减）→ 27（int6）→
**28（int7）**——第六轮的"回归"实为幻影清除（§5.47）。

**剩余 21 cell 的证据化终态**（astran 回退档，全部有证明背书）：

1. **假设核表（§5.51）**：每 cell 的最小不可满足核不可约-certified，
   88 个 drop 见证全部 verify-dirty——普遍基底 pwr+csP+gate 无可靠松
   弛；判决 = 排布墙。
2. **两级墙（§5.50 + 链分割研究）**：局部电源带（分割可解——三个
   cell 的 census 达 (0,0)）+ 全局连通性笼蔽（分割不可解——census-
   clean 排布全部被路由器可达性分析重新封墙；LATCH 5.9M 分割排布无
   净零）。
3. **穷举否定在案**：8th track（7 cell × 4 配置）、XOR2X1 589,824
   排布、contiguous+split 两代空间。
4. **已落地的合法增益**：链分割维度的 LATCH floor 33→28（66a041b，
   additive，等未来基准捕获）。

**未来会话的开放维度**（按预期收益排序）：pair-splits（双链同时分
割，XOR2X1 界内 6 组合×1.5-18M 对——agent N 界定外）、folding 决策
进排布变量（当前 up-front）、行内轨扩展（13-track，四文件协同）。
均属研究级；当前架构的替换率已到其证据边界。

**工程终态**：五档引擎阶梯 + 诊断工具链（假设核/双 census/窗口证明
/探针/基准 harness）为永久资产；745 绿 + 1 诚实 skip；AUDIT
§5.41-5.52 完整记录。

## §5.53 研究级排布空间：核引导与 pair-splits 落地（2026-10-21）

agent R 实现两个研究包后死于静默模型失败（本会话第四次），协调者
验收补完（其跨进程测试的辅助脚本 import 错位——row_seeds/
build_bigcell_blocks 写进了 place_sa 的导入，实属 netlist_ext）。

**(1) 核引导 fitness（深类，探针证据落地）**：假设核的具名连通性关
键网络（core_critical_nets，溯源到 agent M 的提取表）加权 census 与
选择。实测：COMPLEX20 布局 13→12 列、floor 32→4 冲突；DFFNEGX1
17→16；COMPLEX10 27→28（build-fail 选择）。**宽度改善但全部模型仍
INFEASIBLE——墙在核引导空间之外持续存在**。

**(2) pair-splits（机制落地，census 扫描未跑）**：
pair_split_decompositions + pair_split_classes 把链分割维度扩展到双
链同时分割；XOR/MUX/LATCH 的 pair-split 空间 census 重跑是 agent R
未及到达的实验（其死亡点）。

**(3) 状态**：770 绿（+13 研究测试）；跨进程确定性在修复 import 后
通过（XOR2X1 全链双哈希种子一致）。剩余 cell 的替换率未变；两个研
究维度的机制已入库，其 census/OPTIMAL 证据表是下一会话的第一项。

## §5.54 pair-split 空间判决：110 个 census-(0,0) 见证全部倒在全局笼蔽（2026-10-21）

agent R 的扫描器（其遗产）对 XOR2X1/XNOR2X1/MUX2X1/LATCH 的全部
24 个 pair 分解跑完 census：**四个 cell 都存在 (crossing=0, cage=0)
见证**（XOR 94 / XNOR 85 / MUX 96 / LATCH 33 个；XOR 单分解扫描
2,983,798 对）——局部电源带墙被 pair-split 维度溶解，与单分割同构。

**漏斗判决（110 个见证逐一实测，4 cell × 24 分解 × 前 6 见证）**：
零闭合——每个 census-clean 排布都倒在路由器的全局连通性笼蔽，与
agent N 的单分割见证模式完全一致。两代排布空间（contiguous 589,824
穷举 + pair-split 3M 扫描）的漏斗收敛于同一结构：**两级墙 = 局部电
源带（可分割溶解）+ 全局连通性笼蔽（金属跳线重挤走廊，不可由分割
溶解）**。

**正式接受案升级为三重证据**（§5.52 的证据链闭合）：
1. 假设核表（不可约、全部见证 verify-dirty）；
2. census 穷举（contiguous 全空 + 两代 split 空间的 (0,0) 见证全部
   漏斗淘汰）；
3. 词汇扩展探针（M2 双柱、8th track——前者必要不充分，后者无价值）。

**研究维度的完整清单已全部穷举**：contiguous、single-split、
pair-split、core-guided fitness、cage-avoidance、crossing-avoidance、
两个 M2 词汇、窗口修复。剩余 21 cell 的 ASTRAN 回退档是**带完整证明
的终态**；未来重开需：folding 进排布变量、行内轨扩展、或新排布空间
族——均研究级且无先验理由预期不同结果。

## §5.55 fold 维度判决：census 极小值改善但零 (0,0)——第四个穷举的排布维度（2026-10-22）

「folding 进排布变量」落地：fold_devices 增 fold_overrides（{device:
legs}，纯函数、默认字节不变——对 7 个 cell 与 HEAD 直接对拍），specu
late 池增惰性 phase-6 fold 变体（核引导提名：栅网络在核内的器件提名
默认腿数 ±1 + max-fold；每变体重跑 fold→blocks→euler→有界 SA，按自
己的 netlist/腿表试布，(fold, ordering) 双签名去重）。

**探针表（穷举级）**：fold 维度**严格改善 census 极小值**——
XOR2X1/MUX2X1 (0,2)→(0,1)、LATCH (0,3)→(0,2)（全排序空间穷举
147,456 排布/决策；baseline 重跑精确复现 §5.50 记录）——核门控器件
拆 2 腿确实挪动了栅列、解笼一个接触。**但每个变体的每个排布仍剩一
个笼蔽栅：五个 cell 全部零 (0,0)**——CP-SAT/全链阶段无见证可跑（两
路径均烟雾验证可执行）。fold 死在比 split 更早的一层（census 层），
否定证据并入 §5.52 接受案：**第四个穷举的排布维度**（contiguous、
single-split、pair-split、fold）。

引擎接线 diff 已交付未应用（core_guided 只转向 8 个未闭合的核列出
cell，闭合保持字节不变）。18 新测试；788 绿。

## §5.56 行内轨扩展判决：54 次全模型证明全部 INFEASIBLE——第五个穷举的杠杆（2026-10-22）

「13-track 行内轨扩展」在探针层死亡：6 cell × 9 种加宽域配置（9/10/
11/12/13 轨 × 中点填充/条带三分填充 × ± m2_spans，共享 die 视图访
问推导），**54 次全模型 CP-SAT 运行全部 INFEASIBLE**，均在 ≤5.4s 内
证明（非超时）。阳性对照干净（INV 槽位链在每个域上 OPTIMAL+verify
清——判决非补丁破损伪影）。

**机制假设为真但不足以解锁**：W=0.25 窄条带从 1 轨变 2-3 轨（栅落
点 3→5）——假设的几何收益真实落地。但精确覆盖分析显示：**电源条吸
收了带内新轨**（m01/m12/m45/m56 物理上本就在 9-bar 矩形内）；**逃出
电源的条带内轨对（m23/m34）本就被双柱合并毯覆盖**——9-bar 的合并矩
形早已跨越同一 y 区间，模型只是获得了对既有物理阻挡的可见性。drop-CS
实验：XOR base9 → OPTIMAL（复现对照），13tr → FEASIBLE-at-cap（CS
仍绑定且面更大）；LATCH 两域均 INFEASIBLE（其两-census 纠缠深于交
叉安全）。13tr 假设核：pwr 在全部六 cell 持久。

**探针缺陷修正**：旧 _m2_track_bisect2.py 的 k=10-12 运行未打
route_model._access_points 补丁（走的是 base walk 而非引擎/verify 的
槽位模型）——在共享视图上重跑确认其判决有效。

**判决：行内轨维度死在探针层，无需四文件生产化**。接受案升级为
**五个穷举的轨/排布杠杆**（9→13 轨行内、走廊加宽、M2 双柱、8th
track、四个排布空间世代），且行内轨的证据强于其余：**即使授予模型
超出物理可实现（0.25µm 条带内 2-3 轨低于 ~0.19µm M1 间距）的自由
度，cell 仍 INFEASIBLE**。剩余 21 cell 的 ASTRAN 回退档终态的证据
链至此完备。

## §5.57 folding 组合变体判决：census 墙溶解、精确模型拒绝全部自由排布——战役正式关闭（2026-10-22）

组合实验（agent U2）：核心门控器件的选项集笛卡尔积
（fold_combo_candidates，FOLD_COMBO_MAX_COMBOS=64——本语料最宽核 6
器件 → 63 组合，无截断）接入 select_orderings 为惰性 phase-7。腿拷贝
器件（name#legK）排除在门控集外（对拷贝 override 会再折一条腿链）。

**组合假设在 census 层证实**：XOR2X1 39/63 组合达到 census-
(crossing=0, cage=0)、MUX2X1 9/15——per-device 空间为零处，组合互相
搬家成真。**精确模型全部否决**：48 个 census-(0,0) 见证 INFEASIBLE
（0.4-60s，无超时）。见证核（族级不可约）指名绑定机制：
bridge/tjoin/e5same/gjoin——**金属跳线容量绑定，非栅摆放**。§5.54
的两级墙精确复现：局部电源带墙在组合下溶解，全局连通性墙接住每一个
被释放的排布。

**LATCH 的结构性理由**：残余笼蔽栅是网络 Q 的——在核（D, a_2_6#）
之外，核门控 fold 无法搬动（Q 门控提名规则记录为界外）。

**生产级收益**：平台期 cell 的回退 floor 实质改善（XOR2X1 16→12、
LATCH 35→6、DFFNEGX1 UNROUTABLE→150）；core-OFF 生产引擎构造上不
受影响。12 新测试；800 绿。

**战役正式关闭**：六个排布空间世代（contiguous、single-split、
pair-split、fold-per-device、fold-combination、+行内轨模型）× 三个
词汇杠杆（M2 双柱、8th track、假设核松弛）全部以 CP-SAT 级证明穷
举。**28/49 诚实闭合（同口径中位 0.82）+ 完整回退档 = 最终交付状
态**。剩余 21 cell 重开研究的入口：金属跳线容量（bridge/tjoin 词汇
的下一步）与 Q 门控类提名规则——均记录在案，无先验理由预期不同结果。

## §5.58 跳线容量化：fd4fee3 的死析取激活，MUX2X1 以 1.286× 闭合（2026-10-22）

**审计发现（缺陷）**：fd4fee3 的跳线 span 析取（j2/j2g）是死的——无
条件更紧不等式与松弛式同时发出，j2 ≥ 0 使松弛式被蕴含而永不生效；
双柱规则正确门控于 if (not m2_spans)，跳线形式漏了。fd4fee3 的阳性
对照（TBUFX2）只经双柱规则闭合，惰性因此未被发现。

**修复**：jump_m2=False 新参数（钳制要求 m2_spans；三个 proto hash
钉死）——死析取激活 + 三种缺失形式补齐（M2 段侧换轨、span 锚定
M2 跑道端点 E1 逐网精确 OR、bar 锚定 M2 跳点 E3）。bridge 不加析取
（逐间隙列 presence 是 BFS 必要，垂直 span 跨不过列间隙）；e5same
审计后无 M2 类比（verify 本身将 poly↔metal 同网络邻接切换记为违规，
模型编码的正是 verify 的规则）。verify/gds 零改动。

**闭合**：MUX2X1 最宽 fold-combo override（M1=2+M4=2+M6=2+M9=2）
INFEASIBLE 0.8s → OPTIMAL 2.3s——8 M2 span / 4 M2 段 / 13 节点 via，
内部网络 a_2_10# 携带三条 span（与假设机制精确吻合）；全链
verify+GDS+sanity 清，**1.71µm vs ASTRAN 1.33 = 1.286，入 0.8-1.3
验收带**。其余 47 见证核重塑后仍拒绝（MUX2X1 的墙从 M1 跳线容量移
到交叉安全+访问摆放；XOR2X1 不变）。S2 的 core_guided 引擎 diff 逐
字应用：8 个核列出 cell 经生产链复现 phase-7 floors，28 个闭合构造
上不受影响（CORE_CRITICAL_NETS 对它们为空——标志惰性）。6 新测试；
806 绿。

**剩余**：jump_m2 未接入窗口修复器/生产引擎——MUX2X1 的生产闭合
（试布 floor 2）差一步窗口修复器接线；47 个否定核重塑后并入接受案。

## §5.59 窗口修复器接入 jump 容量 + 生产闭合的最后一环定位（2026-10-22）

**(1) 接线落地**：solve_window_routing 增 jump_m2（透传
build_routing_model，钳制要求 m2_spans）；引擎窗口档传
m2_spans=True + jump_m2=True。两个伴生修复：①窗口推导覆盖整路由宽
度（≤WINDOW_MAX_COLS 时）——路由词汇含尾随逃逸列（槽位几何：路由网
格 = 布局 W+1），停在布局宽度的窗口会剥夺精确模型的逃逸列；②
_plateau_partial 复现 route_cell 的精确两相序列（相-1 跳过门 + 相-2
metal2 网格）——单相复跑再现的是不同的失败态，诚实守卫据此拒绝了
每一个相-2 plateau 的窗口修复。

**(2) MUX2X1 的生产闭合定位**：接线的窗口求解在**被选中的
pairsplit 排布**上仍 INFEASIBLE（精确证明）——jump 容量关闭的是
**fold-combo 见证排布**（agent V：OPTIMAL 2.3s、1.71µm=1.286×）。
生产链的最后一环 = phase-7 fold-combo 候选的试布改用精确模型
（jump_m2）——启发式试布无法度量 jump 容量，把 fold-combo 排布排在
pairsplit 之下。运行时成本有界（15-63 组合 × 2-20s/个）。

**(3) 状态**：807 绿（blocks 线程假网格增 structural_diagnosis 相与
双相 blocks 钉）；全部闭合钉保持。MUX2X1 的精确模型闭合证据完整
（agent V），生产接入是下一个精确步骤。

## §5.60 GDS 种子攻击：ASTRAN 自有版图全部可提取、全部被精确模型判死——捕捉清单为空（2026-10-27）

agent gds-seeds 的攻击假设：21 个 ASTRAN 回退 cell 的版图以 .gds 形式
在库内（库基线 original_astran_cells/*.gds + 挖掘 outputs/*/*.gds），
ASTRAN 收敛即证明可行排布存在——把排布提取出来喂给既有机器
（census → route_cell → verify_cell → 精确模型），Python 即可路由/验
证/拥有这些 cell，无需再跑 ASTRAN。

**(1) 提取器（bigcell_engine/gds_seeds.py）**：纯 gdstk 几何提取——
active 连通分量=扩散条；窄 poly 矩形跨越条=栅列（poly 组件经触点接
metal1、标号定网络，大小写不敏感：ASTRAN 把 pin 标号全大写，网表保
持混合大小写）；栅间的条段=端子区（其触点定网络）；网络=metal1∪poly∪
区域经触点桥接的连通分量。器件指派是确定性 DFS：按行从左到右，每栅
以（栅网、端子网络对）匹配网表器件，特征签名相同的纯内部结点（如
XOR 的两个内部结）由选择传播钉死。**21 个中 15 个全部提取干净**（每
行器件序、朝向、断条位置）；**6 个无 ASTRAN 版图可提取**——ASTRAN 自
己的运行就没完成（无 Cell Size 行、无 .gds：CLKBUF2/CLKBUF3/DFFSR/
FAX1/HAX1/LATCH）。交叉验证：NOR3X1 P 行提取出实测栅序 B-A-A-B-C-C、
7 端子槽、0 断条（§5/设计文档的双梯 run——其示例轨迹是同一欧拉回路
的另一种写法；结构断言逐条吻合），断条数与 ASTRAN 日志 Nr. Gaps 全
部一致。

**(2) 投影到槽位模型**：每晶体管一个 single 块携带 die 朝向，
place_row 逐一复现 ASTRAN 每行的次序、朝向与断条（实测：每条 GDS 断
条边界两侧网络必不同——BREAK_GAP_COLS 恰在且仅在断条处插入，模型宽
= 器件数 + 断条数）。

**(3) 判决：捕捉清单为空，且是穷举级证据**。15 个投影排布全部被
CP-SAT 在**全词汇**（metal2 + m2_spans + jump_m2，即 §5.58 修复后的
完整模型）判 INFEASIBLE：6 个小 cell 整胞窗口证明（0.5-3.7s），8 个
大 cell 整胞 solve_routing 证明（2-12s，零超时），NOR3X1 整胞 1s。
die-mirror 变体同判。启发式路由器（两相 + 结构诊断）的失败模式与之
自洽：caged gate contacts、走廊 T3 超订、电源带内交叉墙——census
(cage, crossing) 最好 (0,2)/最差 (11,9)。

**(4) 墙的定位（精确到几何）**：不是搜索空间，是表达力。ASTRAN 的可
布排布用了槽位模型没有的两个自由度，逐 cell 实测——
- **多列端子区**：ASTRAN 的 LP 压缩为了给布线留走廊，把连续扩散里的
  栅推开（实测栅距最高 4.3 pitch，模型里一律 1 pitch 一器件）；栅距
  审计：COMPLEX1/COMPLEX9/COMPLEX11 逐行 ≤1.24 pitch（忠实投影），
  CLKBUF1/XOR2X1/COMPLEX20 有 1.5-2.0 pitch 区，multiplier/COMPLEX0
  达 4.3；
- **行独立 x 偏移**：ASTRAN 两行起点不齐（NOR3X1 的 N 链居中在 P 行
  中段之下，偏 2.16 列；COMPLEX11 后两条偏 3.7/4.3 列），place_row
  把每行钉在 0 列。
即便忠实投影的 cell（COMPLEX1/9/11）也被判死——佐证墙在词汇而非排布
（§5.54-5.57 两级墙的第三种形态：几何自由度）。

**(5) 落库资产**：gds_seeds.py = 提取器 + EXTRACTED_TABLE（15 个排布
的纯数据迁移记录，provenance 测试从 .gds 逐字节重导）+ SEED_TABLE
（运行时闭合表，**空**——按所有权规则，只有真正闭合的排布才入表）
+ seed_candidates（place_sa.select_orderings 的最高优先级候选类：
一次摘要查找、表外 cell 池字节不变、表内 cell 的闭合仅凭表复现，无
需 .gds）。41 新测试（40 快 + 1 慢的 15 证明扫描）；NOR3X1 的 1s 证
明入快套作为墙钉——未来词汇扩展解锁捕捉时测试翻红即提醒移表钉闭合。
§5.52 接受案升级：**六个穷举的排布/轨杠杆 + 一个几何自由度判决**。
重开入口更精确了：多列端子区与行偏移进几何模型（place_row/几何层的
表达力），或接受 21 cell 的 ASTRAN 回退终态。

## §5.61 第二十轮四路：器件粒度判决、性能字节恒等优化、指标面板、泛化性揭示（2026-10-27）

**(1) W2 器件粒度（place_device.py）**：以单个晶体管为移动单位的
SA（复用 place_sa 的增量机制与权重，ASTRAN move set 全移植，内容哈
希种子/迭代预算）。**局部电源带墙在器件粒度下溶解**——XOR/XNOR/
MUX/LATCH 全部出现块空间不存在的 census-(0,0) 见证（5/8 超出
pair-split 的表达力，最多 4 处链同时切割）；**但全局连通性笼蔽在晶
体管粒度下依然成立**：8 见证经全词汇（M2+span+跳线）精确模型
8/8 INFEASIBLE（1.2-4.5s 证明）。§5.54 两级墙确认比粒度更深。诚实
校准：census 是比较度量非闭合神谕（census (0,0) 的排布 7/8 被路由器
静态诊断找到笼蔽栅）。19 新测试；引擎 rung4/4.5 接线 diff 已交付。

**(2) W3 性能轮**：profile 驱动（五 cell 热点表），route_grid 协商
内环优化（预计算 id 表、邻接元组、增量==全量断言纪律下的树收集后处
理、反向树成员索引）——**单次尝试成本降 1.8-2.34x，字节恒等**：
配对电池全部路由签名前后一致，cProfile 调用数与堆操作数（26,717,172）
完全不变——同一搜索、每次更便宜。verify/精确模型实测非热点零改动。
NAND6 签名+时间预算钉入回归套。

**(3) W4 指标面板**：benchmark 每-cell 质量面板（引脚可达性实测分、
sanity 指标、层计数、place/route/window 运行时拆分）+ 汇总质量块
（同口径比中位/最大、引脚分中位、运行时 p50/p90、引擎分布）。49-cell
复拍验证：同口径 n=12 中位 0.80/最大 0.909，引脚分中位 0.479。

**(4) W4 泛化性 hold-out（21 个全新 Verilog 模块经 yosys 合成，字
节可复现）——判决：混合，中档过拟合**：
- 小档（≤8T）：hold-out 4/4 = 100% = 开发集——完美泛化
- 中档（9-16T）：hold-out **0/9 vs 开发集 43%**——8 个 CP-SAT 证明
  INFEASIBLE、1 个 verify-dirty；**开发集的 6 个中档闭合
  （COMPLEX0/1/4/5/11、TBUFX2）是语料特异性，非通用能力**
- 大档（>16T）：双方 0%（§5.54 结构墙）

**诚实总评：引擎的真实通用能力 = 小 cell 100% + 中大档 0%（hold-out
口径 4/21=19%）**。中档的收编钥匙与 W1 的判决汇合：几何变量化（多
列区域+行偏移）+ 泛化驱动的词汇扩展。882 绿。
