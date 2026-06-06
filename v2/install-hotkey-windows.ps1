param(
    [string]$Hotkey = "CTRL+ALT+V",
    [string]$ShortcutName = "Echo-Node Voice Assistant"
)

$ErrorActionPreference = "Stop"
$Root = Split-Path -Parent $MyInvocation.MyCommand.Path
$ShortcutPath = Join-Path ([Environment]::GetFolderPath("Desktop")) "$ShortcutName.lnk"
$Python = Join-Path $Root ".venv\Scripts\python.exe"
$Script = Join-Path $Root "assistant_v2.py"

if (-not (Test-Path $Python)) {
    throw "Missing Windows venv Python. Run .\install-windows.ps1 first."
}

$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = "powershell.exe"
$Shortcut.Arguments = "-NoExit -ExecutionPolicy Bypass -Command `"cd '$Root'; & '$Python' '$Script'`""
$Shortcut.WorkingDirectory = $Root
$Shortcut.Hotkey = $Hotkey
$Shortcut.Description = "Launch Echo-Node Voice Assistant"
$Shortcut.Save()

Write-Host "Installed Windows shortcut hotkey:"
Write-Host "  $Hotkey -> $ShortcutPath"
