param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [string]$Destination = ([Environment]::GetFolderPath('Desktop'))
)
$ErrorActionPreference = 'Stop'
$ResolvedExe = (Resolve-Path $ExePath).Path
if ([System.IO.Path]::GetExtension($ResolvedExe) -ne '.exe') { throw '실행 파일(.exe)만 바로가기로 만들 수 있습니다.' }
if (-not (Test-Path -LiteralPath $Destination)) { New-Item -ItemType Directory -Path $Destination -Force | Out-Null }
$ShortcutPath = Join-Path $Destination 'FileFlow Lite.lnk'
$Shell = New-Object -ComObject WScript.Shell
$Shortcut = $Shell.CreateShortcut($ShortcutPath)
$Shortcut.TargetPath = $ResolvedExe
$Shortcut.WorkingDirectory = [System.IO.Path]::GetDirectoryName($ResolvedExe)
$Shortcut.IconLocation = "$ResolvedExe,0"
$Shortcut.Description = '안전한 폴더 평탄화와 순번 이름짓기'
$Shortcut.Save()
Write-Host "Shortcut: $ShortcutPath"

