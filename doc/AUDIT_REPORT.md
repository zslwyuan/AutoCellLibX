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

### 3.4 附加稳健性修复

| 文件 | 修复 |
|---|---|
| `BLIFPreProc.convertBLIFGraphIntoDataset` | `node_features` 列数由固定 `maxNumType=36` 改为 `max(maxNumType, len(feat_dict))`,消除单元类型数 >36 时的 `IndexError`(此前越界检查被注释) |
| `main.py`(两处) | 访问 `clusterSeqs[0]` 前增加 `len(clusterSeqs) == 0` 保护,避免空序列列表导致的 `IndexError` |

### 3.5 修复后的验证结果(adder)

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
3. **Pattern 算法**:修复了 3 处确凿错误(编码错位、生长方向不对称、labelId 不一致)+ 2 处稳健性缺陷,已通过 adder 全流程验证。

> 本次仅实施了第 3 部分的代码修复(在 `pySrc/`);第 1、2 部分按"分析"交付,其修复涉及 ASTRAN 源码与工艺配置,建议单独立项并重新标定。
