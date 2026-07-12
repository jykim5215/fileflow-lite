$ErrorActionPreference = 'Stop'
$Root = (Resolve-Path (Join-Path $PSScriptRoot '..')).Path
Set-Location $Root
$env:DOTNET_CLI_TELEMETRY_OPTOUT = '1'

$VsWhere = Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\Installer\vswhere.exe'
if (-not (Test-Path $VsWhere)) { throw 'Visual Studio Build Tools are required.' }
$MSBuild = & $VsWhere -latest -products * -requires Microsoft.Component.MSBuild -find 'MSBuild\**\Bin\MSBuild.exe' | Select-Object -First 1
if (-not $MSBuild) {
    $MSBuild = Get-ChildItem (Join-Path ${env:ProgramFiles(x86)} 'Microsoft Visual Studio\2022\*\MSBuild\Current\Bin\MSBuild.exe') -ErrorAction SilentlyContinue | Select-Object -First 1 -ExpandProperty FullName
}
if (-not $MSBuild) { throw 'MSBuild was not found.' }

$KitsBin = Join-Path ${env:ProgramFiles(x86)} 'Windows Kits\10\bin'
$SdkBin = Get-ChildItem $KitsBin -Directory | Sort-Object Name -Descending | Where-Object { Test-Path (Join-Path $_.FullName 'x64\makeappx.exe') } | Select-Object -First 1
if (-not $SdkBin) { throw 'Windows SDK packaging tools were not found.' }
$MakeAppx = Join-Path $SdkBin.FullName 'x64\makeappx.exe'
$SignTool = Join-Path $SdkBin.FullName 'x64\signtool.exe'

$Build = Join-Path $Root 'build-v2'
$Stage = Join-Path $Build 'package'
$Dist = Join-Path $Root 'dist-v2'
if (Test-Path $Build) { Remove-Item -LiteralPath $Build -Recurse -Force }
if (Test-Path $Dist) { Remove-Item -LiteralPath $Dist -Recurse -Force }
New-Item -ItemType Directory -Path $Stage,$Dist | Out-Null

$AssetPython = if (Test-Path '.venv\Scripts\python.exe') { '.\.venv\Scripts\python.exe' } else { 'python' }
& $AssetPython scripts\generate_icon.py
& $AssetPython scripts\generate_msix_assets.py

dotnet run --project native\FileFlow.Core.Tests\FileFlow.Core.Tests.csproj -c Release
if ($LASTEXITCODE -ne 0) { throw 'Core tests failed.' }
dotnet publish native\FileFlow.Worker\FileFlow.Worker.csproj -c Release -r win-x64 --self-contained true -p:PublishSingleFile=true -p:IncludeNativeLibrariesForSelfExtract=true -p:DebugType=None -o (Join-Path $Build 'worker')
if ($LASTEXITCODE -ne 0) { throw 'Worker publish failed.' }
& $MSBuild native\FileFlow.Shell\FileFlow.Shell.vcxproj /t:Build /p:Configuration=Release /p:Platform=x64 /m
if ($LASTEXITCODE -ne 0) { throw 'Shell extension build failed.' }

Copy-Item (Join-Path $Build 'worker\FileFlow.Worker.exe') $Stage
Copy-Item 'native\FileFlow.Shell\x64\Release\FileFlow.Shell.dll' $Stage
Copy-Item 'packaging\msix\AppxManifest.xml' $Stage
New-Item -ItemType Directory -Path (Join-Path $Stage 'Assets') | Out-Null
Copy-Item 'packaging\msix\Assets\*.png' (Join-Path $Stage 'Assets')

$Msix = Join-Path $Dist 'FileFlow-Lite-Explorer.msix'
& $MakeAppx pack /d $Stage /p $Msix /o
if ($LASTEXITCODE -ne 0) { throw 'MSIX packaging failed.' }

$Certificate = Get-ChildItem Cert:\CurrentUser\My | Where-Object { $_.Subject -eq 'CN=FileFlow Lite' -and $_.HasPrivateKey } | Sort-Object NotAfter -Descending | Select-Object -First 1
if (-not $Certificate) {
    $Certificate = New-SelfSignedCertificate -Type Custom -Subject 'CN=FileFlow Lite' -FriendlyName 'FileFlow Lite package signing' -CertStoreLocation 'Cert:\CurrentUser\My' -KeyUsage DigitalSignature -KeyAlgorithm RSA -KeyLength 3072 -HashAlgorithm SHA256 -NotAfter (Get-Date).AddYears(5) -TextExtension @('2.5.29.37={text}1.3.6.1.5.5.7.3.3','2.5.29.19={text}')
}
& $SignTool sign /fd SHA256 /sha1 $Certificate.Thumbprint /s My /tr 'http://timestamp.digicert.com' /td SHA256 $Msix
if ($LASTEXITCODE -ne 0) { throw 'MSIX signing failed.' }
Export-Certificate -Cert $Certificate -FilePath (Join-Path $Dist 'FileFlow-Lite.cer') -Force | Out-Null
Copy-Item 'packaging\msix\FileFlow-Lite.appinstaller','packaging\msix\Install-FileFlowLite.cmd','packaging\msix\Install-FileFlowLite.ps1','packaging\msix\Uninstall-FileFlowLite.ps1' $Dist
Copy-Item 'README.md','LICENSE' $Dist

$Zip = Join-Path $Dist 'FileFlow-Lite-Explorer-v0.2.0.zip'
Compress-Archive -Path (Join-Path $Dist '*') -DestinationPath $Zip -CompressionLevel Optimal -Force
$HashFiles = @($Msix, $Zip)
$HashLines = foreach ($File in $HashFiles) { '{0}  {1}' -f (Get-FileHash -Algorithm SHA256 $File).Hash.ToLowerInvariant(), [IO.Path]::GetFileName($File) }
[IO.File]::WriteAllLines((Join-Path $Dist 'SHA256SUMS.txt'), $HashLines, [Text.UTF8Encoding]::new($false))
Write-Host "Built $Msix"
