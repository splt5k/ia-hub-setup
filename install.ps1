# Instala clientes ausentes, dependências e memória compartilhada neste PC.
# Uso (depois do git clone, em qualquer pasta):
#   powershell -ExecutionPolicy Bypass -File <pasta-do-hub>\install.ps1
# Pode rodar de novo sem problema (idempotente). Faz backup antes de alterar.
$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)
$hub   = $PSScriptRoot
$H     = $env:USERPROFILE
$utf8  = New-Object System.Text.UTF8Encoding($false)
$bk    = Join-Path $hub ("_backup\{0}-{1}" -f $env:COMPUTERNAME, (Get-Date -Format 'yyyy-MM-dd_HHmm'))
$res   = [ordered]@{}
. "$hub\scripts\bootstrap.ps1"
Assert-HubServiceOwnership
Write-HubEvent 'clients' 'running'
$components = @(Invoke-HubBootstrap)
Write-HubEvent 'clients' 'done'
Write-HubEvent 'config' 'running'
foreach ($component in $components) { $res[$component.name] = "$($component.state): $($component.detail)" }

function Backup($p) {
    if (-not (Test-Path $p)) { return }
    $rel = $p.Replace($H, 'HOME').Replace($env:APPDATA, 'APPDATA') -replace ':', ''
    $d = Join-Path $bk $rel
    New-Item -ItemType Directory -Force (Split-Path $d) | Out-Null
    Copy-Item $p $d -Recurse -Force
}
function Tem($dirs, $cmd) {
    foreach ($d in $dirs) { if (Test-Path $d) { return $true } }
    return [bool]($cmd -and (Get-Command $cmd -ErrorAction SilentlyContinue))
}
function Gravar($p, $txt) { New-Item -ItemType Directory -Force (Split-Path $p) | Out-Null; [IO.File]::WriteAllText($p, $txt, $utf8) }

# ---------- Claude Code ----------
if (Tem @("$H\.claude", "$env:LOCALAPPDATA\AnthropicClaude", "$env:APPDATA\Claude") 'claude') {
    $f = "$H\.claude\settings.json"
    Backup $f; Backup "$H\.claude\CLAUDE.md"; Backup "$H\.claude\agents"
    $s = if (Test-Path $f) { Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json } else { New-Object psobject }
    $padrao = [ordered]@{ language = 'portugues brasil'; model = 'sonnet'; autoCompactEnabled = $true }
    foreach ($k in $padrao.Keys) { $s | Add-Member -NotePropertyName $k -NotePropertyValue $padrao[$k] -Force }
    Gravar $f ($s | ConvertTo-Json -Depth 20)
    $res['Claude Code'] = 'configurado (Sonnet, auto-compact, subagentes)'
} else { $res['Claude Code'] = 'não instalado - ignorado' }

# ---------- Codex (ChatGPT) ----------
if (Tem @("$H\.codex", "$env:LOCALAPPDATA\OpenAI\Codex") 'codex') {
    $f = "$H\.codex\config.toml"
    Backup $f; Backup "$H\.codex\AGENTS.md"
    $t = if (Test-Path $f) { [IO.File]::ReadAllText($f, $utf8) } else { '' }
    # altera só as chaves do topo (antes da primeira [tabela])
    $i = [regex]::Match($t, '(?m)^\[').Index; if ($i -eq 0 -and $t -notmatch '^\[') { $i = $t.Length }
    $topo = $t.Substring(0, $i); $resto = $t.Substring($i)
    foreach ($kv in @(@('model', 'gpt-6.1-sol'), @('model_reasoning_effort', 'medium'))) {
        $linha = "$($kv[0]) = `"$($kv[1])`""
        if ($topo -match "(?m)^$($kv[0])\s*=") { $topo = $topo -replace "(?m)^$($kv[0])\s*=.*$", $linha }
        else { $topo = "$linha`n" + $topo }
    }
    $t = $topo + $resto
    if ($t -notmatch '\[profiles\.rapido\]') {
        $t = $t.TrimEnd() + "`n`n[profiles.rapido]`nmodel = `"gpt-6.1-sol`"`nmodel_reasoning_effort = `"low`"`n`n[profiles.pesado]`nmodel = `"gpt-6-astra`"`nmodel_reasoning_effort = `"high`"`n"
    }
    Gravar $f $t
    $res['Codex'] = 'configurado (gpt-6.1-sol médio, perfis rapido/pesado)'
} else { $res['Codex'] = 'não instalado - ignorado' }

# ---------- Antigravity / Gemini ----------
if (Tem @("$H\.gemini", "$env:LOCALAPPDATA\Programs\Antigravity") 'agy') {
    New-Item -ItemType Directory -Force "$H\.gemini" | Out-Null
    Backup "$H\.gemini\GEMINI.md"; Backup "$H\.gemini\config\rules"
    $res['Antigravity'] = 'configurado (GEMINI.md do hub, regras existentes preservadas)'
} else { $res['Antigravity'] = 'não instalado - ignorado' }

# ---------- OpenCode ----------
if (Tem @("$H\.config\opencode") 'opencode') {
    $o = "$H\.config\opencode"
    Backup "$o\opencode.jsonc"; Backup "$o\AGENTS.md"; Backup "$o\agents"
    New-Item -ItemType Directory -Force "$o\agents" | Out-Null
    Copy-Item "$hub\opencode\agents\*.md" "$o\agents\" -Force
    Copy-Item "$hub\opencode\AGENTS.md" "$o\AGENTS.md" -Force
    $cfg = [IO.File]::ReadAllText("$hub\opencode\opencode.jsonc", $utf8)
    $inst = ("$o\ia-hub.md").Replace('\', '/')
    $cfg = [regex]::Replace($cfg, '"instructions"\s*:\s*\[[^\]]*\]', "`"instructions`": [`"$inst`"]")
    if (-not (Test-Path "$o\opencode.jsonc") -and -not (Test-Path "$o\opencode.json")) { Gravar "$o\opencode.jsonc" $cfg }
    $res['OpenCode'] = 'configurado (orquestrador + 8 subagentes, regras do hub)'
} else { $res['OpenCode'] = 'não instalado - ignorado' }

# ---------- Obsidian ----------
$obsExe = "$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe"
if (-not (Test-Path $obsExe)) { $obsExe = "$env:ProgramFiles\Obsidian\Obsidian.exe" }
if (Test-Path $obsExe) {
    $f = "$env:APPDATA\obsidian\obsidian.json"
    $j = if (Test-Path $f) { Get-Content $f -Raw -Encoding UTF8 | ConvertFrom-Json } else { [pscustomobject]@{ vaults = New-Object psobject } }
    if (-not $j.vaults) { $j | Add-Member vaults (New-Object psobject) -Force }
    $existe = $j.vaults.PSObject.Properties | Where-Object { $_.Value.path -eq $hub }
    if (-not $existe) {
        $j.vaults | Add-Member -NotePropertyName (-join ((1..16) | ForEach-Object { '{0:x}' -f (Get-Random -Maximum 16) })) -NotePropertyValue ([pscustomobject]@{ path = $hub; ts = [DateTimeOffset]::Now.ToUnixTimeMilliseconds(); open = $true })
        Gravar $f ($j | ConvertTo-Json -Depth 10)
    }
    # Obsidian 1.14+ ignora cofres registrados por fora: o atalho do Iniciar abre o hub direto via obsidian://
    $lnk = "$env:APPDATA\Microsoft\Windows\Start Menu\Programs\Obsidian.lnk"
    $sh = New-Object -ComObject WScript.Shell
    if (-not (Test-Path $lnk)) { $s = $sh.CreateShortcut($lnk); $s.TargetPath = $obsExe; $s.Save() }
    Backup $lnk
    $s = $sh.CreateShortcut($lnk); $s.Arguments = '"obsidian://open?path=' + [uri]::EscapeDataString($hub) + '"'; $s.Save()
    $res['Obsidian'] = "atalho do Iniciar abre sempre o hub ($hub)"
} else { $res['Obsidian'] = 'não instalado - o hub funciona sem ele' }

# ---------- Contexto local (perfil e notas de projeto; nunca vai para o git) ----------
New-Item -ItemType Directory -Force "$hub\contexto\projetos" | Out-Null
if (-not (Test-Path "$hub\contexto\perfil.md")) { Copy-Item "$hub\modelos\perfil.md" "$hub\contexto\perfil.md" }
Copy-Item "$hub\modelos\projeto.md" "$hub\contexto\projetos\_modelo.md" -Force
$res['Contexto local'] = "$hub\contexto (preencha perfil.md se quiser)"
# ---------- Tarefa agendada: no login ----------
$a  = New-ScheduledTaskAction -Execute 'powershell.exe' -Argument "-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File `"$hub\scripts\sync.ps1`""
$t1 = New-ScheduledTaskTrigger -AtLogOn -User "$env:USERDOMAIN\$env:USERNAME"
$st = New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable -MultipleInstances IgnoreNew
Register-ScheduledTask -TaskName 'IA-Hub Sync' -Action $a -Trigger $t1 -Settings $st -Description "Sincroniza regras de IA a partir de $hub" -Force | Out-Null
$res['Tarefa agendada'] = 'IA-Hub Sync (a cada login)'

# ---------- Primeira sincronização ----------
& "$hub\scripts\sync.ps1"
$res['Sync'] = (Get-Content "$hub\scripts\sync.log" -Tail 1)
Write-HubEvent 'config' 'done'
& "$hub\scripts\install-memory.ps1"
$res['Memória compartilhada'] = 'serviço local, MCPs, captura, busca semântica e tarefa no login'

Write-Host "`nConfiguracao do IA-Hub em $hub`n"
$res.GetEnumerator() | ForEach-Object { Write-Host ("  {0,-16} {1}" -f $_.Key, $_.Value) }
if (Test-Path $bk) { Write-Host "`n  Backup: $bk" }
Write-Host "`n  ChatGPT (app/web): cole o texto de chatgpt\instrucoes-personalizadas.md em Configurações > Personalização."
Write-Host '  Entre nas contas dos aplicativos e reabra as sessoes existentes. Logins e captura em apps graficos nao foram validados pelo instalador.'
$failed = @($components | Where-Object state -eq 'failed')
if ($failed.Count) { throw "Instalacao parcial: $($failed.name -join ', '). Veja contexto\bootstrap.json e execute instalar.cmd novamente." }
Write-Host '  Instalacao e verificacao da memoria concluidas. Relatorios: contexto\bootstrap.json e contexto\.memory\doctor.json.'
