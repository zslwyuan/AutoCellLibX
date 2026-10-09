# tools/gurobi_cl — 求解器适配层

gurobi_cl.py 自解析 ASTRAN 的 LP（不变量 3），默认后端 CP-SAT（GUROBI_CL_SOLVER 可
切 cbc；ortools 缺失自动回退）；失败写全零 .sol → ASTRAN 0×0 单元（§5.5）。
cpsat_backend.py：CP-SAT 后端（自适应缩放，整数模型 scale=1）；
compare_backends.py：双后端对拍。证据：AUDIT §5.20。
