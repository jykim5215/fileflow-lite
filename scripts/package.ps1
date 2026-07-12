$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
$Package = Join-Path $Root 'dist-package'
$Exe = Join-Path $Root 'dist\FileFlow-Lite.exe'
if (-not (Test-Path $Exe)) { throw '먼저 scripts\build.ps1을 실행하세요.' }
$resolvedPackage = (Resolve-Path $Package).Path
if (-not $resolvedPackage.StartsWith($Root, [System.StringComparison]::OrdinalIgnoreCase)) { throw '패키지 경로가 프로젝트 밖입니다.' }
Get-ChildItem -LiteralPath $Package -Force | Where-Object { $_.Name -ne '.gitkeep' } | Remove-Item -Recurse -Force
$portable = Join-Path $Package 'portable'
New-Item -ItemType Directory -Path $portable -Force | Out-Null
Copy-Item -LiteralPath $Exe -Destination (Join-Path $portable 'FileFlow-Lite.exe')
Copy-Item -LiteralPath (Join-Path $Root 'README.md') -Destination $portable
Copy-Item -LiteralPath (Join-Path $Root 'LICENSE') -Destination $portable
$Zip = Join-Path $Package 'FileFlow-Lite-portable.zip'
Compress-Archive -Path (Join-Path $portable '*') -DestinationPath $Zip -CompressionLevel Optimal -Force
Copy-Item -LiteralPath $Exe -Destination (Join-Path $Package 'FileFlow-Lite.exe')
$assets = @((Join-Path $Package 'FileFlow-Lite.exe'), $Zip)
$lines = foreach ($asset in $assets) {
    $hash = (Get-FileHash -Algorithm SHA256 -LiteralPath $asset).Hash.ToLowerInvariant()
    "$hash  $([System.IO.Path]::GetFileName($asset))"
}
[System.IO.File]::WriteAllLines((Join-Path $Package 'SHA256SUMS.txt'), $lines, [System.Text.UTF8Encoding]::new($false))
Remove-Item -LiteralPath $portable -Recurse -Force
Write-Host "Packaged: $Package"

