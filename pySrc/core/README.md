# core — 分层核心包

| 模块 | 层 | 职责 |
|---|---|---|
| config.py | 参数 | FlowConfig 数据类（from_env 读环境变量） |
| parse.py | 读取 | liberty/BLIF/SPICE 解析（load_liberty_file 等规范名，见命名约定） |
| encoding.py | 编码 | canonical_pattern_code / 树编码 / escape_output_count |
| seeding.py | 聚类 | 初始聚类（heuristic_label…_based_on，含单输出种子过滤） |
| growth.py | 生长 | grow_sequence_of_clusters（预估剪枝/内化偏置/_collect_neighbor_features） |
| evaluate.py | 评估门面 | 电气/时序/可布性/复用/宽度代理/体检/表征/PDK |
| external.py | 工具门面 | ASTRAN / GDSIIAnalysis / yosys |
| pipeline.py | 编排 | run_pipeline(cfg, hooks)——CLI 与 GUI 唯一控制流 |
| log.py | dfx | get_flow_logger（级别过滤/时间戳/控制台） |

命名：新代码 snake_case（规范名）；历史 camelCase 作为兼容别名保留（见模块尾部别名块）。
