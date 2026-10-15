# tools/gurobi_cl — 求解器适配层

gurobi_cl.py 自解析 ASTRAN 的 LP（不变量 3），默认后端 CP-SAT（GUROBI_CL_SOLVER 可
切 cbc；ortools 缺失自动回退）；失败写全零 .sol → ASTRAN 0×0 单元（§5.5）。
cpsat_backend.py：CP-SAT 后端（自适应缩放，整数模型 scale=1）；
compare_backends.py：双后端对拍。证据：AUDIT §5.20。

## 两种模型来源（STAGE 1：JSON 模型路径）

默认行为不变（LP 文本路径）。设置环境变量 `ASTRAN_MODEL_DUMP=<path>` 后，若该路径
存在可用的 JSON 模型（`meta.format_version == 1`，且不比 LP 文件旧——旧 JSON 是上一
次 solve 的残留，防止遮蔽新模型），gurobi_cl.py 改走 JSON 路径：

- `model_json.py`：JSON schema 加载校验 + python-mip 建模 + 求解入口。求解策略与
  legacy 完全一致：2% mip gap、`GUROBI_CL_TIME_LIMIT`（默认 300 s）第一阶段、
  FEASIBLE 算成功、*已证明的* INFEASIBLE 才按 `b<A>_<B>_<option=3>_<uid>` 名字模式
  剔除 option-3 间距析取项重解一次。`.sol` 名字保真（ASTRAN 按名回读）。
  注意：JSON 路径目前只支持 CBC；`GUROBI_CL_SOLVER=cpsat` 在该路径下会提示并回退 CBC。
- `lp_to_json.py`：把现有 `ILPmodel.lp` 转成同一 JSON schema（复用 gurobi_cl 的
  `_parse_terms`/`_read_cplex_lp`，保证语义一致）——在 C++ 侧钩子编译进来之前，
  用它对 JSON 路径做端到端验证与 A==B 对拍。
- `tools/astran/src/modeldump.{h,cpp}`：ASTRAN 内的转码器，在 Compaction::solve
  写完 LP 后把它转成同一 JSON（需要 compaction.cpp 的一行调用 + Makefile 加两个
  目标文件；未设 `ASTRAN_MODEL_DUMP` 时零行为变化）。

JSON 保真契约（两个生产者共同遵守，见 `model_json.py` 模块注释）：表达式列以重命名后的
`astranExprN` 普通变量出现，其 `CexprN` 定义约束作为普通约束保留（绝不折叠）；inf 系数
项在源头丢弃（"无界"，绝不夹成 big-M）；约束名逐字保留；变量按 legacy 建模器的建列
顺序排列（Generals、Binary、Semi、目标项扫描、约束项扫描）。
