# Configura o menu de contexto do Windows (HKCU) para os CLIs do IA-Hub.
# Idempotente. Faz backup antes de alterar.
#
# Entradas gerenciadas:
#   ClaudeCLI   -> "Abrir com Claude Code CLI"  (--dangerously-skip-permissions)
#   OpenCode    -> "Abrir com OpenCode CLI"      (--auto)
#   AntigravityCLI -> mantido/atualizado se encontrado
#   AntigravityIDE e Antigravity (sem CLI) -> removidos se existirem
#
# Nao altera: VSCode, Visual Studio, Terminal nem nenhuma outra chave.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = New-Object System.Text.UTF8Encoding($false)

# ── Helpers ──────────────────────────────────────────────────────────────────

function Find-Exe([string[]]$Candidates, [string]$CommandName) {
    foreach ($c in $Candidates) {
        $expanded = [Environment]::ExpandEnvironmentVariables($c)
        if ($expanded -and (Test-Path $expanded)) { return $expanded }
    }
    if ($CommandName) {
        $cmd = Get-Command $CommandName -ErrorAction SilentlyContinue
        if ($cmd) { return $cmd.Source }
    }
    return $null
}

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Import-Reg([string]$Content) {
    $tmp = [System.IO.Path]::GetTempFileName() + '.reg'
    Write-Utf8NoBom $tmp $Content
    $p = Start-Process regedit.exe -ArgumentList "/s `"$tmp`"" -Wait -PassThru
    Remove-Item $tmp -Force -ErrorAction SilentlyContinue
    if ($p.ExitCode -ne 0) { throw "regedit falhou (exit $($p.ExitCode))" }
}

# Escapa barras para o formato .reg (cada \ vira \\)
function EscReg([string]$s) { $s.Replace('\', '\\') }

# Linha de entrada .reg: [secao], @="valor" e "Nome"="valor"
function RegSection([string]$key, [string]$default, [hashtable]$values) {
    $lines = "[${key}]"
    if ($default) { $lines += "`r`n@=`"$default`"" }
    foreach ($k in $values.Keys) { $lines += "`r`n`"$k`"=`"$($values[$k])`"" }
    return $lines
}

# ── Backup ────────────────────────────────────────────────────────────────────

$backupDir = Join-Path $env:LOCALAPPDATA 'IA-Hub\backups-registro'
New-Item -ItemType Directory -Force $backupDir | Out-Null
$ts = Get-Date -Format 'yyyyMMdd_HHmmss'
foreach ($suffix in @('Directory_shell', 'Background_shell')) {
    $key  = if ($suffix -eq 'Directory_shell') { 'HKCU\Software\Classes\Directory\shell' } else { 'HKCU\Software\Classes\Directory\Background\shell' }
    $file = Join-Path $backupDir "context-menu_${suffix}_${ts}.reg"
    reg export $key $file /y 2>$null | Out-Null
}

# ── Detectar CLIs ─────────────────────────────────────────────────────────────

$npm = $env:APPDATA + '\npm'

$claudeExe   = Find-Exe @("$npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
                           "$env:LOCALAPPDATA\AnthropicClaude\app\claude.exe") 'claude'

$opencodeExe = Find-Exe @("$npm\node_modules\opencode-ai\bin\opencode.exe",
                           "$env:LOCALAPPDATA\Programs\@opencode-aidesktop\opencode.exe") 'opencode'

$agyCliExe   = Find-Exe @("$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe",
                           "$env:LOCALAPPDATA\Programs\Antigravity CLI\Antigravity CLI.exe") 'agy'

# ── Remover entradas obsoletas ────────────────────────────────────────────────

foreach ($name in @('Antigravity', 'AntigravityIDE')) {
    foreach ($root in @('HKCU\Software\Classes\Directory\shell', 'HKCU\Software\Classes\Directory\Background\shell')) {
        try { reg delete "$root\$name" /f 2>&1 | Out-Null } catch { }
    }
}

# ── Montar bloco .reg ─────────────────────────────────────────────────────────

$NL  = "`r`n"
$reg = "Windows Registry Editor Version 5.00$NL"

# Claude Code CLI
if ($claudeExe) {
    $e    = EscReg $claudeExe
    $cmdV = "cmd.exe /s /k pushd \`"%V\`" \u0026\u0026 \`"$e\`" --dangerously-skip-permissions"
    $cmdW = "cmd.exe /s /k pushd \`"%W\`" \u0026\u0026 \`"$e\`" --dangerously-skip-permissions"
    $cmdV = 'cmd.exe /s /k pushd \"%V\" && \"' + $e + '\" --dangerously-skip-permissions'
    $cmdW = 'cmd.exe /s /k pushd \"%W\" && \"' + $e + '\" --dangerously-skip-permissions'
    $iconVal = $e

    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\ClaudeCLI' 'Abrir com Claude Code CLI' @{ Icon = $iconVal })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\ClaudeCLI\command' $cmdV @{})
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\ClaudeCLI' 'Abrir com Claude Code CLI' @{ Icon = $iconVal })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\ClaudeCLI\command' $cmdW @{})
}

# OpenCode CLI
if ($opencodeExe) {
    $e   = EscReg $opencodeExe
    $cmd = '\"' + $e + '\" --auto \"%V\"'

    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\OpenCode' 'Abrir com OpenCode CLI' @{ Icon = $e })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\OpenCode\command' $cmd @{})
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\OpenCode' 'Abrir com OpenCode CLI' @{ Icon = $e })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\OpenCode\command' $cmd @{})
}

# Antigravity CLI — mantido/atualizado se existir no PC
if ($agyCliExe) {
    $e   = EscReg $agyCliExe
    $cmd = '\"' + $e + '\" \"%V\"'

    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\AntigravityCLI' 'Abrir com Antigravity CLI' @{ Icon = $e })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\shell\AntigravityCLI\command' $cmd @{})
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\AntigravityCLI' 'Abrir com Antigravity CLI' @{ Icon = $e })
    $reg += $NL + (RegSection 'HKEY_CURRENT_USER\Software\Classes\Directory\Background\shell\AntigravityCLI\command' $cmd @{})
}

# ── Aplicar ───────────────────────────────────────────────────────────────────

Import-Reg $reg

# ── Trusted workspaces (Claude Code + AGY) ────────────────────────────────────

$H = $env:USERPROFILE
foreach ($sf in @("$H\.claude\settings.json", "$H\.gemini\antigravity-cli\settings.json")) {
    if (-not (Test-Path $sf)) { continue }
    try {
        $json = Get-Content $sf -Raw | ConvertFrom-Json
        $ht   = @{}
        $json.PSObject.Properties | ForEach-Object { $ht[$_.Name] = $_.Value }
        $existing = @($ht['trustedWorkspaces']) | Where-Object { $_ }
        $ht['trustedWorkspaces'] = @('C:\', 'D:\', 'E:\') + $existing | Select-Object -Unique
        Write-Utf8NoBom $sf ($ht | ConvertTo-Json -Depth 20)
    } catch {
        Write-Warning "context-menu.ps1: nao foi possivel atualizar trustedWorkspaces em $sf : $_"
    }
}

# ── Reiniciar Explorer ────────────────────────────────────────────────────────

try {
    Stop-Process -Name explorer -Force -ErrorAction SilentlyContinue
    Start-Sleep -Milliseconds 600
    Start-Process explorer
} catch { }

# ── Resultado para o install.ps1 ──────────────────────────────────────────────

return [ordered]@{
    ClaudeCLI  = if ($claudeExe)   { "configurado -> $claudeExe" }   else { 'nao encontrado - ignorado' }
    OpenCode   = if ($opencodeExe) { "configurado -> $opencodeExe" } else { 'nao encontrado - ignorado' }
    AgyCliExe  = if ($agyCliExe)   { "configurado -> $agyCliExe" }   else { 'nao encontrado - ignorado' }
    Obsoletos  = 'Antigravity e AntigravityIDE removidos (se existiam)'
    Backup     = $backupDir
}
