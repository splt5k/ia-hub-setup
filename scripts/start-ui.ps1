param([switch]$Preview)
$ErrorActionPreference = 'Stop'
$hub = Split-Path $PSScriptRoot -Parent
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
Write-Host 'Preparando a interface local do IA-Hub...'
$uv = Ensure-HubUv
$runtime = Join-Path $hub '.setup-runtime\Scripts\python.exe'
if (-not (Test-Path -LiteralPath $runtime)) {
    & $uv venv --python 3.11 (Join-Path $hub '.setup-runtime')
    if ($LASTEXITCODE) { throw 'Falha ao preparar o runtime da interface.' }
}
$arguments = @((Join-Path $hub 'scripts\setup_ui\server.py'), '--root', $hub)
if ($Preview) { $arguments += '--preview' }
& $runtime @arguments
if ($LASTEXITCODE) { throw 'A interface terminou com erro.' }
