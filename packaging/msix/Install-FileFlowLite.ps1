$ErrorActionPreference = 'Stop'

$Identity = [Security.Principal.WindowsIdentity]::GetCurrent()
$Principal = [Security.Principal.WindowsPrincipal]::new($Identity)
$IsAdministrator = $Principal.IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
if (-not $IsAdministrator) {
    $Arguments = "-NoProfile -ExecutionPolicy Bypass -File `"$PSCommandPath`""
    $Process = Start-Process -FilePath 'powershell.exe' -ArgumentList $Arguments -Verb RunAs -Wait -PassThru
    exit $Process.ExitCode
}

$Here = Split-Path -Parent $MyInvocation.MyCommand.Path
$CertificatePath = Join-Path $Here 'FileFlow-Lite.cer'
$PackagePath = Join-Path $Here 'FileFlow-Lite-Explorer.msix'
$AppInstallerPath = Join-Path $Here 'FileFlow-Lite.appinstaller'
if (-not (Test-Path $CertificatePath) -or -not (Test-Path $PackagePath) -or -not (Test-Path $AppInstallerPath)) { throw 'Required install files are missing.' }
$Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
if ($Certificate.Subject -ne 'CN=FileFlow Lite') { throw 'Unexpected package certificate subject.' }
if ($Certificate.NotBefore -gt (Get-Date) -or $Certificate.NotAfter -lt (Get-Date)) { throw 'The package certificate is outside its validity period.' }
$Signature = Get-AuthenticodeSignature -FilePath $PackagePath
if (-not $Signature.SignerCertificate -or $Signature.SignerCertificate.Thumbprint -ne $Certificate.Thumbprint) { throw 'The MSIX signature does not match the included certificate.' }
Import-Certificate -FilePath $CertificatePath -CertStoreLocation 'Cert:\LocalMachine\TrustedPeople' | Out-Null
$TrustedSignature = Get-AuthenticodeSignature -FilePath $PackagePath
if ($TrustedSignature.Status -ne 'Valid') { throw "MSIX signature verification failed: $($TrustedSignature.StatusMessage)" }
$CurrentUserCertificate = Join-Path 'Cert:\CurrentUser\TrustedPeople' $Certificate.Thumbprint
if (Test-Path $CurrentUserCertificate) { Remove-Item -LiteralPath $CurrentUserCertificate -Force }
$LegacyKeys = @(
    'HKCU:\Software\Classes\Directory\shell\FileFlowLite.Flatten',
    'HKCU:\Software\Classes\Directory\shell\FileFlowLite.Rename',
    'HKCU:\Software\Classes\Directory\Background\shell\FileFlowLite.Rename'
)
foreach ($Key in $LegacyKeys) { if (Test-Path $Key) { Remove-Item -LiteralPath $Key -Recurse -Force } }
$LegacyShortcut = Join-Path ([Environment]::GetFolderPath('Desktop')) 'FileFlow Lite.lnk'
if (Test-Path $LegacyShortcut) { Remove-Item -LiteralPath $LegacyShortcut -Force }
try {
    Add-AppxPackage -Path $AppInstallerPath -AppInstallerFile -ForceTargetApplicationShutdown
} catch {
    Write-Warning 'Online App Installer setup was unavailable. Installing the local signed MSIX without automatic update registration.'
    Add-AppxPackage -Path $PackagePath -ForceUpdateFromAnyVersion
}
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Process explorer.exe
Write-Host 'FileFlow Lite is installed in the Windows 11 File Explorer context menu.'
