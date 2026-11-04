$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) {
    $python = Join-Path (Split-Path $root -Parent) 'VozEstudio-Completo\runtime\python.exe'
}
if (!(Test-Path -LiteralPath $python)) { throw 'Primero ejecuta Instalar.cmd para preparar Python y las bibliotecas.' }
if (Test-Path settings.local.json) {
    $settings = Get-Content settings.local.json -Raw | ConvertFrom-Json
    foreach ($property in $settings.PSObject.Properties) { [Environment]::SetEnvironmentVariable($property.Name,[string]$property.Value,'Process') }
}
& $python -B scripts\download_design_model.py
if ($LASTEXITCODE -ne 0) { throw 'La descarga no ha terminado. Vuelve a ejecutar Instalar-VoiceDesign.cmd.' }
