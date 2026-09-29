# Create the Desktop and Start Menu shortcuts for the installed app.
# Runs from %LOCALAPPDATA%\AutoCellLibX (see setup.cmd).  ASCII only.
$dest = Join-Path $env:LOCALAPPDATA "AutoCellLibX"
$target = Join-Path $dest "AutoCellLibX.exe"
$ws = New-Object -ComObject WScript.Shell
foreach ($dir in @([Environment]::GetFolderPath('Desktop'),
                   [Environment]::GetFolderPath('Programs'))) {
    $lnk = $ws.CreateShortcut((Join-Path $dir 'AutoCellLibX.lnk'))
    $lnk.TargetPath = $target
    $lnk.WorkingDirectory = $dest
    $lnk.IconLocation = "$target,0"
    $lnk.Description = "AutoCellLibX - Standard-Cell Extension Workbench"
    $lnk.Save()
}
