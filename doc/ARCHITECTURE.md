# 架构文档：分层模块化核心（core package）

> 目标（用户）：全面重新设计项目层次与架构，拆分大文件/大类，模块化层次化，
> 便于适配新用例、长期维护、衍生与性能提升；正确性由测试钉住，持续重构。

## 分层结构

```
pySrc/
  main.py            ← 薄 CLI：构建 FlowConfig → 调 runPipeline（原 587 行单体内联已抽离）
  core/              ← 新分层核心（本架构的主体）
    config.py        ← FlowConfig 数据类：全部可调参数集中（取代 globalVariables 可变全局
                       与 main.py 顶部魔法数）；from_env() 读环境变量
    pipeline.py      ← runPipeline(cfg)：完整挖掘流水线（AST 逐字从 main() 提取，
                       行为由等价测试对 GUI 移植版钉住）；含阶段一（贪心/束生长+版图+评估）
                       与阶段二（逐模式记录）
    encoding.py      ← 编码（canonicalPatternCode/extractAndEncodeSubgraph_Tree/
                       escapeOutputCount）
    seeding.py       ← 初始聚类（heuristicLabel.../..._BasedOn，AST 逐字提取，
                       BLIFPreProc 现为 re-export shim）
    graph.py         ← （规划）数据结构门面（BLIFGraphUtil）
    evaluate.py      ← （规划）评估层门面：电气/时序/可布性/复用/宽度代理/版图体检
    external.py      ← （规划）外部工具门面：ASTRAN / yosys / GDS
  BLIFPreProc.py     ← shim：seeding 已迁 core，其余解析暂留（下一步迁 core/parse）
  BLIFPatternGrowth.py ← 生长（下一步迁 core/growth）
  ...其余单职责模块（benefit/routability/electrical/timing_power/liberty_gen/
     reuse/width_proxy/layout_sanity/yosys_import/yosys_eval/pdk_config/...）
gui/flow_core.py     ← 待迁移：第三份控制流副本，下一步改为消费 core.pipeline
                      （等价测试 test_flow_parity 在迁移前后持续钉住一致性）
```

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
| heuristicLabel...×2 → core/seeding | AST 逐字提取，BLIFPreProc shim | test_clustering/encoding/reuse 全绿 |

## 待迁移（按优先级）

1. core/parse（liberty/BLIF/SPICE 解析从 BLIFPreProc/spice 拆出）；
2. core/growth（growASeqOfClusters 从 BLIFPatternGrowth 拆出，含 _BasedOn）；
3. core/evaluate + core/external 门面（把已单职责的小模块收编为一层）；
4. gui/flow_core 消费 core.pipeline（消灭第三份控制流副本）；
5. 性能层：CP-SAT 后端默认化、宽度代理训练管线化（见 RESEARCH_AND_OPTIMIZATION）。
