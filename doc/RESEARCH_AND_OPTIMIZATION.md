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

> **实施状态（2026-10-09 全面同步）**：
>
> | 项 | 状态 | 证据 |
> |---|---|---|
> | P0-1 编码规范化 | ✅ 已合入 | canonical_pattern_code；大基准回收 1.4万–2.2万实例/基准（canon_impact） |
> | P0-2 重叠去重 | ✅ 已合入 | count_uncovered_clusters；bestRecord 去重口径 |
> | P0-3 束搜索+在线剪枝 | ✅ 已合入 | grow_sequence_of_clusters 接受 benefit_estimator；growBeamWidth=2 |
> | P0-4 可布性指标 | ✅ 已合入 | routability（Rt. Density+Pathfinder 轮数），门限默认关 |
> | P0-5 等价测试 | ✅ 已合入 | test_flow_parity（CLI≡GUI，现为同一实现） |
> | P1-7 电气量 | ✅ 已合入 | electrical + timing_power（LUT 迷你 STA） |
> | P1-8 PDK 注册表 | ✅ **.rul 已写** | pdk_config + tech_sky130.rul / tech_gf180.rul（主源 LEF 核对，status=draft，DRC 待跑） |
> | P1-9 端口变体 | ✅ 工具就绪 | portorder（评估需跑 ASTRAN） |
> | P1-10 规范化影响 | ✅ 已合入 | canon_impact 实测报告 |
> | P1-11 多行高 | ✅ 几何就绪 | multi_row_variant |
> | P2 阶段0 版图校验门 | ✅ 已合入 | layout_sanity（默认开启） |
> | P2 阶段1 宽度代理 | ✅ 已合入 | width_proxy 训练管线（train→persist→load） |
> | P2 阶段2 CP-SAT | ✅ **已默认化** | 后端默认 cpsat；快照按新口径重生成（总节省 11.46%） |
> | yosys 重导入 | ✅ 已合入 | 真实 stat 交叉校验（707 单元逐类型一致）+ abc 可用（vendored） |
> | 综合复用路径 | ✅ 已合入 | reuse（单输出+简单函数）+ internalize_only 生长；abc 端到端证明 |
> | 架构重构 | ✅ 完成 | core 八层 + 双门面 + 四 shim + flow_core 委托；300 单测全绿 |
> | SMT 引擎 | ✅ 已合入 | smt_engine 包（布局+布线完整 SAT 编码；NAND2 全链闭环，≤8 管边界见 §四.2） |
> | LLM 提示整合 | ✅ 已合入 | llm_hint_provider（offline/llm 双提供方、降级、缓存、并行；pipeline 挂点默认 off） |
> | pin accessibility 度量 | ✅ 已合入 | pin_accessibility（轨道对齐/多晶阻塞/同轨拥挤；COMPLEX0 0.500） |
> | pin accessibility 论文 | ✅ 已检索整合 | 12 篇 2023–2026（§三） |

详见 [AUDIT_REPORT.md](AUDIT_REPORT.md) §5.33。

### P0 —— 低成本、立即收益（不动 ASTRAN）

| # | 优化 | 落点 | 修哪个缺陷 |
|---|---|---|---|
| P0-1 | **编码规范化**：BFS 时对子节点按类型名排序（或按排序后的 (类型,引脚) 元组），消除枚举顺序敏感 | `blif_preproc.extract_and_encode_subgraph_tree`（flow/blif_preproc.py:222-235） | 同构实例分裂成多编码、频次系统性低估（校验报告 §L3）。注意：会改变所有 trace 与既有 COMPLEX 命名，需整体重生成 outputs 并做前后频次对比实验 |
| P0-2 | **收益重叠去重**：累计节省前对 top-N 候选的 cellIds 取并集，共享单元只计一次（或按归属分摊） | `main.py:185-188` / `gui/flow_core.py` 对应处 | 节省高估（校验报告 §L6） |
| P0-3 | **生长宽度>1 的束搜索**：每步保留 top-2/3 邻居分支，用"预估节省 = 频次×(基线宽−估算宽)"剪枝；把 COMPLEX10 式负收益在送版图前挡掉 | `blif_pattern_growth.grow_sequence_of_clusters`（:104 的 `[:1]`） | 生长宽度 1、生长不知面积（COMPLEX10 −56.05） |
| P0-4 | **第二评价维度（routability 代理）**：从 .Astranlog 提取轨道占用/引脚分布，或实现 FastPass 式 pin-access 评分，与宽度一起构成准入门槛 | `Astran.loadAstranArea` 同位置扩展；评估汇总处 | 纯宽度代理（回应 Cell-Flex/Routability Booster 的批评） |
| P0-5 | **flow_core ≡ main.py 等价测试**：固定 seed 在小基准（如 adder topThr=1）上断言两者 bestRecord 一致 | `tests/unit/` 新增 | 三份控制流副本的漂移风险 |
| P0-6 | 顺手修已记录隐患：`astran.py:45` 假宽度 123、`main.py:247` bestRecord 半截写、解析层 `assert(False)` 改显式异常 | 见 AUDIT_REPORT 新增发现 | — |

### P1 —— 中等工作量（本周–本月）

| # | 优化 | 说明 |
|---|---|---|
| P1-7 | **timing/power 感知收益模型**：Liberty 解析补上 delay/leakage/电容字段（`blif_preproc.load_liberty_file` 现只取 direction）；收益从"宽度差"扩展为 α·Δwidth + β·Δleakage + γ·Δ(关键路径影响)；先用静态估计，远期接 FusionCell 式代理模型 | 数据障碍已在校验报告 §L2 定位 |
| P1-8 | **多 PDK 支持（工艺约束参数化）**：把 `astran.py:58-63` 的六个几何常量收进 per-PDK 配置（rowheight/grid/supplysize/nwellpos/celltemplate + .rul/.map 路径）；为 **SKY130、GF180** 各写一份 .rul/.map（**已完成，见 §四.1**；剩余工作是跑 DRC 验证后把 status 从 draft 翻成 validated），再攻 ASAP7；GUI 的 `pdk_editor.py` 已有雏形可复用 | 关键是把 gear ratio（CPP:M1 pitch）当一阶参数暴露（CPCell 的启示），而非只换数字 |
| P1-9 | **端口顺序优化**：现在顺序是遍历副产品且实测影响 ±100% 宽度。低成本方案：对同一网表生成 3–5 个端口排列变体并行缓存评估（借鉴 ASP-DAC'26 双面工作的变体枚举思想）；进阶：TOPCELL 式学习生成 |
| P1-10 | **e-graph 等价类挖掘（CellE 路线）**：作为 `heuristicLabel…+grow_sequence_of_clusters` 的上位替代评估；先行实验：在 adder 上对比 e-graph 枚举与现有编码的候选集合差异 |
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

## 三、pin accessibility 近期论文整合（2026-10-09 检索，OpenAlex/DOI 核验）

针对"宽度唯一评价"与"入库单元能否被详细布线吃掉"两条批评的专项检索
（与 §一.E 的 Cell-Flex/FastPass/Routability Booster 互补，聚焦 2022–2026
的 pin access 专项工作）：

1. **Pin Access-Oriented Concurrent Detailed Routing** | ISPD 2023 | <https://doi.org/10.1145/3569052.3571875>
   并发详细布线的 ILP 访问点联合求解。→ 单元引脚应保证"至少一个无冲突
   访问点"，而不是最大化引脚金属长度。
2. **Concurrent Detailed Routing with Pin Pattern Re-generation for Ultimate Pin Access Optimization** | DAC 2024 | <https://doi.org/10.1145/3649329.3655918>
   伪 pin 提取/布线保住每 I/O 一个访问点，解开 89% 局部不可布区。→ 长/多
   点引脚图案浪费布线资源：单元工具应最小化引脚金属足迹、同时保证每引脚
   一个健壮访问点。
3. **FastPass: A Fast Pin Access Analysis Framework for Detailed Routability Enhancement** | TCAD 2023/24 | <https://doi.org/10.1109/TCAD.2023.3346302>
   DRC 干净访问路线生成 + 增量 SAT 求最优访问方案。→ **SAT 式访问判定可
   当候选版图的适应度函数**（本仓库 pin_accessibility 度量的直接参照）。
4. **Routing Intent Aware Pin Access Point Selection for Standard Cell Designs** | ISQED 2024 | <https://doi.org/10.1109/ISQED60706.2024.10528690>
   按网的路由意图选访问点，DRV/线长 −1.4–2%。→ 引脚访问点选择应与该网
   的预期走向一致（方向感知选点）。
5. **Adaptive Pin Pattern Modification on Standard Cells Towards ECO Routing** | ICCAD 2025 | <https://doi.org/10.1109/ICCAD66269.2025.11240901>
   PST/PF/PB 三种引脚图案改造修复 ECO 路由。→ 生成引脚应容忍后期几何
   编辑（平移/截断/桥接）不破 DRC。
6. **Sub-10nm Standard Cell Library Design Methodology for On-Grid Pin Accesses** | ISCAS 2024 | <https://doi.org/10.1109/ISCAS58744.2024.10558407>
   非整数 CPP/M1P 齿比的 7.5-track 库，on-grid 访问 DRV 降 46–83%。→
   **引脚必须落在路由轨道网格上**（度量第一项）。
7. **A Graph-Based Approach for Optimizing Pin Access in Nanosheet FET Standard Cell Library Synthesis** | ISPD 2026 | <https://doi.org/10.1145/3764386.3779576>
   动态跨 M0/M1 引脚分配 + 引脚长度上限 + 垂直访问冲突消解（DRV 降 97.6%）。
   → 跨层引脚分配与"短引脚优先"，直接可移植到晶体管级生成器。
8. **Synthesis and Utilization of Standard Cells Amenable to Gear Ratio of Gate-Metal Pitches for Improving Pin Accessibility** | DATE 2023 | <https://doi.org/10.23919/DATE56975.2023.10137264>
   按真实 gate:metal 齿比（3:2/4:3）生成引脚图案，避开离轨访问。→ **引脚
   相对真实轨道网格放置**（度量第一项的另一依据）。
9. **Routability Booster: Synthesize a Routing Friendly Standard Cell Library by Relaxing BEOL Resources** | ISPD 2024 | <https://doi.org/10.1145/3626184.3633326>
   合成时主动让出一条 M1 轨给上层布线，track assignment 与晶体管布局、
   MILP 引脚金属分配联合。→ **轨道足迹应是共优化决策**。
10. **Pin Access-aware Multiple Via Pillar Co-Design for Routability Optimization** | ASP-DAC 2025 | <https://doi.org/10.1145/3658617.3697731>
   通孔柱与 PG 条会挡住邻居引脚。→ 引脚落点应避开 MOL/BEOL 通孔柱可能
   插入的位置。
11. **Design Technology Co-Optimization and Time-Efficient Verification for Enhanced Pin Accessibility in the Post-3-nm Node** | IEEE Access 2024 | <https://doi.org/10.1109/ACCESS.2024.3427332>
   低轨数环境五种 DTCO 方法 + 预 P&R 访问性检查器 + LTC 作为额外访问资源。
   → 库应随附快速预布线访问性检查器（本仓库 pin_accessibility 即是）。
12. **MAXCell: PPA-Directed Multi-Height Cell Layout Routing Optimization using Anytime MaXSAT with Constraint Learning** | ICCAD 2024 | <https://doi.org/10.1145/3676536.3676706>
   单元内轨道路由 = MaxSAT + 学习约束，支持多行高。→ 单元内路由作为
   SAT 问题 + 学习约束，是多行高场景的规模化路径。

**整合落地**（`flow/pin_accessibility.py`，5 个单测钉住）：对生成的 GDS
按上列 1/3/6/8/11 的可检查结论实现三项结构度量——**on-track**（引脚中心
落在轨道网格）、**blocked**（多晶栅跨过引脚金属，堵死通孔落点）、**crowd**
（同轨列其他引脚数）。实测 COMPLEX0 = 0.500：VCC/GND 供电轨 x=1.045µm
离格（0.19 网格），VCC 还被多晶阻塞得 0.00——这是"生成单元有可布性摩擦"
的第一手证据。尚未落地：方向感知选点（4）、跨层引脚分配（7）、轨道足迹
共优化（9）——后两项需要 ASTRAN 内部改动，列入 §五。

---

## 四、本轮落地（2026-10-09）：四项工作与证据

### 4.1 第二 PDK .rul（sky130/gf180）

`tools/astran/build/Work/tech_sky130.rul` / `tech_gf180.rul`，几何全部经
主源 LEF 核对（skywater-pdk-libs-sky130_fd_sc_hd、gf180mcu_fd_sc_mcu7t5v0）：
sky130 用 SITE unithd 0.46×2.72（8 轨×0.34）、met1 w/s 0.14/0.14、rails
met1 0.48+li1 0.17；gf180 用 SITE GF018hv5v_mcu_sc7 0.56×3.92（7 轨×0.56）、
met1 w/s 0.230/0.230、rails 0.60。**修正了脚手架两处数字**：gf180 路由
栅格 0.28→**0.56**、供电 0.44→**0.60**（原按"14×0.28"误读）。未核实的
规则行继承 freePDK45 并在文件头明确标注 PLACEHOLDER——ASTRAN 内部规则
不是权威，权威是 PDK 自己的 DRC deck。`pdk_config` 增加
`loadTechnologyRul` 解析器、状态改为 `draft`（几何真实、DRC 未跑），
`test_pdk_config` 8 测试全绿。

### 4.2 SMT 引擎：联合 folding+placement+routing 的完整 SAT 编码（P2-13 落点）

**参考实现**（`flow/smt_cell_placer.py`，8 单测）：宽度下限打分器，两行/
极性、串联链共享扩散、腿宽制造上限、`min(1000·宽度 + 腿数)`；COMPLEX0
单行 4.75µm → 两行 2.47µm（ASTRAN 2.09µm）。

**完整引擎**（`flow/smt_engine/` 包，11 单测，2026-10-10）：布局与布线
全部编入 CP-SAT。布局：折叠+串联/平行组共享扩散+扩散断间距+双行+栅对齐+
接入点列互斥（P/N/G 三区——跨区 P/N 同列合法，正对真实 NAND2X1）。布线：
每列双区竖段（N/P slot，y 分离同列共存）、几何覆盖表（GND 竖段 [0,4] 只
覆盖底部轨——真实不堵轨的原因）、栅接触=段与 poly 交叉、连通=全覆盖+桥接
段、交叉安全（信号+电源竖段）。GDS 诚实头（1um/1nm）直接被
layout_sanity 与 pin_accessibility 消费；verify 从解重算全量复验。

**实测**：NAND2 6 列全链闭环（verify 0 违例、pin accessibility 0.933、
sanity 通过）；COMPLEX0（14 管）布局 OPTIMAL 19 列（3.61µm）但联合布线
不可行——**适用边界 ≤8 管**（4 轨+一列双竖段的资源限制；真实版图靠更多
层/迭代布线）。调试记录与每条模型语义修正见 AUDIT §5.35。

### 4.3 多模态 LLM Agent 资源整合（P2-15 落点）

`flow/llm_hint_provider.py`（9 单测）：`Hint` 协议（fold_max/row_order/
track_grid/keepaway）+ 离线规则提供方（确定性，符合 AGENTS.md 不变量 9）
+ OpenAI 兼容多模态提供方（文本网表 + GDS 截图 → JSON 提示，任何失败
降级为空并记日志）+ 内容寻址缓存 + `suggestHintsBatch` 并行批处理
（资源整合提速）。环境门控 `AUTOCELL_HINT_MODE`（默认 off：结果与无此
功能逐字节一致）；`core/config.py` 加 `hintMode`，`core/pipeline.py` 在
SPICE 导出点挂提示日志（仅报告、不改行为）。

### 4.4 pin accessibility 度量（§三的落地）

`flow/pin_accessibility.py`（5 单测）：on-track/blocked/crowd 三项结构
度量 + 单元总分（均值）；与 GDS 查看器同一套 log 校准纪律（ASTRAN 的
UNITS 记录是假的）。合成 GDS 精确定住 1.0/0.5/0.9 分值与离轨 −0.5 分；
COMPLEX0 实测 0.500（见 §三）。CLI：`python pin_accessibility.py --gds
outputs/adder/COMPLEX0.gds --log outputs/adder/COMPLEX0.Astranlog`。

---

## 五、下一步可行计划（按优先级，均可直接开工）

1. **第二 PDK DRC 验证**：`AUTOCELL_PDK=sky130|gf180` 跑 2–3 个单元 →
   用 PDK 自己的 DRC deck 体检 → 通过后把 `pdk_config` 状态翻成
   `validated`（§四.1 的收尾）。
2. **SMT 评分批量对照**：对 `outputs/*/COMPLEX*.sp` 批量跑
   `smt_cell_placer.py --dir`，给出全快照的"参考宽度 vs ASTRAN 宽度"
   对照表；再补平行组扩散共享与扩散断间距后收紧下限（§四.2 的扩展）。
3. **LLM 提示接入生长剪枝**：offline 的 fold 提示与 benefit_estimator
   联动（超宽器件送版图前先折叠提示），仍保持 env 门控默认关（§四.3）。
4. **pin accessibility 门槛**：把单元分接入 layout sanity gate（默认关，
   避免改变现有快照），论文 4/7/9 的方向感知选点、跨层分配、轨道足迹
   共优化列为 ASTRAN 内部改动的独立项（§三）。
5. **复用库全基准挖掘**：`AUTOCELL_REUSE_MODE=1` 跑 ctrl/max/multiplier
   等，找单输出简单函数模式（adder 几乎无空间，其他基准待验证）。
6. **全设计重映射评估**：用 vendored abc 对多个基准做 baseline vs
   extended 综合对照（评估工具 evaluate_design_savings 已就绪）。
7. **ngspice 签署级表征通道**：COMPLEX*.sp + gpdk45nm.m（level 54
   BSIM4）→ 瞬态仿真标定 LUT 估计器。
8. **多行高实验**：对 >20 管模式用 multi_row_variant 实测宽度-面积权衡。
9. **性能**：基线单元缓存哈希化（内容寻址替代 mtime）、宽度代理随快照
   重训。

---

## 六、开放 PDK 清单（链接已验证，按迁移难度排序）

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

## 七、可复用开源工具（GitHub 已验证活跃）

- `ckchengucsd/SMT-based-STDCELL-Layout-Generator-for-PROBE2.0`——SMT 同步布局布线（CPCell 系）
- `The-OpenROAD-Project/OpenROAD`——RTL-to-GDS 全流程（整片收益验证）
- `ALIGN-analoglayout/ALIGN-public`——学术版图引擎（394★，ASTRAN 外最知名）
- `broccolimicro/floret`——定制单元版图生成（2025 活跃）
- `Yixin-Gong/GigaCell`——晶体管级 1D 布局引擎
- `b8kang/L2L-Logic_to_Layout_Exploration`——开源单元库+版图+表征数据集
- `ckjasonlee0722/rl-transformer-transistor-placer`——RL+Transformer 布局
- `Rushindra205/standard-cell-generator-bspdn`——BSPDN 单元生成

## 八、检索局限（如实声明）

1. Semantic Scholar API 全程 429，已用 OpenAlex 替代；DBLP/ACM DL 正文被反爬，
   IEEE 条目经 OpenAlex/Crossref 摘要核验。
2. "layout compaction" 独立主题的 2023–2026 新论文近乎绝迹（学界转向联合
   优化）；stack forcing / sleep transistor 与自动库生成、multi-Vt 复合单元
   版图生成均未检到针对性新工作（多为电路层或 sizing 子问题）。
3. "frequent subgraph mining" 字面延续仅 CellE（已改用 e-graph）——主流转向
   学习方法，这本身是本项目挖掘层的演进信号。
4. pin accessibility 专项检索（2026-10-09）命中 12 篇（§三）；其中 ISPD'23/
   DAC'24 的并发路由系列、ISPD'26 纳米片库合成均为近两年工作，未发现更早
   的、可替代本轮整合结论的条目。
