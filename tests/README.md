# tests — 测试分层

- tests/unit/：机制型单测（不钉绝对数值，钉行为契约）；`python -m pytest`（慢测试
  默认不选，`-m slow` 需 vendored ASTRAN）。
- 关键网：test_flow_parity（CLI≡GUI 等价）、test_facades（门面对象同一性）、
  test_gds_quality（repair pass 0 违例）、真实 yosys/abc 用例（无工具自跳过）。
- 约定：cwd=flow 的路径型测试用 `in_flow` fixture。
