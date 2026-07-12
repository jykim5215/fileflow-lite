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
Get-AppxPackage -Name 'FileFlowLite.Explorer' | Remove-AppxPackage
if (Test-Path $CertificatePath) {
    $Certificate = New-Object System.Security.Cryptography.X509Certificates.X509Certificate2($CertificatePath)
    if ($Certificate.Subject -ne 'CN=FileFlow Lite') { throw 'Unexpected package certificate subject.' }
    foreach ($Store in @('Cert:\LocalMachine\TrustedPeople', 'Cert:\CurrentUser\TrustedPeople')) {
        $InstalledCertificate = Join-Path $Store $Certificate.Thumbprint
        if (Test-Path $InstalledCertificate) { Remove-Item -LiteralPath $InstalledCertificate -Force }
    }
}
Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
Start-Sleep -Seconds 1
Start-Process explorer.exe
Write-Host 'FileFlow Lite was removed.'
