/* AutoCellLibX launcher.
 *
 * A tiny Win32 GUI stub: finds its own directory, prepends the bundled
 * runtime\python on PATH, chdirs to the app root and starts
 * runtime\pythonw.exe -m gui.  All paths are relative to the exe, so the
 * whole folder is portable.
 *
 * Built by make_stage.py (MinGW gcc via MSYS2 bash).  No CRT dependency
 * beyond Windows itself.
 */
#define WIN32_LEAN_AND_MEAN
#include <windows.h>
#include <tchar.h>

static void fail(const wchar_t *msg)
{
    MessageBoxW(NULL, msg, L"AutoCellLibX", MB_OK | MB_ICONERROR);
}

int WINAPI WinMain(HINSTANCE hInst, HINSTANCE hPrev, LPSTR lpCmd, int nShow)
{
    (void)hInst; (void)hPrev; (void)lpCmd; (void)nShow;

    wchar_t app[MAX_PATH], pyw[MAX_PATH], cmdline[MAX_PATH + 32];
    wchar_t *slash;
    DWORD len = GetModuleFileNameW(NULL, app, MAX_PATH);
    if (len == 0 || len >= MAX_PATH)
        return 1;
    slash = wcsrchr(app, L'\\');
    if (slash == NULL)
        return 1;
    *slash = L'\0';               /* app root = directory of this exe */

    wcscpy(pyw, app);
    wcscat(pyw, L"\\runtime\\pythonw.exe");
    if (GetFileAttributesW(pyw) == INVALID_FILE_ATTRIBUTES) {
        fail(L"找不到内置 Python 运行时（runtime\\pythonw.exe）。\n"
             L"请确认安装目录完整，或重新运行安装包。");
        return 1;
    }

    /* PATH = runtime; runtime\Scripts; %PATH%  (gurobi_cl.cmd calls "python") */
    wchar_t path[MAX_PATH * 2 + 16];
    wsprintfW(path, L"%s\\runtime;%s\\runtime\\Scripts;", app, app);
    DWORD old = GetEnvironmentVariableW(L"PATH", path + wcslen(path),
                                        MAX_PATH);
    if (old == 0 && GetLastError() != ERROR_SUCCESS) {
        /* keep just the runtime entries */
    }
    SetEnvironmentVariableW(L"PATH", path);
    SetCurrentDirectoryW(app);

    wsprintfW(cmdline, L"\"%s\" -m gui", pyw);
    STARTUPINFOW si;
    PROCESS_INFORMATION pi;
    ZeroMemory(&si, sizeof(si));
    si.cb = sizeof(si);
    ZeroMemory(&pi, sizeof(pi));
    if (!CreateProcessW(pyw, cmdline, NULL, NULL, FALSE,
                        CREATE_NEW_PROCESS_GROUP, NULL, app, &si, &pi)) {
        fail(L"无法启动 AutoCellLibX（CreateProcess 失败）。\n"
             L"可尝试用 AutoCellLibX-Console.cmd 查看错误输出。");
        return 1;
    }
    CloseHandle(pi.hThread);
    CloseHandle(pi.hProcess);
    return 0;
}
