# AutoCellLibX 工程化进展记录（Windows 原生环境）

> 更新时间：2026-09-24
> 目标：在裸 Windows 环境下载并跑通 zslwyuan/AutoCellLibX 全流程，
> 用开源求解器替换商业 Gurobi（不修改 AutoCellLibX 算法逻辑）。
>
> 注：本文是当时的工程日志，文中出现的 `D:\...` 绝对路径是**当时机器上的**
> 安装位置，仅作历史记录；现在的仓库已自包含（vendored ASTRAN 等），
> 路径以仓库相对路径为准（见 BUILDING.md）。

---

## 1. 已完成

### 1.1 代码下载
| 项目 | 来源 | 位置 |
|---|---|---|
| AutoCellLibX（zslwyuan 版） | Gitee（GitHub 直连不稳定；默认分支 `main`，35 提交） | `D:\AutoCellLibX` |
| ASTRAN（aziesemer master，2022-04） | GitHub codeload tar.gz（git 协议不通） | `D:\astran` |
| MSYS2（20260611） | 清华 TUNA 镜像（repo.msys2.org 慢） | `C:\msys64` |
| 已配置全局 git 身份 | — | Tingyuan LIANG / tliang@connect.ust.hk |

### 1.2 工具链（MSYS2 + MinGW，TUNA 镜像）
- gcc/g++ 16.2、make、pkgconf
- wxWidgets 3.2.11（msw 变体，wx-config 可用）
- ASTRAN 用 `g++ *.cpp $(wx-config --cppflags --libs) -std=c++14 -O3` **一次编译成功（0 错误）**
- wx 运行库 DLL 已复制到 `D:\astran\Astran\build\bin\`（wxbase32u_gcc_custom.dll、wxmsw32u_core_gcc_custom.dll）

### 1.3 Gurobi → 开源求解器（核心成果）
**发现**：ASTRAN 的 `compaction.cpp::solve()` 只是把约束写成 CPLEX LP 文件，
再调外部命令行求解器（原为 `gurobi_cl`，参数 `TimeLimit=.. ResultFile=..`），
随后解析 Gurobi 格式 .sol。求解器路径在运行时由 `set lpsolve "<path>"` 脚本命令指定——
**无需改 AutoCellLibX 算法**，替换求解器即可。

**替换方案**：`D:\aclx-tools\gurobi_cl.py`（python-mip + COIN-OR CBC 开源 MILP 求解器）
+ `gurobi_cl.cmd` 批处理入口。已实测：1065 变量/1436 约束的真实 ILP 模型，
0.22 秒求到最优。

**ASTRAN 代码补丁（`D:\astran\Astran\src\compaction.cpp`，共 3 处）**：
1. LP 写出前把"表达式型变量名"（如 `x0b + RELAXATION`、`b0_17_1 + b0_17_2 + b0_17_3`，
   Gurobi 宽容接受、CBC 拒绝）统一改名为 `astranVarNN`，.sol 读回时翻译回原名。
2. 目标函数重复项（y16min/y24min 出现两次）写前合并（求和系数）。
3. （包装脚本内）LP 文件缺 CPLEX `End` 关键字，补上后再求解（否则 CBC 段错误）。

### 1.4 AutoCellLibX 代码适配（`D:\AutoCellLibX\pySrc\`）
| 文件 | 改动 |
|---|---|
| `astran.py` | 求解器路径常量 `GUROBI_CL=D:/aclx-tools/gurobi_cl.cmd`；`cellgen autoflow nTrack`→`cellgen autoflow`（原命令多参数会被 ASTRAN 判为非法命令跳过）；PATH 前置 `C:\msys64\mingw64\bin`（wx DLL）；单次尝试 |
| `main.py` | `ASTRANBuildPath=D:/astran/Astran/build`；两处 gurobiPath→`GUROBI_CL`；technologyPath→`D:/astran/Astran/build/Work/tech_freePDK45.rul`；**benchmarks 临时改为 `["adder"]`（冒烟用，跑通后需恢复 5 个）** |
| `gds_analysis.py` | gdspy→gdstk（gdspy 在 Windows/py3.11 无 wheel） |
| `blif_preproc.py` | tensorflow→numpy（TF 在 Windows/py3.11 无 wheel；GNN 训练本就在主流程中被注释） |
| `blif_graph_util.py` | graphviz 布局失败回退 spring_layout（免装 pygraphviz） |

### 1.5 Python 依赖（系统 Python 3.11.9，TUNA PyPI 镜像）
`tqdm numpy networkx easydict blifparser liberty-parser gdstk matplotlib scikit-learn lark mip`
（原 requirements 缺 matplotlib/sklearn/lark/mip；tensorflow 与 gdspy 因无 Windows wheel 已被替换规避）

### 1.6 已验证
- ASTRAN `--shell` 模式可执行脚本（含 `exit` 才能退出）
- INVX1 完整 `cellgen autoflow`：CBC 求解 → `Cell Size (W x H): 0.6 x 2.6` → `INVX1.gds` 生成
- GDS 面积读取：GSCL45nm 32 单元 / Astran 日志 16 单元
- adder 基准：BLIF 解析、模式挖掘、初始聚类全部正常（710 门、61 个三门模式簇等）

### 1.7 全流程闭环（2026-09-24 16:20 达成）
- **ASTRAN 从源码重建成功**（360 误报清除后）：CodeBlocks 工程 `nbproject/Makefile-Release.mk`
  经 mingw32-make 编译，0 错误，产物 `build/bin/Astran`（5.1MB，无扩展名，正好匹配 `astran.py` 调用路径）。
  工具链路径问题用自定义 `D:\astran\Astran\bin\wx-config` shim 解决（见 §3）。
- **adder 冒烟全流程通过**（约 15 分钟），产物在 `pySrc/outputs/adder/`：
  - `COMPLEX0/1/9.{sp,gds,Astranlog,run,png}` + `GDSIILTable.txt`
  - `bestRecord-adder`：COMPLEX0（61簇×[NAND2X1,NAND2X1,OR2X1]）+ COMPLEX1（54簇×[XNOR2X1,XOR2X1,OAI21X1]）
    相对 ASTRAN 面积省 **9.53%**，相对 GSCL 面积省 **15.26%**
  - `bestRecord-seperateadder`：逐模式明细（最高单模式 COMPLEX0 省 6.61%）

---

## 2. ~~当前阻塞项~~（已解决）

~~**360 安全卫士误报**：2026-09-24 15:42 拦截并删除 `D:\astran\Astran\build\bin\Astran.exe`
（HEUR/QVM202.0.4759.Malware.Gen）。原因：MinGW 新编译的未签名二进制 +
ASTRAN 通过 `_popen` 执行脚本的行为特征触发启发式引擎。~~ **已通过重新编译 + 验证解决（§1.7）**。

遗留（未处理，可选）：
1. 在 360 中把 `D:\astran`、`D:\AutoCellLibX`、`D:\aclx-tools` 加入白名单/信任区
   （本机无 Windows Defender 模块，`Add-MpPreference` 不可用，只能靠 360 白名单）——
   新编译的二进制含同样 `_popen` 特征，**存在再次被清除的风险**。
2. 若再被清除：从 360 恢复区恢复，或按 §3 重建（对象文件在 `build/Release/...`，增量重编约 1 分钟）。

---

## 3. 恢复/复现命令

```bash
# 重建 ASTRAN（已验证：2026-09-24 16:20 产物运行正常）
# 需要自定义 wx-config shim（D:/astran/Astran/bin/wx-config，硬编码 msys64 wx 3.2 标志）
cd /d/astran/Astran
export PATH="/d/astran/Astran/bin:/c/msys64/mingw64/bin:$PATH"
mingw32-make -f nbproject/Makefile-Release.mk build/bin/Astran   # 产物 build/bin/Astran（无扩展名）

# 备选：MSYS2 MinGW 原生 shell 直编（需 wx-config 在 msys2 下正确解析 /mingw64）
MSYSTEM=MINGW64 /c/msys64/usr/bin/bash.exe -lc 'export PATH=/mingw64/bin:$PATH; \
  cd /d/astran/Astran/src && \
  g++ *.cpp $(wx-config --cppflags --libs) -std=c++14 -O3 -o ../build/bin/Astran.exe'

# 跑主流程（cwd = D:\AutoCellLibX\pySrc）
cd /d/AutoCellLibX/pySrc
C:/Users/Administrator/AppData/Local/Programs/Python/Python311/python.exe main.py
```

注意：
- 单次 ASTRAN 调用约 1 秒至数分钟（CBC 求解，模式越大越久），每个 benchmark 的模式迭代可能累计数分钟至小时
  （论文口径：每基准 ≤1.1 小时生成最多 5 个定制单元）。
- 冒烟已通过；跑全量前把 `main.py:32` 恢复为 5 个 EPFL 基准：
  `benchmarks = ["adder", "ctrl", "i2c", "multiplier", "router"]`
- BLIF 网表已在仓库内（Yosys 生成），Yosys 安装仅为可选验证，尚未完成。

---

## 4. 遗留事项
1. ~~360 白名单 + 重建 Astran.exe + 重跑 adder~~（已解决：重建成功、adder 闭环，见 §1.7；360 白名单仍未做，建议尽快添加）
2. 恢复 5 基准列表（`main.py` 当前仅 `["adder"]`），全量运行
3. Yosys Windows 二进制下载（可选，仓库 BLIF 已足够跑主流程）
4. 若需 GNN 训练模块（blif_gnn_training.py，主流程已注释），需在 WSL/Linux 装 tensorflow
5. 清理：`D:\msys2-installer.exe`（94MB）、`D:\astran.tar.gz`（6.1MB）可删
6. 详细项目文档见 `doc/PROJECT_ANALYSIS.md`（目录结构、模块解析、数据流、故障修复记录）
