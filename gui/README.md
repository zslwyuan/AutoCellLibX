# gui — PySide6 桌面前端

`flow_core.py` 的挖掘阶段已委托 `core.pipeline`（_GuiPipelineHooks 桥接事件/取消/布局器）；
`paths.py`/`artifacts.py`/`gds_model.py`/`flow_core.py` 为 Qt-free 核心（可单测），
`widgets/`、`tabs/` 为 Qt 层。页面导览与启动：见 gui/README 顶部 docstring 与仓库根 README。
运行：`python -m gui`。
