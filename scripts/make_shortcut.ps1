param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [string]$Destination = ([Environment]::GetFolderPath('Desktop'))
)
$ErrorActionPreference = 'Stop'
$ResolvedExe = (Resolve-Path $ExePath).Path
if ([System.IO.Path]::GetExtension($ResolvedExe) -ne '.exe') { throw 'Only an EXE can be used as the shortcut target.' }
if (-not (Test-Path -LiteralPath $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }
$ShortcutPath = Join-Path $Destination 'FileFlow Lite.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ResolvedExe
$Shortcut.WorkingDirectory = [System.IO.Path]::GetDirectoryName($ResolvedExe)
$Shortcut.IconLocation = "$ResolvedExe,0"
$Shortcut.Description = 'Safe folder flattening and sequential renaming'
$Shortcut.Save()
Write-Host "Shortcut: $ShortcutPath"
