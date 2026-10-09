# Vendored Yosys (Windows, mingw64)

MSYS2 package `mingw-w64-x86_64-yosys-0.51-2` extracted manually (the
MSYS2 pacman installation on the development machine is damaged and
yowasp-yosys cannot run `abc` -- wasm cannot spawn the external ABC
binary).  This build embeds ABC support and ships `yosys-abc.exe`, so
`abc -liberty` technology mapping works.

Usage: the flow's `yosys_import.findYosys()` probes this directory; the
binary needs `C:\msys64\mingw64\bin` on PATH for its DLLs, which the
flow already arranges when `Astran.py` is imported.

Source: https://mirrors.ustc.edu.cn/msys2/mingw/mingw64/
(mirrors.tuna.tsinghua.edu.cn as fallback); `.PKGINFO` preserved next
to this README.
