$ErrorActionPreference = 'Stop'
Set-Location $PSScriptRoot
$manifest = Get-Content release-manifest.json -Raw | ConvertFrom-Json
$name = $manifest.python_bootstrap.name
if ([IO.Path]::GetFileName($name) -ne $name) { throw 'Nombre de archivo inesperado.' }
$stream = [IO.File]::OpenRead((Join-Path $PSScriptRoot $name))
$algorithm = [Security.Cryptography.SHA256]::Create()
try { $hash = [BitConverter]::ToString($algorithm.ComputeHash($stream)).Replace('-','').ToLowerInvariant() }
finally { $stream.Dispose(); $algorithm.Dispose() }
if ($hash -ne $manifest.python_bootstrap.sha256) { throw 'El Python de preparación no coincide con su huella.' }
$bootstrap = Join-Path $PSScriptRoot '.voz-bootstrap'
if (!(Test-Path $bootstrap)) {
    [void][Reflection.Assembly]::LoadWithPartialName('System.IO.Compression.FileSystem')
    [IO.Compression.ZipFile]::ExtractToDirectory((Join-Path $PSScriptRoot $name), $bootstrap)
}
$env:PYTHONDONTWRITEBYTECODE = '1'
& (Join-Path $bootstrap 'python.exe') -B (Join-Path $PSScriptRoot 'extract.py') $PSScriptRoot
if ($LASTEXITCODE -ne 0) { throw 'La preparación no se ha completado. Revisa los mensajes anteriores.' }
