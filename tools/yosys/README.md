# tools/yosys — vendored mingw64 Yosys 0.51（内嵌 abc）

MSYS2 pacman 损坏 + yowasp 无法派生 abc 的替代方案（AUDIT §5.24）：USTC 镜像解包，
补齐 DLL 传递依赖后自包含。yosys_import.findYosys 优先探测本目录。
