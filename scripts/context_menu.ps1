param(
    [Parameter(Mandatory=$true)][string]$ExePath,
    [switch]$Unregister
)
$ErrorActionPreference = 'Stop'
$Base = 'HKCU:\Software\Classes'
$FlattenLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('RmlsZUZsb3cgTGl0ZeuhnCDsnbQg7Y+0642UIO2Pie2DhO2ZlA=='))
$RenameLabel = [Text.Encoding]::UTF8.GetString([Convert]::FromBase64String('RmlsZUZsb3cgTGl0ZSDsiJzrsogg7J2066aE7KeT6riw'))
$Keys = @(
    @{ Path = "$Base\Directory\shell\FileFlowLite.Flatten"; Label = $FlattenLabel; Args = '--flatten "%1"' },
    @{ Path = "$Base\Directory\shell\FileFlowLite.Rename"; Label = $RenameLabel; Args = '--rename-folder "%1"' },
    @{ Path = "$Base\Directory\Background\shell\FileFlowLite.Rename"; Label = $RenameLabel; Args = '--rename-folder "%V"' }
)
if ($Unregister) {
    foreach ($entry in $Keys) {
        if (Test-Path -LiteralPath $entry.Path) { Remove-Item -LiteralPath $entry.Path -Recurse -Force }
    }
    Write-Host 'FileFlow Lite context menus removed.'
    exit 0
}
$ResolvedExe = (Resolve-Path $ExePath).Path
foreach ($entry in $Keys) {
    New-Item -Path $entry.Path -Force | Out-Null
    Set-Item -Path $entry.Path -Value $entry.Label
    New-ItemProperty -Path $entry.Path -Name 'Icon' -Value $ResolvedExe -PropertyType String -Force | Out-Null
    $commandPath = Join-Path $entry.Path 'command'
    New-Item -Path $commandPath -Force | Out-Null
    Set-Item -Path $commandPath -Value ('"{0}" {1}' -f $ResolvedExe, $entry.Args)
}
Write-Host 'FileFlow Lite context menus registered for the current user.'
