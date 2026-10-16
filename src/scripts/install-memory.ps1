$ErrorActionPreference = 'Stop'
$hub = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $hub '.memory-runtime\Scripts\python.exe'
. (Join-Path $PSScriptRoot 'bootstrap.ps1')
Assert-HubServiceOwnership
$uv = Ensure-HubUv
Write-HubEvent 'runtime' 'running'
if (-not (Test-Path -LiteralPath $runtime)) {
    & $uv venv --python 3.11 (Join-Path $hub '.memory-runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o runtime de memória.' }
}
& $uv pip install --python $runtime -r (Join-Path $PSScriptRoot 'memory\requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências da memória.' }
Write-HubEvent 'runtime' 'done'
Write-HubEvent 'memory' 'running'
& $runtime (Join-Path $PSScriptRoot 'memory\entry.py') install
if ($LASTEXITCODE -ne 0) { throw 'Falha ao integrar a memória aos ambientes.' }
Write-HubEvent 'memory' 'done'
& (Join-Path $PSScriptRoot 'sync.ps1')
Write-Host 'Preparando e verificando a busca semantica (primeiro inicio baixa o modelo)...'
Write-HubEvent 'validate' 'running'
& $runtime (Join-Path $PSScriptRoot 'memory\entry.py') doctor
if ($LASTEXITCODE -ne 0) { throw 'Falha na verificacao da memoria; instalacao incompleta.' }
Write-HubEvent 'validate' 'done'
