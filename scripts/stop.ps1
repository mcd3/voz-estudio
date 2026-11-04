$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (!(Test-Path data\server.json)) { Write-Host 'No hay un servidor registrado.'; exit }
$saved = Get-Content data\server.json -Raw | ConvertFrom-Json
$process = Get-CimInstance Win32_Process -Filter "ProcessId = $($saved.pid)" -ErrorAction SilentlyContinue
if ($saved.instance -and $process -and $process.CommandLine -like '*-m voz_estudio*' -and $process.CommandLine -like "*--instance $($saved.instance)*") {
    $children = Get-CimInstance Win32_Process -Filter "ParentProcessId = $($process.ProcessId)" -ErrorAction SilentlyContinue
    foreach ($child in $children) {
        if ($child.CommandLine -like '*-m voz_estudio.design_worker*') { Stop-Process -Id $child.ProcessId -ErrorAction SilentlyContinue }
    }
    Stop-Process -Id $process.ProcessId
    Write-Host 'Voz Estudio detenido. Los datos se conservan en data.'
} else { Write-Host 'No se ha encontrado el proceso de Voz Estudio. No se ha detenido ningún otro programa.' }
