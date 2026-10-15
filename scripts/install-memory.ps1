$ErrorActionPreference = 'Stop'
$hub = Split-Path $PSScriptRoot -Parent
$runtime = Join-Path $hub '.memory-runtime\Scripts\python.exe'
if (-not (Get-Command uv -ErrorAction SilentlyContinue)) {
    throw 'O instalador da memória requer uv no PATH para criar um runtime Python isolado.'
}
if (-not (Test-Path -LiteralPath $runtime)) {
    & uv venv --python 3.11 (Join-Path $hub '.memory-runtime')
    if ($LASTEXITCODE -ne 0) { throw 'Falha ao criar o runtime de memória.' }
}
& uv pip install --python $runtime -r (Join-Path $PSScriptRoot 'memory\requirements.lock')
if ($LASTEXITCODE -ne 0) { throw 'Falha ao instalar dependências da memória.' }
& $runtime (Join-Path $PSScriptRoot 'memory\entry.py') install
if ($LASTEXITCODE -ne 0) { throw 'Falha ao integrar a memória aos ambientes.' }
& (Join-Path $PSScriptRoot 'sync.ps1')
