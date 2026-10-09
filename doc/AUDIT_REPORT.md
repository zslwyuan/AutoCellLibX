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
| 上游 ASTRAN 原始单元(`originalAstranStdCells/`) | 日志 `Cell Size ... x 3.2` | 2.936 | 作为面积对比基准 |
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
| `GDSIIAnalysis.loadOrignalGSCL45nmGDS` | `curCell.area(((6,0),))[(6,0)]` —— 取 GDS **第 6 层**图形面积 | 第 6 层是某个内部层(GSCL 层表中 6=?),其图形面积**不代表单元占用的版图面积**;用单层面积当"单元面积"在物理上无意义 |
| `GDSIIAnalysis.loadAstranGDS` / `Astran.loadAstranArea` | `W(日志) × 0.8 × 3.2` | `0.8` 为缩放系数、`3.2` 是**上游单元高度**;对本机生成单元(高 2.6)系数不匹配 |

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
4. 重新生成 `originalAstranStdCells/` 基准(用本机配置),消除基准与产物的配置差异。

---

## 三、Pattern 提取/生长/组合算法修复(已实施)

发现并修复以下确凿错误(均在 `pySrc/`):

### 3.1 `BLIFPreProc.extract_and_encode_subgraph_tree` —— 编码与节点错位

- **错误**:`encodes.append(...)` 位于 `if (not predCell.id in tree)` **之外**,而 `tree.append(...)` 在之内。当同一前驱经多条 net 驱动同一下游(多输出单元如 FAX1,或菱形结构)时,`encodes` 会比 `tree` 多出重复项,导致**编码串与子图结构不对应**;结构等价的模式被编码成不同串 → **模式被错误拆分/归并**。
- **修复**:将 `encodes.append` 移入去重分支,保证编码与树节点严格一一对应。
- **验证**:adder 初始聚类 128 簇,`编码长度 == 簇内单元数` 的不匹配数为 **0**。

### 3.2 `BLIFPatternGrowth.grow_sequence_of_clusters` / `_BasedOn` —— 生长方向不对称

- **错误**:输入前驱方向有"跳过同类型模式邻居"的检查
  ```python
  if curNeighbor.clusterId != -1 and curNeighbor.cluster.clusterTypeId == cluster.clusterTypeId: continue
  ```
  而**输出后继方向缺少同一检查**。后果:输出方向会把"属于同一模式的其它簇"的单元吸收进来,破坏"同一模式多个独立实例"的结构(错误合并/disable 其它簇)。
- **修复**:在两个函数的输出后继循环中补上同类型模式跳过检查,使两个方向语义对称。
- **说明**:该修复改变模式生长路径,故结果会变化;见 §3.4 关于结果波动的说明。

### 3.3 `BLIFPreProc.heuristic_label_initial_clusters_based_on` —— labelId 递增不一致

- **错误**:与同名函数(非 `_BasedOn`)不同,`labelId += 1` 被放在循环体末尾**无条件执行**(即使该模式的簇数为 0、序列被丢弃),导致`clusterTypeId` 出现空洞。
- **后果**:`main.py` 第二轮以 `patternNum = len(clusterSeqs)` 作为新模式的 `clusterTypeId` 起点,而初始 `clusterTypeId` 已跳号 → **新旧模式编号可能冲突**,使生长中的"同类型模式"判断(依赖 `clusterTypeId` 比较)出错。
- **修复**:改为仅有簇时递增,与另一函数一致。

### 3.4 附加修复(测试体系发现)

| 文件 | 修复 |
|---|---|
| `BLIFPreProc.convertBLIFGraphIntoDataset` | `node_features` 列数由固定 `maxNumType=36` 改为 `max(maxNumType, len(feat_dict))`,消除单元类型数 >36 时的 `IndexError`(此前越界检查被注释) |
| `main.py`(两处) | 访问 `clusterSeqs[0]` 前增加 `len(clusterSeqs) == 0` 保护,避免空序列列表导致的 `IndexError` |
| `spice.SPSubcircuit.__init__` | `interfaces` 从**未剥离换行**的 `texts[0]` 提取(而 `self.texts` 已剥离),导致最后一个引脚名带 `"\n"`(实测 `AND2X1` 的接口为 `['Y','B','VCC','GND','A\n']`);改为从 `self.texts[0]` 提取,`internalSignals` 同步改用 `self.texts` |

### 3.5 测试体系与验证

**项目合并**:ASTRAN 源码与 LP 求解器包装已 vendored 进本仓库(`tools/astran/`、`tools/gurobi_cl/`),`pySrc/Astran.py` 集中定义项目内路径,项目自包含。

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

**工程化交付**:ASTRAN 与 AutoCellLibX 已合并为单一项目管理(`tools/astran`、`tools/gurobi_cl` vendored,路径集中于 `pySrc/Astran.py`,`BUILDING.md` 说明构建/运行/测试);建立分层测试体系(unit 31 + integration 3,含针对上述每个 bug 的回归用例)。

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
| 项目自包含 | ASTRAN 与求解器包装 vendored 至 `tools/`,路径集中于 `pySrc/Astran.py` |

### 5.4 验证

- ASTRAN 重新编译 0 错误;INVX1/COMPLEX0 端到端生成正常(COMPLEX0 修复后 `Cell Size 2 x 2.6`,较修复前 2.2 更窄,说明压缩约束真正生效);
- 测试套件:31 unit + 3 integration 全通过;
- 生成的 LP 已验证:定义约束正确、`width`/`height` 列完整、求解返回最优/可行解。

### 5.5 仍未完成(需工艺标定,非代码缺陷)

1. **与 GSCL45 行高精确对齐**:目标库行高 2.47um,本机 ASTRAN 产物 2.6um(默认 `rowheight 13 × vgrid 0.20`)。可用 `set rowheight`/`set vgrid` 标定(如 13×0.19),但会改变单元几何,需 DRC 复核,故未在本轮强制实施;
2. **层映射统一**:ASTRAN 输出层号与 GSCL45 库不同,集成前需用 `set technology gdsii` 重映射或后处理;
3. **基线重生成**:`originalAstranStdCells/` 仍为上游版本(H=3.2);若需与本机配置完全一致,可用 `tools/gurobi_cl` + 修复版 ASTRAN 重新生成(单次 compaction 约数十秒至 5 分钟,32 个单元约 1 小时)。

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

**工具新增**:`pySrc/regenerate_cells.py`(按名重生成指定单元的版图,无需重跑挖掘流水线)。

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

先前 `outputs/adder` 的增益是在"**基准 H=3.2 × 产物 H=2.6**"下算出的:GSCL45 LEF 的单元高度是 **2.47**(见 `stdCelllib/gscl45nm.lef` 的 `SIZE … BY 2.47`),而 `originalAstranStdCells/` 里的 ASTRAN 基准是上游**另一套** ASTRAN(日志自证 Linux + `/opt/gurobi950` + `cellsHeight=16`)以 **H=3.2** 生成的,本仓库无法复现。行高不同则"面积 ∝ 宽度"不成立,比较无意义——实测 `COMPLEX9` 因此从 +6.5% 翻成 −19.5%。

修复:用 vendored 工具链、**同一套几何常量**重生成 `originalAstranStdCells/`(H=2.6),使基准与产物同高,整条结果可用本仓库复现。与 GSCL45 仍有 2.6 vs 2.47 的残余差异(约 5%);如需完全对齐,把 `Astran.ASTRAN_VGRID` 调为 0.19(13×0.19=2.47)后重做 DRC 复核即可。

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
- 6 单元生长图案(COMPLEX11):求解在两段预算内未终止,由 0×0 防护排除;其后的 7 单元图案(COMPLEX12)同样无法生成——CBC 在最大模型上**不遵守时间上限**(无法中断超长的根松弛求解),故这两个图案的生成不会终止,已从数据集中移除(不会进入任何记录);<s>`bestRecord-seperateadder`(phase 2 的逐图案记录)未生成</s>——已用 phase 2 的忠实回放(`pySrc/replay_seperateadder.py`)生成,与真实循环同公式、同浮点;
- 行高仍为 2.6 vs GSCL45 的 2.47(见 §5.5/§5.7(2));`originalAstranStdCells/` 已全部按 2.6 重生成(16 个单元,含本轮的 CLKBUF1/DFFNEGX1/DFFPOSX1/MUX2X1/NOR3X1)。

### 5.9 第五轮:补齐基线单元时的 ASTRAN 崩溃(2026-09-25)

重生成 `NOR3X1` 时暴露 ASTRAN 三处**上游遗留**缺陷(前几轮未触发,因为 adder 用到的单元 P/N 数量恰好相等)。

**(1) 单管"串联腿"折叠读 `trans[-1]`(`cellnetlst.cpp: seriesFolding`)**

折叠只对 P/N 数量不等的单元触发:短的一侧会被 `link=-1` 的 GAP 占位补齐(见下)。而 `seriesFolding` 对**长度为 1 的串联序列**(如 NOR3X1 的并联 PMOS 对、NMOS 腿)会走"首晶体管"分支并读取 `transToFolding[i+1]`——该处是 `-1` 哨兵,`trans[-1]` 越界。上游在 release 构建下是静默 UB(腿上的晶体管被悄悄丢弃)。修复:长度 1 的腿直接在**真实 drain/source 网**之间拆分(两端不加后缀,否则腿悬空、晶体管从单元里消失)。

**(2) 路由用 GAP 槽位的宽度读 `trans[-1]`(`autocell2.cpp: route`)**

P/N 数量不等时,`transPlacement` 用 `link=-1` 的 GAP 条目把两条 ordering 补齐到等长(`cellnetlst.cpp` `transPlacement`),而 `route()` 对**每个**槽位读 `getTrans(link).width`——GAP 槽位即 `trans[-1]`。共 4 处(两条 track 范围 while 循环 + 两条 next-track while 循环)。修复:link==-1 时按宽度 0 处理(GAP 不占扩散宽度,语义正确)。

**(3) MSYS2 自带 python 遮蔽求解器包装(环境问题)**

为装 gdb 而 `pacman -S mingw-w64-x86_64-gdb` 时,依赖把 `mingw-w64-x86_64-python`(3.14,无 python-mip)装进了 `C:\msys64\mingw64\bin`。`Astran.py` 把该目录置于 PATH 之前(ASTRAN 运行期 DLL 需要),于是 `gurobi_cl.cmd` 里的裸 `python` 解析到 MSYS2 解释器 → `ModuleNotFoundError: No module named 'mip'`,压缩静默失效。修复:`Astran.py` 把**当前流程所用的解释器目录**放在 PATH 最前(mingw64 其次),DLL 仍能解析、求解器包装始终用带 mip 的 python。

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

`gds.cpp: generateUnits` 硬编码的 UNITS 双精度字节解码为 (8.17e-9, 7.98e-33) —— 物理上荒谬。写出器对内部坐标统一乘 2(`designmng.cpp` EXPORT_LAYOUT),内部单位为 1/MINSTEP=2.5nm,故一个 DBU 实为 MINSTEP/2=1.25nm;但乱码 UNITS 使任何遵守规范的读者无法按此解释,gdstk 等回退到 1nm DBU,把全部图形画成设计值的 80%(接触孔 52nm vs 规则 65nm、栅长 40nm vs 50nm、单元 3.36×2.08 vs 日志 4.2×2.6)。而面积度量读的是**日志**宽度(`GDSIIAnalysis._readAstranCellWidth`),与物理 GDS 相差 25%。修复:UNITS 字节改为 (0.00125, 1.25e-9)(`struct.pack('>d')` 计算的 IEEE 754),并注明推导。验证:重生成后 GDS 实测尺寸与日志完全一致(AND2X1 1.0×2.6µm、接触孔 0.065µm)。

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

从 `stdCelllib` 提取的 GSCL45 约定:LEF `CoreSite SIZE 0.38 BY 2.47`、M1 pitch 0.19µm、abutment 导轨 0.13µm 高、宽度取 0.19 的倍数、`gscl45nm.lib` 标称电压 1.1V、`gds2_encounter.map` 的 stream 号(metal1=49、via=50、metal2=51、via2=61、metal3=62、via3=30、metal4=31、via4=32、metal5=33)。

- `pySrc/Astran.py`:`ASTRAN_VGRID=ASTRAN_HGRID=0.19`(原 0.20)、`ASTRAN_SUPPLY_SIZE=0.26`(原 0.72;内部 `supWidth = max(supplyVSize, W1M1)/2 = 0.13` → 导轨高 0.13µm)、`ASTRAN_NWELL_POS=1.235 = H/2`(使 nwell/pwell 等高,与手工库一致;初版取过 1.0825,井高不等)。行高 = 13 × 0.19 = **2.47µm = GSCL45 site 高**。
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

- `make_stage.py` 装配 `dist/stage/`:流程本体(pySrc、stdCelllib、benchmark/blif 去掉 BoomBranchPredictor 与 DCache 两个 >90MB 巨型网表、tools/astran/build、tools/gurobi_cl、doc)+ 从开发机 Python 3.11 复制的**裁剪运行时**(site-packages 按 `SITE_KEEP` 保留列表,2.9GB → 970MB);
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
- `THIRD_PARTY_NOTICES.md`(仓库根):逐组件清单——ASTRAN(来源/版权头/无许可文本的如实记录/修改记录/wxWidgets LGPL 动态链接)、gurobi_cl 包装(自有)+ python-mip(EPL-2.0)+ CBC(EPL-1.0)、stdCelllib(GSCL45=FreePDK45 系 Apache-2.0、sky130=Apache-2.0、gpdk45nm.m=Cadence 专有)、benchmark(EPFL 研究用、BOOM/Rocket/Gemmini BSD-3 系)、内置 Python 依赖全表(逐包许可证,并指向 runtime 内 dist-info 自带文本);
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
- `pySrc/BLIFPreProc.py`:`load_liberty_file` 增加 (路径,mtime) 键控的进程级缓存,返回浅拷贝隔离 `load_bool_gate_from_blif` 的 bool-* 注入(避免跨基准污染)。实测:第二次解析 0.93s→0.01s。
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
1. `pySrc/Astran.py:45-46`:日志缺 `Cell Size` 行时 `assert(False); return 123`——`python -O` 下 assert 被剥离会静默返回 123µm 假宽度(应改抛异常);
2. `pySrc/main.py:247-248`:`bestRecord-seperate` 在逐模式循环之前以 `'w'` 打开,循环中途异常会留下空/半截记录;
3. `pySrc/main.py:92`:`cellIdsContained>=11` 用 `continue` 跳过但队首未弹出,依赖后续分支弹出才不死循环(脆弱);
4. `pySrc/BLIFPreProc.py:123-124`:库中找不到 `.subckt` 类型直接 `assert(False)`;`BLIFGraphUtil.py:82-84` 多驱动网静默覆盖 `predCell`,均无告警;
5. `pySrc/GDSIIAnalysis.py:18-21` 注释仍写"基线 H=3.2/本地 2.6"(现行 2.47),且两个 `load*GDS*` 函数名误导(实际读 LEF/日志)——文档漂移,行为正确。

**算法层面风险(转化为优化路线图的动机,详见 doc/RESEARCH_AND_OPTIMIZATION.md)**:
- 编码不对子节点排序(`BLIFPreProc.py:222-235` 无 sort):根节点多输入类型不同时,同构实例会得到不同编码→频次系统性低估(P0-1);
- 节省求和无重叠去重:不同模式的簇可共享单元(`setCluster` 覆盖),`main.py:185-188` 直接求和会重复计收益(P0-2);
- 生长宽度恒为 1(`BLIFPatternGrowth.py:104` 的 `[:1]`)且不知面积:COMPLEX10 实证负收益(−56.05,bestRecord-seperateadder:5)(P0-3);
- 唯一归属为破坏式 enforcement:占用冲突时整个旧簇被 `disabled=True`,无收益比较(`BLIFPatternGrowth.py:118-120`);
- flow_core 与 main.py 无任何等价测试,"faithful port"靠人工评审(P0-5)。

**验证**:194 单测通过(校验未触碰流程代码,仅改文档)。

### 5.18 第十四轮:隐患修复与 P0/P1 优化落地(2026-10-09)

**§5.17 五处代码隐患已全部修复(带回归测试,test_hazard_fixes.py 等)**:
1. `Astran.loadAstranArea` 缺日志时改为 `raise RuntimeError`(原 `assert(False); return 123` 在 `python -O` 下静默造假宽度);
2. `main.py` 两个 `>=11` 守卫由 `continue` 改为弹出队首(原写法空转整个迭代预算);`flow_core.py` 两处同步;
3. `main.py` 第二阶段 `bestRecord-seperate` 改为末尾才打开写盘(原开头 `'w'` 截断,中途崩溃留空文件);
4. `BLIFPreProc` 未知单元类型改抛 `ValueError`(含类型名与 lib 路径),`PIN=net` 畸形行显式报错;
5. `DesignNet.addPin` 多驱动网保留 last-wins 但发出 `RuntimeWarning` 并计数(`DesignNet.multiDriverCount`)。

**P0 优化(行为变化已标定)**:
- P0-1 编码规范化(`canonical_pattern_code`,根在前、子节点排序):trace 字符串因此对既有 outputs 快照改名(如 `[XNOR2X1,XOR2X1,OAI21X1]`→`[XNOR2X1,OAI21X1,XOR2X1]`),重生成时以新名为准。**大基准实测收益显著**(`pySrc/canon_impact.py`):BoomBranchPredictor 2721→1793 组(合并 737 个虚假分裂、回收 21541 个实例)、DCache 2084→1459(13503)、GemminiLoopConv 2829→1787(14588);adder 网表顺序本来就一致,数字不变。
- P0-2 节省重叠去重(`countUncoveredClusters`):同轮候选共享的簇只计一次;bestRecord 中 clusterNum 变为去重后计数。
- P0-3 束搜索+预估剪枝:`grow_sequence_of_clusters` 接受 `benefitEstimator`(新增 `pySrc/benefit.py` 的 ShrinkModel,按"尺寸→收缩率"在线标定、取保守 max);`growBeamWidth=2`(globalVariables)/`cfg.grow_beam=2`(GUI)每轮生长前 2 个队首;≥10 单元的队首不再生长(其 11 单元后代在版图阶段必然被剔除)。COMPLEX10 型负收益(−56.05)在其首个观测后会被剪枝。
- P0-4 可布性第二指标(新增 `pySrc/routability.py`):从 .Astranlog 解析 `Rt. Density` 与 Pathfinder 尝试轮数,报告默认开启;硬门限 `routabilityDensityGate`/`cfg.max_rt_density` 默认 None(先测量后执法)。
- P0-5 flow_core≡main.py 等价测试:桩 ASTRAN(按 .sp 内容哈希定宽)比较两流程 bestRecord(见 tests/unit/test_flow_parity.py)。

**P1 优化**:
- P1-7 电气量(新增 `pySrc/electrical.py`):解析 liberty 的 `cell_leakage_power`/引脚电容/LUT 均值延迟代理;模式级汇总含 internal_nets(合并内化的网数=动态功耗节省代理)。report-only,不改选择准则。
- P1-8 PDK 注册表(新增 `pySrc/pdk_config.py`):freepdk45 与 Astran.py 常量强一致(测试钉住);sky130(8×0.34µm)/gf180(14×0.28µm)为脚手架,.rul 未编写前 raise;`nwellPos` 恒取 H/2 防再次漂移。
- P1-9 端口顺序变体(新增 `pySrc/portorder.py`):确定性变体集(恒等/电源在前排序/反转/种子洗牌),只重写 .subckt 头部;评估走注入式 runner。
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

**阶段 0 版图合理性校验门(pySrc/layout_sanity.py)**:对生成 .gds 做结构检查(非退化、metal1 高度=行高、宽度网格对齐、层与电源标签齐全),标定方式与 GUI 查看器一致(16.5 units/µm、井区外扩不计入)。main.py/flow_core 默认开启剔除(`layoutSanityGate`)。真实 COMPLEX0/1/9 全部通过;等价测试桩同步升级为最小合法 GDS。

**yosys 重导入(用户指定优先级)**:① `electrical.py` 增 area 属性与逐引脚电容(`pin_caps`);② 新增 `timing_power.py`:解析 liberty 时序弧(cell_rise/fall、rise/fall_transition)与 internal_power LUT(delay_template_6x6:行=负载 pF、列=输入转换 ns),双线性插值(边缘钳位),并在模式 DAG 上做迷你 STA(逐网负载=被驱动引脚电容和、最坏弧级延迟、摆率传播、最长路径、翻转能量),已用库角点值验证;③ 新增 `yosys_import.py`:探测 yosys→`stat -json`→防御式解析 area/num_cells/histogram 并与流程的 lib 面积和交叉校验;本机无 yosys 时优雅降级。全部 report-only 接入 main.py 与 flow_core(pattern 事件带 timing_power)。

**阶段 1 宽度代理(pySrc/width_proxy.py)**:特征(单元数、晶体管数、基线宽度和)→Ridge 回归,训练语料=仓库既有 12 个 COMPLEX 版图。真实 LOO:MAPE 16.4%、R²=0.79——粗筛可用、精度有限;对 COMPLEX9(好)过估、对 COMPLEX10(坏)方向正确,故默认 report-only,生长估计器替换由 `useWidthProxyForGrowth` 显式开启。

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

**实现(pySrc/liberty_gen.py)**:对每个生成的 COMPLEX 单元输出 .lib 片段——
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

1. **复用资格判定(pySrc/reuse.py)**:`reuseEligible(cluster)` = 单输出(仅一个逃逸成员输出脚)+ 函数 support≤4、逻辑深度≤4(深度只数"含运算符或≥2 操作数"的括号层,组合包裹不计)。组合函数复用 liberty_gen 的 `_composeFunction`。
2. **生长偏置(internalizeOnly)**:`grow_sequence_of_clusters(+_BasedOn)` 新增 `internalizeOnly`——只吸收"输出负载全部落在簇内"的邻居,吸收不新增逃逸输出,单输出性保持。
3. **流程接线**:main.py/flow_core 逐候选报告 reuse 资格;`requireReuseEligible`/`cfg.require_reuse_eligible` 可选门限(默认关,打开即只收单输出简单函数模式)。
4. **两个接口修复**(真 bug):① `_clusterInterface` 的 zip 截断改为按网名/位置配对,且"无网对象的外部输入"正确判为接口输入(修复前生成片段 inputs=0,abc 提前失败);② `_composeFunction` 成员引脚同名串扰——先做 `@@k@@pin@@` 唯一令牌化再单遍替换(修复前组合函数串入他成员的同名引脚)。

**端到端验证(真实 abc)**:单输出合成簇 [NAND2,NAND2,OR2](函数 ¬(ab)∨¬(cd),support 4/深度 4)→ .lib 片段 → 扩展库 → 设计 `y=~(a&b)|~(c&d)` → **ABC RESULTS: COMPLEX_SO cells: 1** ✓。另修 yosys abc 在 Windows 的临时目录混合分隔符问题(测试内 TMP/TEMP 正斜杠化)。固化测试:test_reuse 4 例(含真实 abc 端到端,自跳过)。

**现状与下一步**:adder 现有模式均多输出(测试钉住 top-10 全不合格),复用路径需在"复用模式"下重跑挖掘(`requireReuseEligible=True` + 生长 `internalizeOnly`),预期得到单输出简单函数的新模式族。280 单测通过。

### 5.27 双模式并存:物理库与综合复用库(2026-10-10)

**并存机制**:`AUTOCELL_REUSE_MODE=1` 时 main.py 切到复用模式——初始聚类 `singleOutputSeeds=True`(只保留接口逃逸输出=1 的种子,`_escapeOutputCount`)+ 生长 `internalizeOnly=True`(只吸收输出负载全在簇内的邻居)+ 输出目录隔离为 `outputs/<bench>_reuse`,物理模式快照不受影响;`requireReuseEligible` 门限兜底。

**加种子过滤的原因**:首轮实验证明 adder 初始聚类 top-30 **全部多输出**——单输出约束若只在生长/验收阶段,种子本身不合格就无从谈起;必须从种子开始。

**adder 对照实验结果(pySrc/reuse_experiment.py)**:

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

- core/evaluate.py 收编评估层:electrical/timing_power/routability/reuse/width_proxy/layout_sanity/benefit/liberty_gen/pdk_config 的公开面;core/external.py 收编工具层:ASTRAN 常量与运行面/GDSIIAnalysis/yosys_import/yosys_eval。
- core/pipeline 的依赖导入全部改走两个门面(BLIFPreProc/BLIFPatternGrowth/spice 星号导入保留,属 parse/seed/growth/export 层);test_facades 钉住"pipeline 绑定的对象与门面导出的对象是同一份"(杜绝双实现漂移)与"门面 Qt-free"。
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
- **4.2 SMT 联合 folding+placement 参考实现**(pySrc/smt_cell_placer.py,P2-13 落点,8 单测):CP-SAT 建模,串联链=内节点度 2 识别,链成员同行+首尾相接(共享扩散);折叠受腿宽制造上限约束(无上限时折叠永远无收益,ceil 只会加宽);NoOverlap2D;目标 min(1000·宽度+腿数)。关键修正:单行/极性模型给 COMPLEX0 4.75µm,与 ASTRAN 2.09 差一倍——ASTRAN 每极性用两排扩散堆叠,参考模型必须同样支持两行/极性(2.47µm)。简化项如实记录(平行组共享、扩散断、行粘性未建模),宽度是理想化下限。
- **4.3 多模态 LLM Agent 资源整合**(pySrc/llm_hint_provider.py,P2-15 落点,9 单测):Hint 协议+离线确定性提供方+OpenAI 兼容多模态提供方(文本网表+GDS 截图→JSON,任何失败降级 [] 并记日志)+内容寻址缓存(sha256)+`suggestHintsBatch` 线程池并行。env 门控 `AUTOCELL_HINT_MODE`(默认 off),core/config 加 hintMode,core/pipeline 在 SPICE 导出点挂提示日志(仅报告)。测试:离线确定性、门控、缓存命中免网络、LLM 故障降级、批量并行保序、from_env 读 hintMode。
- **4.4 pin accessibility 度量**(pySrc/pin_accessibility.py,5 单测):按 §三 论文(ISPD'23/DAC'24/FastPass/DATE'23/ISCAS'24)的可检查结论实现 on-track(引脚中心落轨道网格)/blocked(多晶跨引脚金属)/crowd(同轨列引脚数),单元分=均值;与 GDS 查看器同一 log 校准纪律。合成 GDS 精确定住 1.0/0.5/0.9 与离轨 −0.5;COMPLEX0 实测 0.500(VCC/GND 轨 x=1.045 离格,VCC 多晶阻塞 0.00)。调试记录:loadCellGeometry 曾丢失图层信息导致"金属1自身+轮廓被判为 poly 阻塞"(A 引脚 1.0→0.5 误报),修复为保留 (layer, pts)。
- **RESEARCH 文档膨胀事故**:5623712 的"刷新"把 doc/RESEARCH_AND_OPTIMIZATION.md 写成 28MB/32.4 万行——同一 14 行状态块重复 2.2 万次(唯一行仅 710),原 17KB 文献综述被覆盖。恢复 1ba428a 版本为基底,重写状态表(新增 SMT/LLM/pin-accessibility 行)、新增 §三(12 篇 pin accessibility 论文+整合说明)、§四(四项工作证据)、§五(更新版下一步 9 项),旧三/四/五 重编号为 六/七/八。教训:文档生成脚本必须校验输出大小/唯一行占比,写回前 diff。
- **验证**:新增 30 单测(SMT 8 + LLM 9 + pin-accessibility 5 + pdk 4 新增/改写 + 既有 4),全量回归见提交记录。
