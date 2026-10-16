$ErrorActionPreference = 'Stop'
[Net.ServicePointManager]::SecurityProtocol = [Net.SecurityProtocolType]::Tls12
$app = Split-Path (Split-Path $PSScriptRoot -Parent) -Parent
$work = Split-Path $app -Parent
$env:UV_INSTALL_DIR = Join-Path $work 'uv'
$env:UV_PYTHON_INSTALL_DIR = Join-Path $work 'python'
$env:UV_CACHE_DIR = Join-Path $work 'cache'
$env:UV_PYTHON_PREFERENCE = 'only-managed'
$env:UV_NO_MODIFY_PATH = '1'
$download = Join-Path $work 'uv-install.ps1'
$env:TEMP = Join-Path $work 'tmp'
$env:TMP = $env:TEMP
New-Item -ItemType Directory -Force $env:TEMP | Out-Null
Write-Host 'Preparando o instalador temporario do IA-Hub...'
Invoke-WebRequest 'https://astral.sh/uv/0.11.24/install.ps1' -UseBasicParsing -OutFile $download
Import-Module Microsoft.PowerShell.Security -ErrorAction Stop
& $download
if (-not (Test-Path (Join-Path $env:UV_INSTALL_DIR 'uv.exe'))) { throw 'Falha ao preparar uv.' }
$uv = Join-Path $env:UV_INSTALL_DIR 'uv.exe'
$env:PATH = "$env:UV_INSTALL_DIR;$env:PATH"
$arguments = @()
if ($env:IA_HUB_PORTABLE_MODE) { $arguments += $env:IA_HUB_PORTABLE_MODE }
& $uv run --no-project --python 3.11 -- python (Join-Path $app 'scripts\portable\entry.py') @arguments
exit $LASTEXITCODE
