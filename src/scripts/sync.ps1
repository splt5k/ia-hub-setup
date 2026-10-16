# Gera as instruções globais de cada IA a partir de <hub>\regras.
# Roda no login (tarefa "IA-Hub Sync") e por sincronizar.cmd. Só escreve para as ferramentas instaladas.
$ErrorActionPreference = 'Stop'
$hub  = Split-Path $PSScriptRoot -Parent
$H    = $env:USERPROFILE
$utf8 = New-Object System.Text.UTF8Encoding($false)
$log  = Join-Path $PSScriptRoot 'sync.log'

function Log($m) { "$(Get-Date -Format s) $m" | Out-File $log -Append -Encoding utf8 }

function Ler($rel) { [IO.File]::ReadAllText((Join-Path $hub $rel), $utf8).Replace('{{HUB}}', $hub) }

function Gerar($destino, $especifico, [switch]$SomenteEspecifico) {
    $aviso = "<!-- GERADO por $hub\scripts\sync.ps1. Não edite aqui: edite $hub\regras. -->`n`n"
    # OpenCode é memory-only no diagrama: recebe só regras/opencode.md, sem o núcleo de roteamento.
    $conteudo = $aviso
    if (-not $SomenteEspecifico) { $conteudo += (Ler 'regras\nucleo.md') }
    if ($especifico) { $conteudo += $(if ($SomenteEspecifico) { '' } else { "`n" }) + (Ler $especifico) }
    [IO.File]::WriteAllText($destino, $conteudo, $utf8)
}

try {
    $feitos = @()
    if (Test-Path "$H\.claude") {
        Gerar "$H\.claude\CLAUDE.md" 'regras\claude.md'
        New-Item -ItemType Directory -Force "$H\.claude\agents" | Out-Null
        Copy-Item "$hub\claude\agents\*.md" "$H\.claude\agents\" -Force
        $feitos += 'claude'
    }
    if (Test-Path "$H\.codex")           { Gerar "$H\.codex\AGENTS.md"  'regras\codex.md';       $feitos += 'codex' }
    if (Test-Path "$H\.gemini")          { Gerar "$H\.gemini\GEMINI.md" 'regras\antigravity.md'; $feitos += 'antigravity' }
    if (Test-Path "$H\.config\opencode") { Gerar "$H\.config\opencode\ia-hub.md" 'regras\opencode.md' -SomenteEspecifico;         $feitos += 'opencode' }

    # Obsidian: garante o hub na lista de cofres (só com o app fechado, senão ele sobrescreve)
    $obsCfg = "$env:APPDATA\obsidian\obsidian.json"
    if ((Test-Path $obsCfg) -and -not (Get-Process Obsidian -ErrorAction SilentlyContinue)) {
        $j = Get-Content $obsCfg -Raw -Encoding UTF8 | ConvertFrom-Json
        if (-not $j.vaults) { $j | Add-Member vaults (New-Object psobject) -Force }
        if (-not ($j.vaults.PSObject.Properties | Where-Object { $_.Value.path -eq $hub })) {
            $id = -join ((1..16) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })
            $j.vaults | Add-Member -NotePropertyName $id -NotePropertyValue ([pscustomobject]@{ path = $hub; ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds(); open = $true })
            [IO.File]::WriteAllText($obsCfg, ($j | ConvertTo-Json -Depth 10 -Compress), $utf8)
            $feitos += 'obsidian'
        }
    }
    Log "OK ($($feitos -join ', '))"
} catch {
    Log "ERRO: $_"
    throw
}
