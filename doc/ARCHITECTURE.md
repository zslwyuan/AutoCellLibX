# 架构文档：分层模块化核心（core package）

> 目标（用户）：全面重新设计项目层次与架构，拆分大文件/大类，模块化层次化，
> 便于适配新用例、长期维护、衍生与性能提升；正确性由测试钉住，持续重构。

## 分层结构

```
flow/
  main.py            ← 薄 CLI：构建 FlowConfig → 调 runPipeline（原 587 行单体内联已抽离）
  core/              ← 新分层核心（本架构的主体）
    config.py        ← FlowConfig 数据类：全部可调参数集中（取代 global_variables 可变全局
                       与 main.py 顶部魔法数）；from_env() 读环境变量
    pipeline.py      ← runPipeline(cfg)：完整挖掘流水线（AST 逐字从 main() 提取，
                       行为由等价测试对 GUI 移植版钉住）；含阶段一（贪心/束生长+版图+评估）
                       与阶段二（逐模式记录）
    encoding.py      ← 编码（canonical_pattern_code/extract_and_encode_subgraph_tree/
                       escape_output_count）
    seeding.py       ← 初始聚类（heuristicLabel.../..._BasedOn，AST 逐字提取，
                       blif_preproc 现为 re-export shim）
    graph.py         ← （规划）数据结构门面（blif_graph_util）
    evaluate.py      ← 评估层门面：电气/时序/可布性/复用/宽度代理/版图体检/表征/PDK
                       （收编 electrical/timing_power/routability/reuse/width_proxy/
                         layout_sanity/benefit/liberty_gen/pdk_config）
    external.py      ← 外部工具门面：ASTRAN / gds_analysis / yosys / 重映射评估
  blif_preproc.py     ← shim：seeding 已迁 core，其余解析暂留（下一步迁 core/parse）
  blif_pattern_growth.py ← 生长（下一步迁 core/growth）
  ...其余单职责模块（benefit/routability/electrical/timing_power/liberty_gen/
     reuse/width_proxy/layout_sanity/yosys_import/yosys_eval/pdk_config/...）
  smt_cell_placer.py    ← 2026-10-09 新增：SMT 宽度下限参考实现（打分器）
  smt_engine/           ← 2026-10-10 新增：完整 SMT 引擎（布局+布线联合 SAT 编码）
                          netlist(链/组/朝向/接入点) · layout_model(折叠+共享+断+
                          互斥+栅对齐) · route_model(双区竖段+几何覆盖+段/交叉+
                          连通) · gds(诚实 GDS 头,可被 sanity/pin-access 消费) ·
                          verify(解重算全量复验) · __init__(synth_cell 编排)
  llm_hint_provider.py  ← 2026-10-09 新增：LLM/离线布局提示（Hint 协议、降级、
                          缓存、并行批处理；AUTOCELL_HINT_MODE 门控，默认 off）
  pin_accessibility.py  ← 2026-10-09 新增：生成单元引脚可达性度量（on-track /
                          blocked / crowd，读 GDS 标签+log 校准）
gui/flow_core.py     ← 待迁移：第三份控制流副本，下一步改为消费 core.pipeline
                      （等价测试 test_flow_parity 在迁移前后持续钉住一致性）
```

## 代码质量约定（2026-10-10 起）

1. **命名**：全库 snake_case（2026-10-10 三级整改：模块文件名、633 个标识符、
   文件夹，见 AUDIT 5.34）。例外白名单：Qt 信号/方法名（Qt 惯例）、注释里引用的
   ASTRAN C++ 标识符、bestRecord-* 文件格式 token（受保护字面量）。
   `test_naming` 用 ~130 个 LEGACY 名字钉住不回流。
2. **大函数**：>80 行的函数必须拆分；重复块抽共享 helper（growth 的
   `_collect_neighbor_features` 已消掉两函数各 ~50 行重复与 4 层嵌套）。
3. **日志/dfx**：一律走 `core.log.getFlowLogger()`（级别过滤、时间戳、控制台
   输出），不再散落裸 print；GUI 事件仍经 PipelineHooks。
4. **多入参**：参数 ≥6 的函数改用配置对象/命名元组（如 FlowConfig）。

## 迁移原则

1. **行为不变**：每次迁移都先建立/复用回归网（等价测试、机制型单测），迁移后全绿；
2. **shim 兼容**：被拆模块保留原文件名作 re-export，gui/ 与既有测试零改动；
3. **单一事实来源**：函数物理移动（AST 提取），不留双份实现；
4. **新代码只进 core/**：旧模块只出不进。

## 已完成迁移（2026-10-10）

| 迁移 | 方式 | 验证 |
|---|---|---|
| main() 587 行 → core/pipeline.runPipeline | AST 逐字提取 + FlowConfig 参数化 | test_flow_parity（main≡flow_core）通过 |
| main.py → 薄 CLI | 重写（22 行） | 同上 |
| 可变全局 → FlowConfig | 新数据类，默认值=旧行为 | test_config（新增） |
| heuristicLabel...×2 → core/seeding | AST 逐字提取，blif_preproc shim | test_clustering/encoding/reuse 全绿 |
| grow_sequence_of_clusters(+_BasedOn) → core/growth | AST 逐字提取，blif_pattern_growth shim | test_pattern_growth/benefit 全绿 |

## 待迁移（按优先级）

1. ~~core/parse~~ ✅ 已迁（2026-10-10）：load_liberty_file/load_bool_gate_from_blif/
   gen_graph_from_liberty_and_blif + SPSubcircuit/load_spice_subcircuits（AST 逐字），
   blif_preproc 与 spice 变 shim（编排/GNN/导出留在 shim）；

2. ~~core/growth~~ ✅ 已迁（2026-10-10）；
3. ~~gui/flow_core 消费 core.pipeline~~ ✅ 已迁（2026-10-10）；
4. ~~core/evaluate + core/external 门面~~ ✅ 已迁（2026-10-10）：pipeline 改为
   经门面取依赖，测试钉住"同一对象绑定"（test_facades）；
5. ~~性能层~~ ✅ 已迁（2026-10-10）：CP-SAT 压缩后端默认化（GUROBI_CL_SOLVER
   默认 cpsat，缺 ortools 回退 CBC；证据 AUDIT 5.20/5.30）；宽度代理训练
   管线化（train→persist→load + stale 检查，pipeline 集成，test_width_proxy
   钉住 roundtrip 与"fresh 即复用"）。
