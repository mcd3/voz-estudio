param([switch]$CPU, [string]$ModelCache = '', [string]$WhisperCache = '')
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
if (!(Test-Path '.venv\Scripts\python.exe')) {
    $candidates = @((Join-Path $env:LOCALAPPDATA 'Programs\Python\Python312\python.exe'), 'python3.12', 'python')
    $selected = $null
    foreach ($candidate in $candidates) {
        if ((Test-Path -LiteralPath $candidate) -or (Get-Command $candidate -ErrorAction SilentlyContinue)) {
            $version = & $candidate -c 'import sys; print(f"{sys.version_info.major}.{sys.version_info.minor}")' 2>$null
            if ($version -eq '3.12') { $selected = $candidate; break }
        }
    }
    if (!$selected) { throw 'Instala Python 3.12 de 64 bits desde https://www.python.org/downloads/ y vuelve a ejecutar Instalar.cmd.' }
    & $selected -m venv .venv
    if ($LASTEXITCODE -ne 0) { throw 'No se ha podido crear el entorno Python.' }
}
$python = Join-Path $root '.venv\Scripts\python.exe'
& $python -m ensurepip --upgrade
if ($LASTEXITCODE -ne 0) { throw 'No se ha podido preparar pip en el entorno.' }
& $python -m pip install --upgrade pip
if ($LASTEXITCODE -ne 0) { throw 'No se ha podido preparar pip.' }
$index = 'https://download.pytorch.org/whl/cpu'
if (!$CPU -and (Get-Command nvidia-smi -ErrorAction SilentlyContinue)) { $index = 'https://download.pytorch.org/whl/cu128' }
& $python -m pip install 'torch==2.11.0' 'torchaudio==2.11.0' --index-url $index
if ($LASTEXITCODE -ne 0) { throw 'No se ha podido instalar PyTorch. Comprueba conexión y compatibilidad.' }
& $python -m pip install -e .
if ($LASTEXITCODE -ne 0) { throw 'No se han podido instalar las dependencias de Voz Estudio.' }
$settings = @{}
if (Test-Path 'settings.local.json') {
    $loaded = Get-Content 'settings.local.json' -Raw | ConvertFrom-Json
    foreach ($property in $loaded.PSObject.Properties) { $settings[$property.Name] = $property.Value }
}
if ($ModelCache) { $settings['VOZ_MODEL_CACHE'] = [IO.Path]::GetFullPath($ModelCache) }
if ($WhisperCache) { $settings['VOZ_WHISPER_CACHE'] = [IO.Path]::GetFullPath($WhisperCache) }
if ($CPU) { $settings['VOZ_DEVICE'] = 'cpu' }
$settings | ConvertTo-Json | Set-Content 'settings.local.json' -Encoding utf8
foreach ($key in $settings.Keys) { [Environment]::SetEnvironmentVariable($key, [string]$settings[$key], 'Process') }
& $python scripts\download_models.py
if ($LASTEXITCODE -ne 0) { throw 'La descarga de modelos no se ha completado. Vuelve a ejecutar Instalar.cmd.' }
Write-Host 'Instalación completada. Abre Iniciar.cmd para utilizar la aplicación.' -ForegroundColor Green
