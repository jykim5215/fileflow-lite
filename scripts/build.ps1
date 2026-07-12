param([switch]$SkipInstall)
$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
if (-not (Test-Path '.venv\Scripts\python.exe')) { python -m venv .venv }
$Python = Join-Path $Root '.venv\Scripts\python.exe'
if (-not $SkipInstall) {
    & $Python -m pip install --upgrade pip
    & $Python -m pip install "pyinstaller>=6.16" "pillow>=11.0"
}
& $Python scripts\generate_icon.py
$env:PYTHONPATH = 'src'
& $Python -m unittest discover -s tests -v
& $Python -m PyInstaller --noconfirm --clean --onefile --windowed --name FileFlow-Lite --icon assets\fileflow.ico --paths src src\fileflow_lite\__main__.py
Write-Host "Built: $Root\dist\FileFlow-Lite.exe"

