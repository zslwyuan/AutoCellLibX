# tools — 随仓库分发的工具

| 目录 | 内容 |
|---|---|
| astran/ | vendored ASTRAN（UFRGS，C++ 标准单元版图综合）+ build_astran.sh；`astran/build/bin/Astran.exe` 有 360 误报史，白名单见 AGENTS.md |
| gurobi_cl/ | LP 求解器 shim：默认 **CP-SAT**（ortools），缺失自动回退 CBC；compare_backends.py 对拍工具 |
| yosys/ | vendored mingw64 yosys 0.51（内嵌 abc，自包含 DLL），供 stat 交叉校验与 abc 重映射评估 |
