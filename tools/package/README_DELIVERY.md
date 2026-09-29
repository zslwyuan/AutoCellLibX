# AutoCellLibX · 标准单元扩展工作台 — 交付说明

感谢使用 AutoCellLibX。本工具从您的网表（BLIF）中自动挖掘**反复出现的
子电路（模式）**，把每个模式合并成一个新的“复杂标准单元”，并用
ASTRAN 自动生成晶体管级版图 —— 从而减小设计的整体面积。

本安装包是**自包含**的：内置完整的 Python 运行时、ASTRAN 版图合成器、
LP 求解器和 GSCL45 工艺数据，安装后**无需联网、无需安装任何其他软件**
即可完整运行。

---

## 一、系统要求

| 项目 | 要求 |
|---|---|
| 操作系统 | Windows 10 / 11，64 位（x64） |
| 内存 | 建议 8 GB 以上（大型网表分析时更高） |
| 磁盘 | 安装后约 1.5 GB 可用空间 |
| 权限 | 无需管理员权限（按用户安装到 `%LOCALAPPDATA%`） |

## 二、安装

1. 双击 `AutoCellLibX-Setup.exe`，等待自动解压（有进度条）。
2. 安装脚本自动把程序复制到 `%LOCALAPPDATA%\AutoCellLibX`，
   并在**桌面**和**开始菜单**创建 `AutoCellLibX` 快捷方式。
3. 安装完成后可选择立即启动。

> 卸载：运行安装目录下的 `uninstall.cmd`（或直接删除
> `%LOCALAPPDATA%\AutoCellLibX` 与两个快捷方式）。

## 三、首次运行

1. 双击桌面 `AutoCellLibX` 快捷方式（或安装目录下的 `AutoCellLibX.exe`）。
2. 打开**「总览」**页，检查环境检查表是否全绿：
   - `ASTRAN binary`、`python-mip`、`gurobi_cl wrapper` 必须为绿色；
   - `ASTRAN baseline cells generated` 为黄色是正常的（首次运行流程时
     会自动生成缺失的基线单元）。
3. 若 `ASTRAN binary` 变红，见下文**「四、360 安全软件误报」**。

## 四、360 安全软件误报（重要）

ASTRAN 版图合成器（`tools\astran\build\bin\Astran.exe`）会被 360 Total
Security 误判为病毒（`HEUR/QVM…Malware.Gen`）并**隔离**，导致版图运行
失败，报错“无法启动 ASTRAN 二进制”。这是**误报**（ASTRAN 是 UFRGS 的
开源标准单元版图合成器，本安装包原样内置）。

处理步骤：

1. 打开 360 安全卫士 → **木马查杀** → **信任区**；
2. 把安装目录下的 `tools\astran\build\bin\` 整个文件夹加入信任区
   （或直接添加 `Astran.exe`）；
3. 恢复被隔离的文件（若已被隔离）；
4. 重新启动 AutoCellLibX，环境检查恢复绿色。

> 若公司使用其他杀毒软件（卡巴、火绒等），遇到同样提示时按同样方式
> 添加信任即可。ASTRAN 为开源软件，可自行核对源码。

## 五、运行一次完整流程（示例）

1. **「配置」**页：基准选择 `adder`（自带演示网表，约 20K）；
2. **「运行」**页：点击「开始」，观察阶段列表与 ASTRAN 单元面板；
   流程会依次执行：解析 → 基线单元 → 聚类 → 模式挖掘 → 复杂单元版图
   → 逐模式明细 → 写结果；
3. 完成后到**「结果」**页查看面积节省报告（并排 vs 合并、每模式节省、
   设计级节省与原始记录文件）；
4. **「版图」**页可交互查看每个复杂单元的 GDS 版图（缩放、图层开关、
   测量、导出 PNG）。

内置演示基准：`adder`、`ctrl`、`max`、`multiplier` 等 22 个中小规模网表。
也可以随时在配置页「📄 添加 BLIF 文件…」导入您自己的网表。

## 六、目录结构

```
AutoCellLibX\
├── AutoCellLibX.exe          启动器（桌面快捷方式指向它）
├── AutoCellLibX-Console.cmd  控制台启动（排障用，显示全部日志）
├── runtime\                  内置 Python 3.11 运行时（裁剪版）
├── pySrc\                    流程核心：解析/挖掘/生长/SPICE/GDS 分析
│   ├── outputs\<基准>\       运行结果：COMPLEX*.sp/.gds/.Astranlog、
│   │                         bestRecord-*（附带的演示结果）
│   ├── originalAstranStdCells\   ASTRAN 基线单元缓存
│   └── originalGSCL45StdCells\   GSCL45 原始库单元数据
├── stdCelllib\               GSCL45 工艺数据（.lib/.lef/.sp/图层映射）
├── benchmark\blif\           演示网表（BLIF）
├── tools\astran\build\       ASTRAN 版图合成器 + 工艺规则
├── tools\gurobi_cl\          LP 求解器封装（python-mip + CBC）
└── doc\                      算法设计文档与工程记录
```

## 七、常见问题

- **流程很慢 / 卡在“ASTRAN 基线单元”？** 首次运行时需要为设计中每种
  标准单元生成一个参照版图（每个约 5–10 分钟），只生成一次，之后缓存
  复用。复杂单元版图同理。
- **日志出现 “no usable LP solution” / 某单元 0×0？** 该模式的版图
  合成在求解器无解/超时时宽度记为 0，流程会**自动排除**该模式并继续；
  最终的节省数字不包含它。
- **“large design” 警告？** 超过 8 MB 的网表在桌面交互中可能很慢，
  建议只运行中小规模网表；大网表请用命令行版本。
- **想恢复出厂演示结果？** 删除 `pySrc\outputs\` 下对应目录后重新运行。

## 八、数字口径（务必阅读）

- 面积用**宽度（µm）**作为代理：所有单元行高固定（默认 2.47 µm，
  GSCL45 CoreSite），故 面积 ∝ 宽度。
- 所有对比（ASTRAN 基线 vs 复杂单元）都在**同一行高、同一工艺参数**
  下进行；跨工具版本的数字不可直接比较。
- “节省”= 原始单元并排宽度和 − 合并后宽度，乘以出现次数。
- 本工具不修改您的原始网表与库文件，所有产物都写入
  `pySrc\outputs\<基准>\`。

## 九、许可与合规（请阅读）

安装包根目录随附以下许可文件：

| 文件 | 内容 |
|---|---|
| `LICENSE` | AutoCellLibX 项目许可：非商业使用遵循 Apache License 2.0；**商业使用须联系项目作者授权**（Wei ZHANG, eeweiz@ust.hk；Tingyuan LIANG, tliang@connect.ust.hk） |
| `NOTICE` | 版权声明与第三方归属摘要 |
| `THIRD_PARTY_NOTICES.md` | 全部第三方组件的来源与许可清单（ASTRAN、GSCL45/FreePDK45 数据、基准网表、内置 Python 依赖） |
| `tools\astran\LICENSE.md` | ASTRAN（UFRGS）的来源与许可状况说明 |

特别说明：

1. **ASTRAN**（版图合成器，UFRGS 开源项目，上游 github.com/aziesemer/astran）
   的源码中**没有附带许可文本**——本安装包如实记录其来源与版权头，
   不代替其作者授予任何权利。学术/研究用途按上游惯例；
   **商业用途请先联系 ASTRAN 作者确认**（与 AutoCellLibX 自身的
   商业授权条款一致）。
2. 内置 Python 运行时中的每个包均保留其自带许可文本
   （`runtime\Lib\site-packages\*.dist-info\licenses\`）。
   其中 `liberty-parser` 为 GPL-3.0-or-later，是唯一的强 copyleft 依赖，
   按原样随包分发，详见 `THIRD_PARTY_NOTICES.md` 第 5 节。
3. 本工具不含任何闭源第三方二进制（ASTRAN 为开源项目，CBC 求解器为
   COIN-OR 开源项目）。

---

AutoCellLibX · 标准单元扩展工作台 · 内置 ASTRAN（UFRGS，开源）与
COIN-OR CBC 求解器。更多技术细节见安装目录 `doc\` 下的设计文档。
