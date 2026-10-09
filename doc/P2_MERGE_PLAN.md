# P2 研究级算法合入计划（2023–2026 文献 → 本仓库）

> 输入：[RESEARCH_AND_OPTIMIZATION.md](RESEARCH_AND_OPTIMIZATION.md) 的 P2 清单。
> 排序原则：**先能判对错，再谈优化**（版图合理性校验门是所有引擎替换的前置），
> 然后按"价值 × 可行性 ÷ 对现有不变量的冲击"排序。每个阶段都有独立的
> 可验证出口（测试 + 报告），不允许"半替换"状态进主分支。
>
> 执行状态会实时更新在本文（✅ 已合入 / 🟡 部分 / ⬜ 未动 / ⛔ 环境阻塞）。

## 阶段 0 · 质量闸门（前置）✅ 本轮执行

| 项 | 内容 | 验证 |
|---|---|---|
| 版图合理性校验器 `pySrc/layout_sanity.py` | 对生成的 .gds 做结构性检查：非退化（W,H>0）、bbox 高度≈行高（±5%）、宽度是网格整数倍、含 active/poly/metal1 层、含 VDD/GND 标签；配 `.sp` 端口数对照 | 合成 GDS 夹具 + 真实 `outputs/adder/*.gds` 全过 |

**为什么最优先**：替换任何引擎后，第一个问题就是"新引擎的版图对不对"。
没有这道闸门，SMT/CP-SAT 替换无法验收。

## 阶段 1 · 性能预测代理（FusionCell-lite）✅ 已合入（2026-10-09）

| 项 | 内容 | 验证 |
|---|---|---|
| `pySrc/width_proxy.py` | 用既有 `outputs/*`（.sp+.Astranlog 对）建数据集：特征=管数/端口数/单元数/基线宽度和/模式尺寸，标签=生成宽度；sklearn 回归；LOO 交叉验证报告 MAPE/R²；作为 benefit 估计器的可选增强（先 report-only） | 数据集构建测试 + 模型 sanity（预测>0、单调性） |

**实测结果**：12 样本 LOO MAPE 16.4%、R²=0.79——粗筛可用。对 COMPLEX10
（负收益）方向正确（预测 5.42 > 基线 4.94），但对 COMPLEX9 过估
（预测 4.54 vs 实际 3.61）——故默认 **report-only**，替换生长估计器需显式
开启 `useWidthProxyForGrowth`（globalVariables）/ cfg 开关（GUI）。样本量
到 ~50+ 后重新评估是否默认启用。

对应论文：FusionCell（arXiv'26）的"先预测再版图"思想。全量双模态深度模型
（DeiT+graph transformer）超出本仓库依赖与数据量，**不做**；这里取其核心
主张"廉价代理粗筛候选"落地。衡量标准：对已知负收益（COMPLEX10 形状）是否
给出比 ShrinkModel 更早的信号——已确认。

## 阶段 2 · CP-SAT 压缩/布线引擎（TransRoute 路线）✅ 已合入（2026-10-09）

| 项 | 内容 | 验证 |
|---|---|---|
| `tools/gurobi_cl/cpsat_backend.py` | 复用适配层自解析 LP（不变量 3），改喂 OR-Tools CP-SAT；关键发现：**ASTRAN 的压缩 LP 全整数**（400 DBU/µm），CP-SAT 精确消费无需近似；`GUROBI_CL_SOLVER=cpsat` 启用，CBC 仍为默认；失败语义（全零 .sol）与 option-3 恢复纪律（仅证明 INFEASIBLE）与 CBC 一致；ortools 缺失自动回退 | 小 LP 最优解/INFEASIBLE/端到端 .sol 测试 + `compare_backends.py` 真实模型对拍（结果见 git 历史） |

**真实对拍**（`pySrc/ILPmodel.lp`：11,554 约束 / 2,740 二进制 / 6,447 变量，
各 120s）：CBC objective 2,724,960（OPTIMAL）、width 532 DBU；CP-SAT
objective 2,722,000（FEASIBLE，**−0.11%**）、width 532 DBU——版图宽度一致，
目标值略优。过程中修复两处移植缺陷：inf 系数未随 CBC 解析器丢弃（后端改为
复用 `gurobi_cl._parse_terms` 单一来源）、`0.000000` 字面量误触缩放（检测改
为"非零小数"）。 |

**排在第三的原因**：边界清晰（LP in → .sol out）、有现成黄金对照（CBC 结果），
是四个"换引擎"项里风险最低的。SMT folding+placement、SO3-Cell、CoP&R 都
要重写 ASTRAN 内部表示（C++），本轮不动；z3 同样缺失。

## 阶段 3 · LLM/学习辅助（低风险路径优先）⬜ 待阶段 1 评估

顺序：LLM 出约束（NVIDIA LAD'24，**只产出 placement 提示**、不碰版图）→
TOPCELL 式拓扑排序生成（可作为 portorder 变体集的学习版升级）。
前置：需要可用的 LLM API 配置与离线降级策略；阶段 1 的代理若已足够剪枝，
本阶段优先级下降。

## 阶段 4 · 引擎级替换（研究项目，单独立项）⬜

- SMT 联合 folding+placement（ASP-DAC'26）：先在 ≤12 管小单元上做**参考实现**
  用于给 ASTRAN 布局打质量分（配合阶段 0 的校验门），不是替换。
- CoP&R（MCTS+AllSAT）：若阶段 2 的 CP-SAT 后端落地，其 AllSAT 枚举可复用。
- SO3-Cell（MILP 三同时）：44 管 7.2h 的求解成本与本流程"每单元 5–10min"
  的预算不兼容，除非换商业求解器；**暂不合入，年度复评**。
- NVCell2 / RL-Transformer：需要训练基础设施与大规模数据集，**不合入**，
  其价值已被阶段 1 代理部分覆盖。

## 阶段 5 · 明确不合入（结论性判断）

- DiSPlace/TransOpt（超单元边界晶体管级 P&R）：属于芯片级布局器范畴，
  与本项目"库扩展器"定位正交；若要利用，应作为下游工具的输入而非本仓功能。
- CFET/BSPDN：ASTRAN 是单面 bulk/FinFET 时代架构（单排 P、单排 N、
  顶部电源轨），支持 CFET 等于重写布局器；如需先进节点验证，迁移到
  支持双面的开源引擎（见调研报告开源清单），而非改造 ASTRAN。

## 验收纪律（每阶段必须满足）

1. 不破坏 AGENTS.md 十条不变量（面积口径、确定性、trace 身份、缓存契约…）；
2. 每个合入带机制型测试（不钉绝对数值，钉行为契约）+ 全量 pytest 绿；
3. 版图相关的变更必须过阶段 0 校验门；
4. 行为变化在 doc/AUDIT_REPORT.md 留痕（修了哪个缺陷、宽度如何动）。
