# pySrc — 流程核心

分层结构见 `core/`（八层：config/parse/encoding/seeding/growth/evaluate/external/pipeline/log）。
`main.py` 是 22 行薄 CLI；`BLIFPreProc.py`/`BLIFPatternGrowth.py`/`spice.py` 为兼容 shim。
运行：`cd pySrc && python main.py`；测试：仓库根 `python -m pytest`（见 tests/README.md）。
