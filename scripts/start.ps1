param([int]$Port = 3010, [switch]$NoBrowser)
$ErrorActionPreference = 'Stop'
$root = Split-Path $PSScriptRoot -Parent
Set-Location $root
$python = Join-Path $root '.venv\Scripts\python.exe'
if (!(Test-Path -LiteralPath $python)) { throw 'Primero ejecuta Instalar.cmd.' }
if (Test-Path 'settings.local.json') {
    $settings = Get-Content 'settings.local.json' -Raw | ConvertFrom-Json
    foreach ($property in $settings.PSObject.Properties) { [Environment]::SetEnvironmentVariable($property.Name, [string]$property.Value, 'Process') }
}
$env:PYTHONUTF8 = '1'
$env:PYTHONUNBUFFERED = '1'
New-Item -ItemType Directory -Force data\logs | Out-Null
$url = "http://127.0.0.1:$Port"
$running = $false
try { $status = Invoke-RestMethod "$url/api/status" -TimeoutSec 2; $running = ($status.app -eq 'voz-estudio') } catch { }
if (!$running) {
    $instance = [guid]::NewGuid().ToString('N')
    $process = Start-Process -FilePath $python -ArgumentList '-m','voz_estudio','--port',"$Port",'--instance',$instance -WorkingDirectory $root -WindowStyle Hidden -RedirectStandardOutput data\logs\server.log -RedirectStandardError data\logs\server-error.log -PassThru
    for ($attempt=0; $attempt -lt 25; $attempt++) {
        try { $status = Invoke-RestMethod "$url/api/status" -TimeoutSec 1; if ($status.app -eq 'voz-estudio') { $running=$true; break } } catch { }
        Start-Sleep -Milliseconds 500
    }
}
if (!$running) { throw 'No se ha podido iniciar Voz Estudio. Consulta data\logs\server-error.log o utiliza otro puerto.' }
@{pid=$status.pid; port=$Port; instance=$status.instance} | ConvertTo-Json | Set-Content data\server.json -Encoding utf8
Write-Host "Voz Estudio: $url"
if (!$NoBrowser) { Start-Process $url }
