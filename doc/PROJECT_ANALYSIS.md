# AutoCellLibX 项目目录详细分析

> 分析日期:2026-09-24
> 分析范围:`D:\AutoCellLibX`(git 仓库,当前分支 `main`)

---

## 1. 项目概述

**AutoCellLibX** 是一个基于频繁子图挖掘的自动化标准单元库扩展框架,由香港科技大学(HKUST)可重构计算系统实验室(Reconfiguration Computing Systems Lab)开发,论文发表于 arXiv(2207.12314,2022)。

**核心思想**:在技术映射后的门级网表(BLIF)中,通过高效的频繁子图挖掘算法寻找高频出现的标准单元组合模式(pattern),再用模式组合算法迭代挑选一组模式,将其合并成"复杂标准单元"(COMPLEX cell),生成其 SPICE 网表和 GDSII 版图,作为初始标准单元库的扩展,从而减小整个 VLSI 设计的面积。

**声明效果**:针对 31 个 benchmark 设计,平均可在 1.1 小时内为每个设计扩展最多 5 个自定义标准单元,平均节省 4.49% 设计面积。

**许可**:Apache License(非商业用途);商业用途需联系导师 Wei Zhang(eeweiz@ust.hk)授权。

---

## 2. 目录结构总览

```
D:\AutoCellLibX
├── .git/                      # git 仓库
├── .gitignore                 # 忽略 __pycache__/ 与 astran
├── .vscode/
│   ├── launch.json            # VS Code 调试配置(运行 pySrc/main.py)
│   └── settings.json
├── LICENSE                    # Apache License
├── README.MD                  # 项目说明(论文、特性、调用图)
├── requirements.txt           # Python 依赖(tqdm/numpy/networkx/easydict/blifparser/gdspy/liberty-parser)
├── benchmark/                 # 各领域 benchmark 设计 + 综合脚本
│   ├── blif/                  # 24 个技术映射后的门级网表(已用 yosys 综合)
│   ├── batchSynthesis.py      # yosys 批量综合脚本(Verilog → BLIF)
│   ├── syn.ys                 # yosys 综合模板(read_liberty/abc/dfflibmap/write_blif)
│   ├── EPFL/EPFLBenchmarks.zip
│   ├── boomModule/            # BOOM 处理器模块源(Verilog,zip)
│   ├── gemmini/Gemmini.zip    # Gemmini 加速器源
│   └── rocketModule/          # Rocket 处理器模块源(Verilog,zip)
├── doc/                       # 文档与示意图
│   ├── callGraph.png          # 项目调用图
│   ├── experimentalResult.png # 实验结果示例(复杂单元版图)
│   ├── flow.png               # 整体流程图
│   ├── motivation.png         # 动机图(标准单元合并示例)
│   ├── pattern.png            # 模式挖掘示意图
│   └── PROJECT_ANALYSIS.md    # 本文档
├── pySrc/                     # Python 主代码
│   ├── main.py                # 入口:完整流水线
│   ├── BLIFPreProc.py         # BLIF/liberty 解析、构图、启发式初始聚类、数据集转换
│   ├── BLIFGraphUtil.py       # 数据结构(StdCellType/DesignCell/DesignNet/PatternCluster...) + 画图
│   ├── BLIFPatternGrowth.py   # 模式生长算法(吸收邻居扩展模式)
│   ├── Astran.py              # 调用 ASTRAN 工具生成版图 + 读取面积
│   ├── GDSIIAnalysis.py       # GDS 版图面积解析(gdstk)
│   ├── spice.py               # SPICE 子电路解析与复杂单元网表导出
│   ├── globalVariables.py     # 全局常量(bypassTypes = ["DFF", "bool"])
│   ├── GNNModel.py            # GraphCNN 模型(TensorFlow,实验性)
│   ├── BLIFGNNTraining.py     # GNN 训练(当前主流程未使用,被注释)
│   ├── resultAnalysis.py      # 结果汇总脚本(生成 results/result.csv)
│   ├── resultAnalysisCountTops.py # 按 top 模式汇总结果的变体
│   ├── clean.sh / README / requirements.txt
│   ├── originalAstranStdCells/ # 原始单元经 ASTRAN 生成的 .gds/.run/.Astranlog
│   ├── originalGSCL45StdCells/ # FreePDK45 GSCL 库原始 .gds(31 个单元)
│   └── outputs/               # 每个 benchmark 的输出目录
│       ├── someResults.zip    # 论文相关结果打包
│       └── adder/             # 当前运行实例的输出(见 §9)
├── stdCelllib/                # PDK 与标准单元库数据
│   ├── cellsAstranFriendly.sp # ASTRAN 友好的单元 SPICE 网表(24 个单元)
│   ├── gscl45nm.lib           # GSCL45 liberty 时序库(输入文件)
│   ├── gscl45nm.lef / .tlf / .db / gds2_encounter.map / gpdk45nm.m
│   ├── gscl45nmVfiles.zip
│   └── sky130_fd_sc_hd__tt_025C_1v80.lib  # SkyWater 130nm 库(备用,约 13MB)
└── tools/                     # README.md 说明:"Install ASTRAN here"
```

---

## 3. 核心模块详细分析(pySrc)

### 3.1 `main.py` — 主流水线入口

主函数执行以下步骤(单个 benchmark 循环):

1. **环境设置**:`CUDA_VISIBLE_DEVICES=-1`(禁用 GPU);配置 `ASTRANBuildPath = "D:/astran/Astran/build"`。
2. **加载原始单元面积**:`loadOrignalGSCL45nmGDS()` 读取 GSCL45 GDS 面积;`loadAstranGDS()` 读取 ASTRAN 重生成的原始单元面积。
3. **加载数据**:`loadDataAndPreprocess()` 解析 `stdCelllib/gscl45nm.lib` + `benchmark/blif/<name>.blif`,构建门级图、启发式初始聚类、生成 GNN 数据集。
4. **为缺失 GDS 的原始单元调用 ASTRAN**(路径存在时)。
5. **模式迭代扩展循环**(`topThr=5` 轮 × 每轮检查前 `topThr` 个模式序列):
   - 对每个候选模式序列:若面积覆盖不足(`size×cnt < ratioThr×cells` 且 `cnt < cntThr`)则跳过;
   - 绘制模式子图 PNG、导出 SPICE 网表(`exportSpiceNetlist`)、调用 ASTRAN 生成 `COMPLEX<n>.gds`;
   - 计算面积节省 `(oriUnitArea - newUnitArea) × clusterNum`,记录最佳组合;
   - 用 `growASeqOfClusters()` 把最频繁模式吸收邻居扩展出新模式,更新模式序列池;
   - 有改进则写入 `bestRecord-<benchmark>`,否则停止。
6. **逐模式明细第二轮**:对检测到的每个模式(`detectedPatterns`)重新聚类(`heuristicLabelSomeNodesAndGetInitialClusters_BasedOn`),仅追踪目标模式沿 `patternExtensionTrace` 生长,输出 `bestRecord-seperate<benchmark>`,内含表格:
   `designOverallArea | saveArea | saveRatio | patternCnt | patternSize | patternCoverage | patternName | patternCode`。

**关键阈值参数**:
| 参数 | 值 | 含义 |
|---|---|---|
| `topThr` | 5 | 每轮考察的模式/轮次数上限 |
| `ratioThr` | 0.05 | 模式覆盖率下限(占全部单元比例) |
| `cntThr` | 30 | 模式出现次数下限 |
| 单元数上限 | 11 | 单个复杂单元含单元数上限 |

**当前配置差异(相对上游)**:
- `ASTRANBuildPath = "D:/astran/Astran/build"`(原为 `../tools/astran/Astran/build`);
- `technologyPath = "D:/astran/Astran/build/Work/tech_freePDK45.rul"`;
- 求解器使用开源包装 `GUROBI_CL = "D:/aclx-tools/gurobi_cl.cmd"`(替代 Gurobi `gurobi_cl`);
- benchmark 列表当前只启用 `["adder"]`。

### 3.2 `BLIFPreProc.py` — 数据预处理与初始聚类

- `loadLibertyFile()`:用 `liberty.parser.parse_liberty` 解析 `.lib`,构建 `StdCellType`(引脚方向)。
- `loadBoolGateFromBLIF()`:把 BLIF 中的布尔函数(真值表)作为 `bool-<tt>` 类型的虚拟单元加入库。
- `genGraphFromLibertyAndBLIF()`:解析 BLIF(`blifparser`),为每个 `.subckt`/逻辑门创建 `DesignCell`,为每个网创建 `DesignNet`,构建 **networkx DiGraph**(节点=单元,边=信号流);统计各单元类型频次取 top 类型作为特征类型,其余标记 `minorType`;含 `DFF`/`bool` 的单元标记 `stopType`(不参与聚类)。
- `extractAndEncodeSubgraph_Tree()`:以某单元为根、沿输入反向做深度受限(`depthLimit`)的树编码,编码串 = 单元类型序列。
- `heuristicLabelSomeNodesAndGetInitialClusters()`:对每个非 bypass 单元提取深度 1 的树编码,按编码频次排序取 top 30 作为初始模式;把同编码单元簇成 `DesignPatternCluster`,同一编码的所有簇构成一个 `DesignPatternClusterSeq`;打印标注/聚类覆盖率。
- `heuristicLabelSomeNodesAndGetInitialClusters_BasedOn()`:同上,但只保留编码串与 `targetPatternTrace` 前缀匹配的模式(用于第二轮逐模式追踪)。
- `convertBLIFGraphIntoDataset()`:把图转成 GNN 训练用数据集(`S2VGraph`,节点 one-hot 特征、`edge_mat`)。**注意:已从 TensorFlow 常量改为 numpy 数组**(见 §11),`BLIFGNNTraining`/`GNNModel` 在主流程中被注释掉。
- `getArea()`:按单元类型面积字典累加总面积。
- `loadDataAndPreprocess()`:串联上述步骤,返回 `(BLIFGraph, cells, netlist, stdCellTypesForFeature, dataset, maxLabelIndex, clusterSeqs, clusterNum)`。

### 3.3 `BLIFGraphUtil.py` — 数据结构与绘图

数据结构(核心):

| 类 | 职责 |
|---|---|
| `StdCellType` | 单元类型:名称、输入/输出引脚列表 |
| `DesignCell` | 设计中的单元实例:id、名称、类型、输入/输出网、所属 cluster、`stopType` |
| `DesignNet` | 网:id、名称、前驱/后继单元与引脚 |
| `DesignPatternCluster` | 模式簇:包含的单元 id 列表、`patternExtensionTrace`(编码轨迹,如 `[NAND2X1,NAND2X1,OR2X1]+c2o0_OAI21X1`)、`clusterTypeId`、`disabled` 标记 |
| `DesignPatternClusterSeq` | 同一模式的所有簇集合(即模式序列) |

辅助函数:
- `removeEmptySeqsAndDisableClusters()`:剔除空序列与 disabled 簇。
- `sortPatternClusterSeqs()`:按 `簇数×簇大小` 降序、大小升序排序(lexsort)。
- `drawColorfulFigureForGraphWithAttributes()`:绘制模式子图,优先 `graphviz_layout(dot)`,失败回退 `spring_layout`(本地修改);按 `type` 属性着色并标注单元名,导出 PNG。

### 3.4 `BLIFPatternGrowth.py` — 模式生长算法

`growASeqOfClusters(BLIFGraph, clusterSeq, ...)`,对应论文中的**模式增长/组合**环节:

1. 遍历当前模式序列中所有簇的每个单元,收集其输入前驱与输出后继邻居;
2. 跳过已在簇内、已访问、`stopType`、或属于同类模式簇的邻居;
3. 对每个邻居生成"特征码" `typeName_c<i>i<j>`(输入侧)或 `typeName_c<i>o<j>`(输出侧),编码其在簇中的相对位置(该编码用于保证**技术映射约束下的重叠处理**);
4. 按特征码出现次数排序,取 top 1 特征(示例实现只合并一种邻居);
5. 把该特征对应的所有邻居并入其所在簇,更新 `patternExtensionTrace += "+" + neighborCode`、`clusterTypeId = patternNum`,返回新序列 + 未扩展的旧序列。

`growASeqOfClusters_BasedOn()`:变体,仅当 `targetPatternTrace` 以 `当前trace+"+"+neighborF` 为前缀时才合并,用于第二轮按目标模式生长。

### 3.5 `spice.py` — SPICE 网表处理

- `SPSubcircuit`:解析一个 `.subckt` 块;`renamePrefix(prefix)` 给所有信号/晶体管加前缀(`cl<orderId>#`),`replaceInputPin()` 把单元内部输入引脚重连到前驱单元输出引脚。
- `loadSpiceSubcircuits()`:从 `cellsAstranFriendly.sp` 加载全部子电路。
- `exportSpiceNetlist()`:把一个模式簇内所有单元的子电路拼接:加前缀 → 按网表内部连接替换引脚 → 计算接口(删除完全内部化的输出)→ 生成 `COMPLEX<n>.sp`,文件头/尾注释记录 pattern code、出现次数、单元数、示例实例。

### 3.6 `Astran.py` — ASTRAN 版图综合

- 模块级设置:把 `C:\msys64\mingw64\bin` 加入 PATH(MinGW 运行库,供 Astran.exe 使用);定义开源 Gurobi 替代 `GUROBI_CL = "D:/aclx-tools/gurobi_cl.cmd"`(python-mip + COIN-OR CBC 的 `gurobi_cl` 包装)。
- `loadAstranArea(GDSPath, typeName)`:从 `.Astranlog` 解析 `-> Cell Size (W x H):` 行,面积 = 宽 × 0.8 × 3.2(单位换算系数)。
- `runAstranForNetlist()`:生成 ASTRAN shell 命令脚本(`set lpsolve`/`load technology`/`load netlist`/`cellgen select`/`cellgen autoflow`/`export layout`),写 `.run` 文件后调用 `Astran --shell` 执行。**本地修改**:由多轨道循环 `for nTrack in [5,3,4,6]` 改为单次 `cellgen autoflow`(无 nTrack 参数)。

### 3.7 `GDSIIAnalysis.py` — GDS 面积解析

- `loadOrignalGSCL45nmGDS()`:遍历 31 个 GSCL45 单元名,用 `gdstk.read_gds` 读取 `originalGSCL45StdCells/<name>.gds`,计算第 6 层(金属?)面积。
- `loadAstranGDS()`:从 `originalAstranStdCells/` 所有 `.gds` 对应的 `.Astranlog` 读取面积(复用宽×0.8×3.2 换算)。
- **本地修改**:从 `gdspy` 迁移到 `gdstk`(API: `read_gds`/`cell.area(((6,0),))`)。

### 3.8 `globalVariables.py`

仅一行:`bypassTypes = ["DFF", "bool"]` —— 带 DFF(时序)或 bool(布尔函数)字样的单元不参与模式聚类。

### 3.9 GNN 相关(实验性,当前未启用)

- `GNNModel.py`:TensorFlow 实现的 GraphCNN(多层 MLP + 邻域聚合 + epsilon 重加权 + 节点级输出),用于节点嵌入预测。
- `BLIFGNNTraining.py`:`enbeddedNodes_GNN()` 训练该模型并为节点生成嵌入,`encodedEntireGraphWIthLabelOrder()` 把嵌入转成特征排序。
- 主流程中对应导入被注释(`# from BLIFGNNTraining import *`),即当前版本**以启发式聚类替代 GNN 嵌入**,这也是 `convertBLIFGraphIntoDataset` 改为 numpy 数组的原因。

### 3.10 结果分析脚本

- `resultAnalysis.py`:扫描 `outputs/*/best*` 文件,解析保存面积与百分比,生成 `results/result.csv`,并把最佳复杂单元相关文件复制到 `results/<benchmark>/`。
- `resultAnalysisCountTops.py`:针对 `bestRecord-seperate` 格式(按 top 模式明细表)复制对应 `COMPLEX*.sp/gds` 到结果目录。

---

## 4. 执行流水线(数据流)

```
gscl45nm.lib ──┐
               ├─> BLIFPreProc ──> BLIFGraph(有向图)+cells+nets ──> 初始模式簇(深度1树编码)
adder.blif ────┘                        │
                                         ▼
          originalGSCL45StdCells/*.gds ─> loadOrignalGSCL45nmGDS() ─> stdType2GSCLArea
          originalAstranStdCells/*.gds ─> loadAstranGDS() ──────────> stdType2AstranArea
                                         │
    ┌────────────────────────────────────▼────────────────────────────────┐
    │ 迭代(topThr轮):                                                    │
    │  top1 模式序列 → 画PNG → exportSpiceNetlist → COMPLEX<n>.sp          │
    │  → runAstranForNetlist → COMPLEX<n>.gds(+Astranlog)                  │
    │  → loadAstranArea → 面积节省计算 → 记录 bestRecord-<benchmark>       │
    │  → growASeqOfClusters 吸收邻居 → 新模式序列入池 → 排序               │
    └─────────────────────────────────────────────────────────────────────┘
                                         │
                         第二轮:逐模式重新聚类(BasedOn 变体)
                                         ▼
                          bestRecord-seperate<benchmark>(模式明细表)
```

---

## 5. 标准单元库与 PDK 数据(stdCelllib)

| 文件 | 说明 |
|---|---|
| `cellsAstranFriendly.sp` | 24 个单元的 SPICE 子电路(AND2X1/AND2X2/AOI21X1/AOI22X1/BUFX2/BUFX4/CLKBUF1-3/DFFNEGX1/DFFPOSX1/DFFSR/FAX1/HAX1/INVX1/2/4/8/LATCH/MUX2X1/NAND2X1/NAND3X1/NOR2X1/NOR3X1/OAI21X1/OAI22X1/OR2X1/OR2X2/TBUFX1/TBUFX2/XNOR2X1/XOR2X1 等),工艺参数 W=0.5u/0.25u、L=0.05u |
| `gscl45nm.lib` | 主 liberty 时序库(268KB,主流程输入) |
| `gscl45nm.lef/.tlf/.db` | 物理/时序抽象与数据库文件 |
| `gds2_encounter.map` | Encounter GDS layer 映射 |
| `gpdk45nm.m` | FreePDK45 工艺文件 |
| `sky130_fd_sc_hd__tt_025C_1v80.lib` | SkyWater 130nm 库(13MB,备用,对应 TODO 中 ASAP7 类似扩展方向) |

**原始 GDS**:`pySrc/originalGSCL45StdCells/` 含 31 个单元 GDS;`pySrc/originalAstranStdCells/` 含这些单元经 ASTRAN 生成的 GDS(部分单元只有 log,如 AND2X2、INVX2 等无 .gds)。

---

## 6. 基准测试集(benchmark)

- `blif/` 现有 24 个技术映射后的门级网表:adder、arbiter、bar、BoomBranchPredictor、BoomRegisterFile、BoomRob、cavlc、ctrl、DCache、div、GemminiLoopConv、GemminiLoopMatmul、GemminiMesh、i2c、int2float、log2、max、multiplier、priority、router、sin、sqrt、square、voter。
- 来源:EPFL 基准(算术/随机控制)、BOOM 处理器模块、Rocket 处理器模块、Gemmini 加速器(源码以 zip 形式存放)。
- `syn.ys` + `batchSynthesis.py`:yosys 综合脚本模板(`read_liberty -lib gscl45nm.lib` → `synth` → `dfflibmap` → `abc -liberty` → `opt;clean` → `write_blif`),验证设计域覆盖。
- 论文称共 31 个 benchmark;main.py 中启用/注释的基准集合与该数字对应。

---

## 7. 依赖与环境

**Python 依赖**(requirements.txt):`tqdm numpy networkx easydict blifparser gdspy liberty-parser`;本地代码实际还用到 `matplotlib`、`gdstk`(替代 gdspy)。GNN 部分需要 `tensorflow`(当前流程未启用)。

**第三方工具**:
- **ASTRAN**(开源标准单元自动综合工具):安装于 `D:\astran\Astran\build`,工艺文件 `tech_freePDK45.rul`。
- **Gurobi 求解器替代**:`D:\aclx-tools\gurobi_cl.cmd`(python-mip + CBC 的 gurobi_cl 兼容包装),避免商业许可。
- **MinGW 运行库**:`C:\msys64\mingw64\bin`(已由 Astran.py 自动加入 PATH)。

**运行环境**:Windows 10(26100)、Python 3.11(`__pycache__` 中 cpython-311)、Git Bash。

---

## 8. 输出产物(outputs)

每个 benchmark 输出到 `pySrc/outputs/<name>/`:
- `COMPLEX<n>.png` — 模式子图可视化;
- `COMPLEX<n>.sp` — 合并后的复杂单元 SPICE 网表(含 pattern code 注释);
- `COMPLEX<n>.gds` + `.Astranlog` + `.run` — ASTRAN 版图与日志;
- `bestRecord-<benchmark>` — 最佳扩展组合记录(面积节省绝对/百分比、复杂单元列表、运行时);
- `bestRecord-seperate<benchmark>` — 逐模式明细表(面积、覆盖率、pattern code)。

---

## 9. 当前运行状态(pySrc/outputs/adder)

**已完成一次完整闭环运行(2026-09-24 16:20,约 15 分钟)**,产物齐全:

| 文件 | 说明 |
|---|---|
| `COMPLEX0/1/9.{sp,gds,Astranlog,run,png}` | 3 个复杂单元的 SPICE 网表、GDS 版图、ASTRAN 日志、运行脚本、模式可视化 |
| `GDSIILTable.txt` | ASTRAN 导出的 GDS 层映射表 |
| `bestRecord-adder` | 最佳组合:COMPLEX0(61簇×[NAND2X1,NAND2X1,OR2X1])+ COMPLEX1(54簇×[XNOR2X1,XOR2X1,OAI21X1]);相对 ASTRAN 面积省 **9.53%**,相对 GSCL 面积省 **15.26%** |
| `bestRecord-seperateadder` | 逐模式明细:最高单个模式 COMPLEX0 省 6.61%(124.9/2196.3) |

**历史故障与修复**(见下节):原 `Astran.exe` 被 360 安全卫士按 `_popen` 特征误报清除,导致 15:42 首次运行时 `Astranlog` 为 0 字节、无 GDS。已从源码重新编译 ASTRAN(见 §14),流水线恢复正常闭环。

---

## 10. 设计要点(对应论文贡献)

1. **顶点编码算法**:深度受限的树编码 + 邻居相对位置特征码(`c<i>i<j>`/`c<i>o<j>`),兼顾标准单元特征,用于模式增长时的邻居选择;
2. **模式增长**:每次只吸收"同特征码"的邻居,避免模式子图重叠,满足技术映射约束;
3. **模式组合(迭代挑选)**:贪心迭代——每次取覆盖率最高的模式,验证面积节省后才扩展,直至无改进(`bestSaveArea` 判断)或模式过小;
4. **闭环**:门级网表分析 → 库扩展 → SPICE/GDS 版图产物直接用于后端流程。

---

## 11. 未提交修改(git diff 摘要)

工作区相对 HEAD 有 5 个文件修改,`pySrc/outputs/adder/` 未跟踪:

| 文件 | 修改内容 |
|---|---|
| `pySrc/Astran.py` | 引入 MinGW PATH;用开源 `gurobi_cl.cmd` 包装替代 Gurobi;`cellgen autoflow` 去掉 nTrack 多轨道循环(单次执行);`gdspy`/`os.path` 统一化 |
| `pySrc/BLIFPreProc.py` | 移除 `tensorflow` 依赖:`edge_mat`/`node_features` 由 `tf.constant` 改为 numpy 数组;删除无用 import |
| `pySrc/BLIFGraphUtil.py` | 画图布局:graphviz 失败时回退 `spring_layout`(不强制依赖 pygraphviz) |
| `pySrc/GDSIIAnalysis.py` | `gdspy` → `gdstk` 迁移 |
| `pySrc/main.py` | ASTRAN 路径改为本地 `D:/astran/...`;benchmark 列表改为仅 `adder`;使用 `GUROBI_CL` 常量 |

**解读**:这些改动把上游(面向 Linux + Gurobi 商业许可)的实现适配到了**本地 Windows 环境**,同时解耦了 TensorFlow 依赖,使核心挖掘/聚类/版图流程可在无 GPU、无 Gurobi 许可的情况下运行。

---

## 12. 注意事项与潜在问题

1. **ASTRAN 未成功**:`adder` 输出的 `Astranlog` 为空且无 GDS,流水线在版图综合环节未闭环;建议检查 `D:\astran\Astran\build\bin\Astran.exe` 能否独立运行、`gurobi_cl.cmd` 包装是否可执行、MinGW DLL 是否齐全。
2. **面积换算系数**:`*0.8*3.2` 硬编码在 `Astran.py`/`GDSIIAnalysis.py`,换 PDK 需重新标定。
3. **`lib` 与 `sp` 单元集合需一致**:`gscl45nm.lib` 中单元必须都在 `cellsAstranFriendly.sp` 中存在,否则 `exportSpiceNetlist`/ASTRAN 会报错。
4. **模式数量假设**:`main.py` 多次引用 `clusterSeqs[0].patternClusters[0]`,空列表时依赖 `len()==0` 提前 break,但 `heuristicLabel...` 需保证初始至少有一个模式。
5. **GNN 分支未启用**:`BLIFGNNTraining`/`GNNModel` 需要 TensorFlow 2.x,若需复现论文中的 GNN 变体需恢复导入并把 `convertBLIFGraphIntoDataset` 输出改回 TF 格式。
6. **覆盖率阈值耦合**:`ratioThr/cntThr` 与设计规模相关,小设计(如 adder)可能触发 "pattern is too small and bypassed" 提前终止。

---

## 13. 快速上手指南

```bash
pip install -r requirements.txt   # 安装 Python 依赖
# 确认 ASTRAN 安装于 D:/astran/Astran/build 且 gurobi_cl.cmd 可用
cd pySrc
python main.py                    # 运行 adder 流水线(当前配置)
python resultAnalysis.py          # 汇总 outputs/*/bestRecord* → results/
```

---

## 14. 故障修复记录:重新编译 ASTRAN(2026-09-24)

**故障**:15:42 运行 adder 流水线时 `COMPLEX0.Astranlog` 为 0 字节且无 GDS,日志开头出现"拒绝访问。"。根因:**`D:/astran/Astran/build/bin/Astran.exe` 被 360 安全卫士按 `_popen` 特征误报为木马并清除**(14:22 复制 DLL 后、15:42 运行前被删,全盘已无 Astran.exe 副本)。

**修复:从源码重新编译**(工具链与依赖已具备,一次通过,0 错误):

1. **工具链确认**:`C:/msys64/mingw64/bin/` 下 g++ 16.2.0、mingw32-make 4.4.1、wxWidgets 3.2 开发包(头文件 `include/wx-3.2`、库 `libwx_baseu-3.2.a` 等)齐全。
2. **解决 wx-config 路径问题**:msys64 的 `wx-config` 用 `cygpath` 按调用 shell 根解析 `/mingw64`,在 Git Bash 下解析到 Git 的 mingw64(无开发包)。创建自定义 shim:`D:/astran/Astran/bin/wx-config`,硬编码输出 msys64 的 `--cppflags`(`-IC:/msys64/mingw64/lib/wx/include/msw-unicode-3.2 -IC:/msys64/mingw64/include/wx-3.2 -DWXUSINGDLL -D__WXMSW__`)与 `--libs`(`-LC:/msys64/mingw64/lib -lwx_mswu_xrc-3.2 ...`),置于 PATH 首位。
3. **编译**:`cd D:/astran/Astran && PATH="/d/astran/Astran/bin:/c/msys64/mingw64/bin:$PATH" mingw32-make -f nbproject/Makefile-Release.mk build/bin/Astran`,约 2 分钟完成,生成 5.1MB 可执行文件(无扩展名,正好匹配 `Astran.py` 的调用路径 `build/bin/Astran`)。
4. **功能验证**:`Astran --shell` 跑 INVX1 全流程成功(求解器经 `gurobi_cl.cmd` 包装调用 CBC,LP 最优,输出 `Cell Size 0.6 x 2.6`,GDS 生成),与 14:15 官方二进制结果一致。
5. **流水线验证**:重跑 adder,COMPLEX0/1/9 的 SPICE/GDS/日志全部生成,`bestRecord-adder` 与 `bestRecord-seperateadder` 正常输出(见 §9)。

**遗留事项**:
- 新编译的 Astran.exe 与官方版本一样含 `_popen` 调用,360 可能再次误报。**建议在 360 安全卫士中把 `D:\astran\Astran\build\bin` 与 `D:\aclx-tools` 加入信任目录**;若再被清除,从 360 恢复区恢复或按上述步骤重编(对象文件仍在 `build/Release/...` 下,增量重编约 1 分钟)。
- 运行时依赖:wx 3.2 DLL 与工具位于 `C:/msys64/mingw64/bin`,已由 `Astran.py` 自动加入 PATH,无需额外配置。
