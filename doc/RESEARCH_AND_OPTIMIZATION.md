# 近三年文献综述与算法优化路线图（2023–2026）

> **检索方法**：arXiv API、OpenAlex API、Crossref（DOI/venue 核验），覆盖
> DAC/ICCAD/DATE/ISPD/ASP-DAC/TCAD/TVLSI/SBCCI/VLSI-TSA 2023–2026。所有条目附
> 可解析链接；Semantic Scholar 全程限流（429）、DBLP 反爬，已用 OpenAlex 替代。
> **动机**：本报告与 [LAYER_VERIFICATION.md](LAYER_VERIFICATION.md) 发现的
> 六项合理性风险一一对应——每条优化都回答"它修掉哪个已知缺陷"。

---

## 一、文献综述（按主题）

### A. 版图综合综述（定位坐标）

1. **Standard Cell Layout Generation: Review, Challenges, and Future Works** | ASP-DAC 2025 | <https://doi.org/10.1145/3658617.3703146>
   系统综述 sub-10nm 单元版图自动化的晶体管布局与 in-cell 布线算法谱系，含
   复杂度分析；明确提出 "standard cell fusion"（单元融合）方向——正是本项目的
   学术对标词。
2. **Standard Cell Layout Generation: Methodological Evolution and Architectural Impacts** | ASP-DAC 2026 | <https://doi.org/10.1109/asp-dac66049.2026.11420759>
   沿"手工→启发式→精确求解→AI"与"planar→CFET/Flip-FET、多行高、BPR/背面
   金属"两轴梳理。ASTRAN 处于"1990s 启发式"坐标位。

### B. 库扩展与模式挖掘（对应第 3/4 层）

3. **CellE: Automated Standard Cell Library Extension via Equality Saturation** | arXiv 2026 | <https://arxiv.org/abs/2603.12797>
   **与本项目目标最接近的新工作**：对映射后网表做 equality saturation 生成
   e-graph，穷举功能等价子电路，再用模式挖掘选面积最优新单元。平均面积
   −15.41%，商业流程延迟再 −8%。→ 其等价类枚举从机制上消除我们"编码顺序
   敏感漏匹配"与"贪心生长宽度 1"两个缺陷。
4. **Technology Mapping Using Multi-Output Library Cells** | ICCAD 2023 | <https://doi.org/10.1109/ICCAD57390.2023.10323999>
   多输出复杂单元只有在映射器能识别"部分输出复用"时才真正省面积。→ 我们
   目前把复合单元当单输出黑盒，挖掘时可专门寻找"共享中间节点、多扇出锥"
   的模式。
5. **Target Circuit Matching in Large-Scale Netlists using GNN-Based Region Prediction** | arXiv 2025 | <https://arxiv.org/abs/2507.19518>
   GNN 先预测候选区域再精确匹配。→ 可作生长阶段的预筛器。
6. **DeepGate3: Towards Scalable Circuit Representation Learning** | arXiv 2024 | <https://arxiv.org/abs/2407.11095>
   子电路级嵌入。→ 拓扑相似但编码串不同的模式可用嵌入聚类合并，减少重复
   送 ASTRAN 的冗余单元（每个省 5–10 min）。

### C. 精确求解框架（对应第 7 层 place/route/compact 的质量上限）

7. **SMT-Based Optimal Transistor Folding and Placement** | ASP-DAC 2026 | <https://doi.org/10.1109/asp-dac66049.2026.11420355>
   SMT 统一编码 folding+placement，LCS mono-dummy 插入对齐 P/N 链增强扩散
   共享；ASAP7 上比手工单元面积 −4.12%，172 单元全部可布线。→ ASTRAN 的
   阈值接受布局可拿它做质量基线。
8. **SO3-Cell: Simultaneous Optimization of Topology, Placement, and Routing** | ICCAD 2025 | <https://doi.org/10.1109/iccad66269.2025.11240677>
   MILP 同时优化拓扑/布局/布线；44 管单元 7.2h 解出，block 级功耗 −35%、
   面积 −31.1%。→ 证明大复杂单元的全自动版图可行，其等价管划分剪枝可反哺
   ASTRAN 前处理。
9. **CPCell（gear-ratio 感知，SMTCell 扩展版）** | arXiv 2026（前身 SLIP 2023） | <https://arxiv.org/abs/2603.13665>
   支持任意 CPP:metal-pitch gear ratio 的分层网格图 + 约束编程布局布线，
   含 MOL/M0 pin 与 pin-accessibility 约束。→ 我们把 `set grid 0.19` 写死，
   CPCell 说明**网格几何本身就是 DSE 变量**，是多 PDK 支持的直接参照。
10. **CoP&R: Co-Optimizing Place-and-Route via MCTS and AllSAT** | ICCAD 2025 | <https://doi.org/10.1109/ICCAD66269.2025.11240928>
    MCTS 联合布局布线、AllSAT 枚举个解空间。→ 其 MCTS 动作空间设计可改进
    ASTRAN transPlacement。
11. **Standard Cell Layout Synthesis for Dual-Sided 3D-Stacked Transistors** | ASP-DAC 2026 | <https://doi.org/10.1109/asp-dac66049.2026.11420512>
    双面 I/O 分配变体枚举择优。→ 其"枚举引脚分配变体"思想可立即用于我们
    `.subckt` 端口顺序问题（AGENTS.md 已记录端口顺序改变版图的坑）。

### D. 超越单元边界的晶体管级优化（远期路线）

12. **DiSPlace: Diffusion-Sharing-Driven Transistor-Level Placement** | ICCAD 2025 | <https://doi.org/10.1109/iccad66269.2025.11240688>
13. **TransRoute: Hierarchical Transistor-Level Routing** | DAC 2025 | <https://doi.org/10.1109/dac63849.2025.11132558>
14. **TransOpt: Scalable Transistor-Level P&R Optimization** | ISPD 2026 | <https://doi.org/10.1145/3764386.3779582>
    三篇构成"打破单元边界"谱系。TransOpt 与本项目哲学最兼容：保留单元抽象、
    只对合并的复杂单元局部做晶体管级精调（开源 3nm GT3 PDK 已验证）。
15. **CFET-HMF: Hybrid Metaheuristic Framework for CFET Cells** | VLSI-TSA 2026 | <https://doi.org/10.1109/vlsitsa69131.2026.11527922>
    PSO×SA 混合 + 快速拥塞估计闭环。→ **对 ASTRAN 最直接的改良模板**：替换
    成本低（同为元启发式），给出拥塞代理的现代化做法。

### E. ML 辅助与可布性评估（对应第 6 层评估维度扩展）

16. **NVCell 2**（NVIDIA，RL 单元版图） | ISPD 2023 | <https://doi.org/10.1145/3569052.3578920>
    lattice-graph 可布性模型作 RL 奖励；难布线单元 DRC/LVS 干净率 +84–87%。
17. **Cell-Flex Metrics** | ISPD 2025 | <https://doi.org/10.1145/3698364.3705344>
    超越 pin accessibility 的"版图灵活性"度量，以其为目标使 block 面积
    −13.2%；KAN 预测 DRV 准确率 0.65→0.79。→ **直接回应我们"只量宽度"
    的局限**。
18. **FastPass: Fast Pin Access Analysis** | TCAD 2024 | <https://doi.org/10.1109/TCAD.2023.3346302>
    详细布线前预测引脚可达性。→ 可作复合单元"入库门槛"第二指标。
19. **Routability Booster**（让一条 M1 轨换可布性） | ISPD 2024 | <https://doi.org/10.1145/3626184.3633326>
    宽度略增但可布性更好的单元可能全局更优——挑战"宽度唯一"评价。
20. **Transistor Placement Routability Prediction** | SBCCI 2025 | <https://doi.org/10.1109/SBCCI66862.2025.11218677>
    布局阶段预测最终可布性。→ 可作阈值接受的新适应度项。
21. **FusionCell: Cross-Attentive Layout+Netlist Fusion for Performance Prediction** | arXiv 2026 | <https://arxiv.org/abs/2605.20287>
    DeiT 编码版图 + graph transformer 编码网表，时序/功耗预测 MAPE 0.92%。
    → 替代"每个候选跑 5–10min 版图"的粗筛代理。
22. **LLM for Standard Cell Layout Design Optimization**（NVIDIA） | IEEE LAD 2024 | <https://arxiv.org/abs/2406.06549>
    LLM（ReAct）生成器件聚类约束喂给现有版图引擎；2nm 时序单元面积最高
    −19.4%。→ **与本架构最契合的 LLM 用法：LLM 出约束、ASTRAN 出版图**。
23. **TOPCELL: Topology Optimization via LLMs** | arXiv 2026 | <https://arxiv.org/abs/2604.14237>
    GRPO 微调生成晶体管扩散共享拓扑，质量媲美穷举、加速 85.91×。→ 我们
    "端口/晶体管序列保持插入序"的被动策略可被学习生成替代。

### F. PDK / DTCO / 先进器件

24. **PROBE3.0: Design-Technology Pathfinding** | arXiv 2023 | <https://arxiv.org/abs/2304.13215>
    自动生成可配置 PDK+单元库（含 BSPDN）并全 flow 评估 PPAC——"自动生成库→
    整片评估"的正规范式。
25. **Virtual_N2_PDK: Predictive 2nm Nanosheet PDK** | TVLSI 2025 | <https://doi.org/10.1109/TVLSI.2025.3529504>
26. **Optimal Transistor Folding and Placement for CFET** | DAC 2024 | <https://doi.org/10.1145/3649329.3658261>
27. **Optimal Layout Synthesis of Multi-Row Standard Cells** | ICCAD 2024 | <https://doi.org/10.1145/3676536.3676784> + **Better Intra-Cell Routability for Multi-Row** | ASP-DAC 2025 | <https://doi.org/10.1145/3658617.3704453>
    多行高单元：>20 管的复合大单元用双倍高可能显著省宽；第二篇显式给出
    宽度–可布性帕累托。

### G. Timing / Power 驱动

28. **Learning-Driven Physically Aware Gate Sizing** | TCAD 2024 | <https://arxiv.org/abs/2403.08193>
    sizing 收益高度依赖实例上下文 → 我们挖掘阶段应记录模式出现处的负载/
    转换环境，而不只计数频率。
29. **Standard Cell Libraries for Optimal Subthreshold Circuits** | i-PACT 2023 | <https://doi.org/10.1109/i-PACT58649.2023.10434863>
    亚阈值下串联管数限制等库级设计准则。→ 低功耗方向落地：筛选"低电压
    友好"拓扑（限制复合单元串联深度）。

---

## 二、优化路线图（按优先级，每条标注落点与所修缺陷）

### P0 —— 低成本、立即收益（不动 ASTRAN）

| # | 优化 | 落点 | 修哪个缺陷 |
|---|---|---|---|
| P0-1 | **编码规范化**：BFS 时对子节点按类型名排序（或按排序后的 (类型,引脚) 元组），消除枚举顺序敏感 | `BLIFPreProc.extractAndEncodeSubgraph_Tree`（pySrc/BLIFPreProc.py:222-235） | 同构实例分裂成多编码、频次系统性低估（校验报告 §L3）。注意：会改变所有 trace 与既有 COMPLEX 命名，需整体重生成 outputs 并做前后频次对比实验 |
| P0-2 | **收益重叠去重**：累计节省前对 top-N 候选的 cellIds 取并集，共享单元只计一次（或按归属分摊） | `main.py:185-188` / `gui/flow_core.py` 对应处 | 节省高估（校验报告 §L6） |
| P0-3 | **生长宽度>1 的束搜索**：每步保留 top-2/3 邻居分支，用"预估节省 = 频次×(基线宽−估算宽)"剪枝；把 COMPLEX10 式负收益在送版图前挡掉 | `BLIFPatternGrowth.growASeqOfClusters`（:104 的 `[:1]`） | 生长宽度 1、生长不知面积（COMPLEX10 −56.05） |
| P0-4 | **第二评价维度（routability 代理）**：从 .Astranlog 提取轨道占用/引脚分布，或实现 FastPass 式 pin-access 评分，与宽度一起构成准入门槛 | `Astran.loadAstranArea` 同位置扩展；评估汇总处 | 纯宽度代理（回应 Cell-Flex/Routability Booster 的批评） |
| P0-5 | **flow_core ≡ main.py 等价测试**：固定 seed 在小基准（如 adder topThr=1）上断言两者 bestRecord 一致 | `tests/unit/` 新增 | 三份控制流副本的漂移风险 |
| P0-6 | 顺手修已记录隐患：`Astran.py:45` 假宽度 123、`main.py:247` bestRecord 半截写、解析层 `assert(False)` 改显式异常 | 见 AUDIT_REPORT 新增发现 | — |

### P1 —— 中等工作量（本周–本月）

| # | 优化 | 说明 |
|---|---|---|
| P1-7 | **timing/power 感知收益模型**：Liberty 解析补上 delay/leakage/电容字段（`BLIFPreProc.loadLibertyFile` 现只取 direction）；收益从"宽度差"扩展为 α·Δwidth + β·Δleakage + γ·Δ(关键路径影响)；先用静态估计，远期接 FusionCell 式代理模型 | 数据障碍已在校验报告 §L2 定位 |
| P1-8 | **多 PDK 支持（工艺约束参数化）**：把 `Astran.py:58-63` 的六个几何常量收进 per-PDK 配置（rowheight/grid/supplysize/nwellpos/celltemplate + .rul/.map 路径）；为 **SKY130、GF180** 各写一份 .rul/.map（规则宽松、最接近 freePDK45 格式，作为第二 PDK 验证移植性），再攻 ASAP7；GUI 的 `pdk_editor.py` 已有雏形可复用 | 关键是把 gear ratio（CPP:M1 pitch）当一阶参数暴露（CPCell 的启示），而非只换数字 |
| P1-9 | **端口顺序优化**：现在顺序是遍历副产品且实测影响 ±100% 宽度。低成本方案：对同一网表生成 3–5 个端口排列变体并行缓存评估（借鉴 ASP-DAC'26 双面工作的变体枚举思想）；进阶：TOPCELL 式学习生成 |
| P1-10 | **e-graph 等价类挖掘（CellE 路线）**：作为 `heuristicLabel…+growASeqOfClusters` 的上位替代评估；先行实验：在 adder 上对比 e-graph 枚举与现有编码的候选集合差异 |
| P1-11 | **多行高评估**：>20 管复合单元尝试双倍高（ASTRAN 端只需改 rowheight 常量实验）；收益判定加入"宽度×行数"统一口径 | ICCAD'24/ASP-DAC'25 已给出评估框架 |
| P1-12 | **挖掘覆盖率报告**：统计被 bypass 的 bool/DFF 单元与未被任何模式覆盖的逻辑占比，在 GUI 设计页显式呈现 | 目前静默丢弃（校验报告 §L2） |

### P2 —— 研究级（月度–学期）

| # | 优化 | 说明 |
|---|---|---|
| P2-13 | **place 现代化**：把阈值接受换成 PSO×SA 混合（CFET-HMF 模板）或在其适应度中加入可布性预测（SBCCI'25）；更激进：SMT 联合 folding+placement（ASP-DAC'26）做质量基线对照 |
| P2-14 | **route/compact 换引擎**：Pathfinder→CP-SAT（TransRoute 已验证数百至数千管）；ILP compaction 的 CBC→CP-SAT 迁移可显著缩短"证优"时间（学界已无 compaction 专门新工作，两阶段范式本身成了差异化特征） |
| P2-15 | **LLM 出约束、ASTRAN 出版图**：LLM 生成器件聚类/扩散共享约束注入 transPlacement 初解（NVIDIA LAD'24 路径，风险最低） |
| P2-16 | **TransOpt 式局部晶体管级精调**：保留单元抽象，仅对合并大单元局部打破边界优化（ISPD'26） |
| P2-17 | **CFET/BSPDN 远期**：ASTRAN 单面架构不支持；迁移需双面感知引擎（ASP-DAC'26、CFET-HMF），先以 Virtual_N2/开源 3nm GT3 PDK 做可行性评估 |

### 预期收益与风险排序（建议先做）

**P0-1 → P0-3 → P0-4 → P1-8 → P1-7**：P0-1 直接提高模式频次统计的完备性
（所有下游数字都会变准），P0-3 用最少改动砍掉负收益分支，P0-4 回应学术界对
"宽度唯一"最一致的批评，P1-8/P1-7 打开多 PDK 与电气感知两条独立价值线。
每条落地都必须遵守 AGENTS.md 的不变量（面积口径一致、确定性、trace 身份），
并在 AUDIT_REPORT.md 留痕。

---

## 三、开放 PDK 清单（链接已验证，按迁移难度排序）

| PDK | 节点 | 获取 | 迁移难度 |
|---|---|---|---|
| FreePDK45 | 45nm 预测型（现用） | <https://www.eda.ncsu.edu/wiki/FreePDK45>（注册） | — |
| SKY130 | 130nm | <https://github.com/google/skywater-pdk> | 低（规则宽松，.rul 格式最接近） |
| GF180MCU | 180nm | <https://github.com/google/gf180mcu-pdk> | 低 |
| Nangate OCL | 45/15nm | <https://si2.org/open-cell-library/>（免费注册） | 中 |
| ASAP7 | 7nm FinFET 预测型 | <https://github.com/The-OpenROAD-Project/asap7> + asap7sc7p5t_28 | 高（规则复杂度跃升，需重验证 LP/DRC 适配） |
| IHP SG13G2 | 130nm BiCMOS | <https://github.com/IHP-GmbH/IHP-Open-PDK> | 中高 |
| Virtual_N2 | 2nm 纳米片预测型 | 论文 DOI: 10.1109/TVLSI.2025.3529504 | 研究用途 |
| OpenROAD-flow-scripts | 多 PDK 集成 | <https://github.com/The-OpenROAD-Project/OpenROAD-flow-scripts> | 复合单元入库后的整片评估基准 |

## 四、可复用开源工具（GitHub 已验证活跃）

- `ckchengucsd/SMT-based-STDCELL-Layout-Generator-for-PROBE2.0`——SMT 同步布局布线（CPCell 系）
- `The-OpenROAD-Project/OpenROAD`——RTL-to-GDS 全流程（整片收益验证）
- `ALIGN-analoglayout/ALIGN-public`——学术版图引擎（394★，ASTRAN 外最知名）
- `broccolimicro/floret`——定制单元版图生成（2025 活跃）
- `Yixin-Gong/GigaCell`——晶体管级 1D 布局引擎
- `b8kang/L2L-Logic_to_Layout_Exploration`——开源单元库+版图+表征数据集
- `ckjasonlee0722/rl-transformer-transistor-placer`——RL+Transformer 布局
- `Rushindra205/standard-cell-generator-bspdn`——BSPDN 单元生成

## 五、检索局限（如实声明）

1. Semantic Scholar API 全程 429，已用 OpenAlex 替代；DBLP/ACM DL 正文被反爬，
   IEEE 条目经 OpenAlex/Crossref 摘要核验。
2. "layout compaction" 独立主题的 2023–2026 新论文近乎绝迹（学界转向联合
   优化）；stack forcing / sleep transistor 与自动库生成、multi-Vt 复合单元
   版图生成均未检到针对性新工作（多为电路层或 sizing 子问题）。
3. "frequent subgraph mining" 字面延续仅 CellE（已改用 e-graph）——主流转向
   学习方法，这本身是本项目挖掘层的演进信号。
