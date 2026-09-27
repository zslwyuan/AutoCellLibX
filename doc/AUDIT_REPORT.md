# AutoCellLibX / ASTRAN 技术审查报告

> 审查日期:2026-09-24
> 审查范围:ASTRAN 源码(D:\astran\Astran\src)、AutoCellLibX layout 生成配置、pattern 提取/生长/组合算法
> 审查视角:半导体 PDK / EDA 算法

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

### 3.1 `BLIFPreProc.extractAndEncodeSubgraph_Tree` —— 编码与节点错位

- **错误**:`encodes.append(...)` 位于 `if (not predCell.id in tree)` **之外**,而 `tree.append(...)` 在之内。当同一前驱经多条 net 驱动同一下游(多输出单元如 FAX1,或菱形结构)时,`encodes` 会比 `tree` 多出重复项,导致**编码串与子图结构不对应**;结构等价的模式被编码成不同串 → **模式被错误拆分/归并**。
- **修复**:将 `encodes.append` 移入去重分支,保证编码与树节点严格一一对应。
- **验证**:adder 初始聚类 128 簇,`编码长度 == 簇内单元数` 的不匹配数为 **0**。

### 3.2 `BLIFPatternGrowth.growASeqOfClusters` / `_BasedOn` —— 生长方向不对称

- **错误**:输入前驱方向有"跳过同类型模式邻居"的检查
  ```python
  if curNeighbor.clusterId != -1 and curNeighbor.cluster.clusterTypeId == cluster.clusterTypeId: continue
  ```
  而**输出后继方向缺少同一检查**。后果:输出方向会把"属于同一模式的其它簇"的单元吸收进来,破坏"同一模式多个独立实例"的结构(错误合并/disable 其它簇)。
- **修复**:在两个函数的输出后继循环中补上同类型模式跳过检查,使两个方向语义对称。
- **说明**:该修复改变模式生长路径,故结果会变化;见 §3.4 关于结果波动的说明。

### 3.3 `BLIFPreProc.heuristicLabelSomeNodesAndGetInitialClusters_BasedOn` —— labelId 递增不一致

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
