/* AutoCellLibX self-extracting installer stub.
 *
 * The distribution is this exe plus the payload ZIP.  The archive is looked
 * up first as a sibling "<exe name>.dat" file, then as data appended to the
 * exe itself (single-file mode).  At run time the stub:
 *   1. opens the archive, locates its central directory,
 *   2. extracts every entry (stored or deflate) into %TEMP%\AutoCellLibX_setup_<pid>
 *      while showing a progress dialog,
 *   3. runs setup.cmd from the extraction directory and waits for it,
 *   4. deletes the temporary extraction directory.
 *
 * The sibling-.dat layout exists because 360 Total Security's real-time
 * protection quarantines an exe with an appended archive (bundle heuristic)
 * but leaves a plain stub + data file alone.
 *
 * Built by tools/package/make_installer.py with MinGW (static CRT + static
 * zlib), so the produced exe has no external DLL dependencies.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <commctrl.h>
#include <shellapi.h>
#include <shlobj.h>
#include <zlib.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include <wchar.h>
#include <stdarg.h>

#define EOCD_SIG   0x06054b50u
#define CD_SIG     0x02014b50u
#define LOCAL_SIG  0x04034b50u

static FILE *g_dbg;   /* ACLX_DEBUG=1 -> %TEMP%\aclx_setup_debug.log */

static void dbg(const wchar_t *fmt, ...)
{
    if (!g_dbg)
        return;
    va_list ap;
    va_start(ap, fmt);
    vfwprintf(g_dbg, fmt, ap);
    fwprintf(g_dbg, L"\n");
    fflush(g_dbg);
    va_end(ap);
}

typedef struct {
    unsigned short method, namelen, extralen;
    unsigned int csize, usize, lhoffset;
    wchar_t *name;
} Entry;

static const wchar_t *g_err;
static HWND g_wnd, g_bar, g_label;
static unsigned __int64 g_total_bytes, g_done_bytes;

static void die(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, L"AutoCellLibX 安装", MB_OK | MB_ICONERROR);
    ExitProcess(1);
}

/* ------------------------------------------------------------- zip parsing */

static unsigned int rd16(const unsigned char *p) { return p[0] | (p[1] << 8); }
static unsigned int rd32(const unsigned char *p)
{
    return (unsigned int)p[0] | ((unsigned int)p[1] << 8) |
           ((unsigned int)p[2] << 16) | ((unsigned int)p[3] << 24);
}

static void get_temp_dir(wchar_t *buf, size_t n)
{
    /* Robust against POSIX-style TEMP (/tmp) inherited from shells: always
       resolve a real Windows temp path via the shell folder API. */
    if (SHGetFolderPathW(NULL, CSIDL_LOCAL_APPDATA | CSIDL_FLAG_CREATE, NULL,
                         SHGFP_TYPE_CURRENT, buf) == S_OK) {
        wcscat(buf, L"\\Temp");
        CreateDirectoryW(buf, NULL);
        return;
    }
    wcscpy(buf, L".");
}

static void delete_tree(const wchar_t *dir)
{
    /* Recursive delete without SHFileOperationW (whose FO_DELETE silently
       no-ops here under some shells). */
    wchar_t pattern[4096];
    swprintf(pattern, 4096, L"%ls\\*", dir);
    WIN32_FIND_DATAW fd;
    HANDLE h = FindFirstFileW(pattern, &fd);
    if (h == INVALID_HANDLE_VALUE)
        return;
    do {
        if (wcscmp(fd.cFileName, L".") == 0 || wcscmp(fd.cFileName, L"..") == 0)
            continue;
        wchar_t full[4096];
        swprintf(full, 4096, L"%ls\\%ls", dir, fd.cFileName);
        if (fd.dwFileAttributes & FILE_ATTRIBUTE_DIRECTORY)
            delete_tree(full);
        SetFileAttributesW(full, FILE_ATTRIBUTE_NORMAL);
        DeleteFileW(full);
    } while (FindNextFileW(h, &fd));
    FindClose(h);
    RemoveDirectoryW(dir);
}

static HANDLE g_fh;

static void read_at(HANDLE fh, unsigned __int64 off, void *buf, DWORD n)
{
    LARGE_INTEGER li;
    DWORD got = 0;
    li.QuadPart = (LONGLONG)off;
    SetFilePointerEx(fh, li, NULL, FILE_BEGIN);
    if (!ReadFile(fh, buf, n, &got, NULL) || got != n)
        die(L"安装包文件读取失败（文件可能已损坏）。");
}

/* Scan the last 64 KB for the End Of Central Directory record. */
static void find_eocd(unsigned __int64 *cd_offset, unsigned *n_entries)
{
    LARGE_INTEGER size;
    GetFileSizeEx(g_fh, &size);
    if (size.QuadPart < 22)
        die(L"安装包文件损坏（无 ZIP 目录）。");
    unsigned int tail = (size.QuadPart > 65557) ? 65557
                                                : (unsigned int)size.QuadPart;
    unsigned char *buf = (unsigned char *)malloc(tail);
    read_at(g_fh, size.QuadPart - tail, buf, tail);
    unsigned int i;
    for (i = tail - 22; i != 0xFFFFFFFFu; i--) {
        if (rd32(buf + i) == EOCD_SIG) {
            *n_entries = rd16(buf + i + 10);
            *cd_offset = (unsigned __int64)rd32(buf + i + 16);
            free(buf);
            return;
        }
    }
    free(buf);
    die(L"安装包文件损坏（找不到 ZIP 目录）。");
}

static Entry *read_central_dir(unsigned __int64 cd_offset, unsigned n)
{
    Entry *entries = (Entry *)calloc(n, sizeof(Entry));
    unsigned char hdr[46];
    unsigned __int64 pos = cd_offset;
    unsigned i;
    for (i = 0; i < n; i++) {
        read_at(g_fh, pos, hdr, 46);
        if (rd32(hdr) != CD_SIG)
            die(L"安装包文件损坏（中央目录解析失败）。");
        Entry *e = &entries[i];
        e->method   = rd16(hdr + 10);
        e->csize    = rd32(hdr + 20);
        e->usize    = rd32(hdr + 24);
        e->namelen  = rd16(hdr + 28);
        e->extralen = rd16(hdr + 30);
        e->lhoffset = rd32(hdr + 42);
        unsigned char *nb = (unsigned char *)malloc(e->namelen + 1);
        read_at(g_fh, pos + 46, nb, e->namelen);
        nb[e->namelen] = 0;
        int wlen = MultiByteToWideChar(CP_UTF8, 0, (const char *)nb,
                                       e->namelen, NULL, 0);
        e->name = (wchar_t *)calloc(wlen + 1, sizeof(wchar_t));
        MultiByteToWideChar(CP_UTF8, 0, (const char *)nb, e->namelen,
                            e->name, wlen);
        free(nb);
        pos += 46 + e->namelen + e->extralen +
               rd16(hdr + 32) + rd16(hdr + 34);
    }
    return entries;
}

static void extract_one(const Entry *e, const wchar_t *dest)
{
    unsigned char lh[30];
    read_at(g_fh, e->lhoffset, lh, 30);
    if (rd32(lh) != LOCAL_SIG)
        die(L"安装包文件损坏（本地头解析失败）。");
    unsigned int name_len = rd16(lh + 26), extra_len = rd16(lh + 28);
    unsigned __int64 data_off = e->lhoffset + 30 + name_len + extra_len;

    wchar_t full[4096];
    swprintf(full, 4096, L"%ls\\%ls", dest, e->name);

    /* create parent directories */
    wchar_t tmp[4096];
    wcscpy(tmp, full);
    for (wchar_t *p = tmp; *p; p++) {
        if (*p == L'/') {
            *p = L'\0';
            CreateDirectoryW(tmp, NULL);
            *p = L'/';
        }
    }

    unsigned char *cbuf = (unsigned char *)malloc(e->csize ? e->csize : 1);
    read_at(g_fh, data_off, cbuf, e->csize);

    unsigned char *ubuf = NULL;
    if (e->method == 8) {
        ubuf = (unsigned char *)malloc(e->usize ? e->usize : 1);
        z_stream zs;
        memset(&zs, 0, sizeof(zs));
        if (inflateInit2(&zs, -MAX_WBITS) != Z_OK)
            die(L"解压初始化失败。");
        zs.next_in = cbuf;
        zs.avail_in = e->csize;
        zs.next_out = ubuf;
        zs.avail_out = e->usize;
        int rc = inflate(&zs, Z_FINISH);
        if (rc != Z_STREAM_END && rc != Z_OK)
            die(L"解压失败（安装包可能已损坏）。");
        inflateEnd(&zs);
    } else if (e->method == 0) {
        ubuf = cbuf;
    } else {
        die(L"不支持的压缩方式。");
    }

    HANDLE out = CreateFileW(full, GENERIC_WRITE, 0, NULL, CREATE_ALWAYS,
                             FILE_ATTRIBUTE_NORMAL, NULL);
    if (out == INVALID_HANDLE_VALUE) {
        wchar_t emsg[2048];
        swprintf(emsg, 2048,
                 L"无法写入临时目录（%TEMP% 不可写？）。\n\n路径：%ls\n错误码：%lu",
                 full, GetLastError());
        die(emsg);
    }
    dbg(L"wrote %ls (%u bytes)", full, e->usize);
    DWORD written = 0;
    WriteFile(out, ubuf, e->usize, &written, NULL);
    CloseHandle(out);

    g_done_bytes += e->usize;
    if (g_bar) {
        SendMessageW(g_bar, PBM_SETPOS,
                     (WPARAM)(g_total_bytes
                              ? (int)(g_done_bytes * 100 / g_total_bytes)
                              : 0), 0);
    }
    free(cbuf);
    if (e->method == 8)
        free(ubuf);
}

/* ------------------------------------------------------------- progress UI */

static LRESULT CALLBACK wnd_proc(HWND h, UINT m, WPARAM w, LPARAM l)
{
    if (m == WM_DESTROY) {
        PostQuitMessage(0);
        return 0;
    }
    return DefWindowProcW(h, m, w, l);
}

static void run_progress_ui(void)
{
    WNDCLASSW wc;
    memset(&wc, 0, sizeof(wc));
    wc.lpfnWndProc = wnd_proc;
    wc.hInstance = GetModuleHandleW(NULL);
    wc.lpszClassName = L"ACLXSetupWnd";
    wc.hCursor = LoadCursorW(NULL, (LPCWSTR)IDC_APPSTARTING);
    RegisterClassW(&wc);

    HINSTANCE hInst = wc.hInstance;
    int w = 440, h = 120;
    g_wnd = CreateWindowExW(0, L"ACLXSetupWnd",
                            L"AutoCellLibX 安装",
                            WS_OVERLAPPED | WS_CAPTION | WS_SYSMENU |
                            WS_MINIMIZEBOX,
                            CW_USEDEFAULT, CW_USEDEFAULT, w, h,
                            NULL, NULL, hInst, NULL);
    g_label = CreateWindowExW(0, L"STATIC",
                              L"正在解压安装文件，请稍候…",
                              WS_CHILD | WS_VISIBLE | SS_LEFT,
                              16, 14, w - 32, 20,
                              g_wnd, NULL, hInst, NULL);
    g_bar = CreateWindowExW(0, PROGRESS_CLASSW, L"",
                            WS_CHILD | WS_VISIBLE | PBS_SMOOTH,
                            16, 48, w - 32, 22,
                            g_wnd, NULL, hInst, NULL);
    SendMessageW(g_bar, PBM_SETRANGE32, 0, 100);
    ShowWindow(g_wnd, SW_SHOWNORMAL);
    UpdateWindow(g_wnd);
}

static void pump_messages(void)
{
    MSG msg;
    while (PeekMessageW(&msg, NULL, 0, 0, PM_REMOVE)) {
        TranslateMessage(&msg);
        DispatchMessageW(&msg);
    }
}

/* ------------------------------------------------------------------- main */

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow)
{
    (void)hInst; (void)hPrev; (void)lpCmd; (void)nShow;

    INITCOMMONCONTROLSEX icc;
    icc.dwSize = sizeof(icc);
    icc.dwICC = ICC_PROGRESS_CLASS;
    InitCommonControlsEx(&icc);

    wchar_t self[MAX_PATH];
    DWORD len = GetModuleFileNameW(NULL, self, MAX_PATH);
    if (len == 0 || len >= MAX_PATH)
        return 1;

    /* archive = sibling "<self>.dat" if present, else the exe itself */
    wchar_t archive[MAX_PATH];
    wcscpy(archive, self);
    wchar_t *dot = wcsrchr(archive, L'.');
    if (dot != NULL && wcslen(dot) == 4)   /* ".exe" */
        wcscpy(dot, L".dat");
    {
        const wchar_t *dbg_path = _wgetenv(L"ACLX_DEBUG");
        if (dbg_path && *dbg_path) {
            wchar_t dp[1024], tdir[1024];
            get_temp_dir(tdir, 1024);
            swprintf(dp, 1024, L"%ls\\aclx_setup_debug.log", tdir);
            g_dbg = _wfopen(dp, L"w");
            if (g_dbg)
                fwprintf(g_dbg, L"stub start; self=%ls\n", self);
        }
    }
    g_fh = CreateFileW(archive, GENERIC_READ, FILE_SHARE_READ, NULL,
                       OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    if (g_fh == INVALID_HANDLE_VALUE) {
        dbg(L"sibling not openable (%lu), falling back to self", GetLastError());
        wcscpy(archive, self);
        g_fh = CreateFileW(archive, GENERIC_READ, FILE_SHARE_READ, NULL,
                           OPEN_EXISTING, FILE_ATTRIBUTE_NORMAL, NULL);
    }
    dbg(L"archive=%ls (fh=%p)", archive, (void *)g_fh);
    if (g_fh == INVALID_HANDLE_VALUE)
        die(L"无法打开安装数据文件：<安装包名>.dat 应与此程序放在同一目录。");

    unsigned __int64 cd_offset;
    unsigned n_entries;
    find_eocd(&cd_offset, &n_entries);
    Entry *entries = read_central_dir(cd_offset, n_entries);

    unsigned i;
    for (i = 0; i < n_entries; i++)
        g_total_bytes += entries[i].usize;

    wchar_t temp[MAX_PATH];
    get_temp_dir(temp, MAX_PATH);
    wsprintfW(temp + wcslen(temp), L"\\AutoCellLibX_setup_%lu",
              GetCurrentProcessId());
    CreateDirectoryW(temp, NULL);
    dbg(L"temp dir: %ls (last err=%lu)", temp, GetLastError());

    run_progress_ui();
    for (i = 0; i < n_entries; i++) {
        if (g_wnd)
            pump_messages();
        dbg(L"extracting %ls (method=%u csize=%u usize=%u)",
            entries[i].name, entries[i].method, entries[i].csize,
            entries[i].usize);
        extract_one(&entries[i], temp);
    }
    dbg(L"extraction done: %I64u/%I64u bytes", g_done_bytes, g_total_bytes);
    if (g_wnd) {
        ShowWindow(g_wnd, SW_HIDE);
        pump_messages();
        DestroyWindow(g_wnd);
    }

    /* run setup.cmd from the extraction dir */
    wchar_t setup[MAX_PATH];
    wsprintfW(setup, L"%s\\setup.cmd", temp);
    if (GetFileAttributesW(setup) == INVALID_FILE_ATTRIBUTES)
        die(L"安装包内容不完整（缺少 setup.cmd）。");
    wchar_t cmdline[MAX_PATH + 16];
    wsprintfW(cmdline, L"cmd.exe /c \"%s\"", setup);
    dbg(L"running: %ls (cwd=%ls)", cmdline, temp);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(NULL, cmdline, NULL, NULL, FALSE, 0, NULL, temp,
                        &si, &pi))
        die(L"无法启动安装脚本 setup.cmd。");
    CloseHandle(pi.hThread);
    WaitForSingleObject(pi.hProcess, INFINITE);
    CloseHandle(pi.hProcess);

    CloseHandle(g_fh);

    /* clean up the extraction dir */
    delete_tree(temp);
    dbg(L"cleanup done: %ls", temp);

    for (i = 0; i < n_entries; i++)
        free(entries[i].name);
    free(entries);
    return 0;
}
