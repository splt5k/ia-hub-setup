# Configura o menu de contexto do Windows (HKCU) para os CLIs do IA-Hub.
# Idempotente: remove as entradas gerenciadas e recria só as ferramentas encontradas.
#
# Entradas gerenciadas (ver $Tools): Antigravity CLI, Claude Code CLI, Codex CLI, OpenCode CLI.
# Onde aparecem (ver $Targets): pastas, fundo de pasta, unidades e arquivos (abre a pasta do arquivo).
# Antigravity e AntigravityIDE (versões antigas) são removidos se existirem.
#
# Nao altera: VSCode, Visual Studio, Terminal nem nenhuma outra chave.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# =====================================================================
#  CONFIGURAÇÃO
#  Para adicionar/remover uma ferramenta, basta editar a lista $Tools.
#  O Explorer ordena os itens pelo nome da chave (Key), por isso
#  AntigravityCLI -> ClaudeCLI -> CodexCLI -> OpenCodeCLI aparecem nessa ordem.
# =====================================================================

$IconCacheDir  = Join-Path $env:LOCALAPPDATA 'IA-Hub\icons'
$IconOverrides = Join-Path $PSScriptRoot 'icons'   # icons\<Key>.ico ao lado do script tem prioridade
$FallbackIcon  = "$env:SystemRoot\System32\cmd.exe,0"

$Tools = @(
    @{
        Key       = 'AntigravityCLI'
        Label     = 'Abrir com Antigravity CLI'
        Title     = 'Antigravity CLI'
        Commands  = @('agy')
        Paths     = @(
            "$env:LOCALAPPDATA\agy\bin\agy.exe",
            "$env:LOCALAPPDATA\Programs\Antigravity CLI\agy.exe"
        )
        Args      = '--dangerously-skip-permissions'
        IconFiles = @(
            "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe",
            "$env:ProgramFiles\Antigravity\Antigravity.exe",
            "$env:LOCALAPPDATA\agy\antigravity.ico"
        )
        Appx      = @('*Antigravity*')
    },
    @{
        Key       = 'ClaudeCLI'
        Label     = 'Abrir com Claude Code CLI'
        Title     = 'Claude Code CLI'
        Commands  = @('claude')
        Paths     = @(
            "$env:USERPROFILE\.local\bin\claude.exe",
            "$env:LOCALAPPDATA\Microsoft\WinGet\Links\claude.exe",
            "$env:APPDATA\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
            "$env:APPDATA\npm\claude.cmd",
            "$env:LOCALAPPDATA\Programs\claude\claude.exe",
            "$env:LOCALAPPDATA\AnthropicClaude\app\claude.exe"
        )
        Args      = '--dangerously-skip-permissions'
        IconFiles = @(
            "$env:LOCALAPPDATA\AnthropicClaude\app.ico",
            "$env:LOCALAPPDATA\AnthropicClaude\claude.exe",
            "$env:ProgramFiles\AnthropicClaude\claude.exe"
        )
        Appx      = @('*Claude*')
    },
    @{
        Key       = 'CodexCLI'
        Label     = 'Abrir com Codex CLI'
        Title     = 'Codex CLI'
        Commands  = @('codex')
        Paths     = @(
            "$env:LOCALAPPDATA\Microsoft\WinGet\Links\codex.exe",
            "$env:USERPROFILE\.codex\bin\codex.exe",
            "$env:APPDATA\npm\codex.cmd"
        )
        Args      = '--dangerously-bypass-hook-trust'
        IconFiles = @("$env:USERPROFILE\.codex\codex.ico")
        Appx      = @('*Codex*', '*ChatGPT*')
    },
    @{
        Key       = 'OpenCodeCLI'
        Label     = 'Abrir com OpenCode CLI'
        Title     = 'OpenCode CLI'
        Commands  = @('opencode')
        Paths     = @(
            "$env:APPDATA\npm\node_modules\opencode-ai\bin\opencode.exe",
            "$env:LOCALAPPDATA\Programs\@opencode-aidesktop\opencode.exe",
            "$env:APPDATA\npm\opencode.cmd"
        )
        Args      = '--auto'
    }
)

# Onde cada menu aparece. %V = pasta clicada/fundo/unidade; %1 = arquivo.
$Targets = @(
    @{ ShellPath = 'Software\Classes\Directory\shell';            Arg = '%V'    },
    @{ ShellPath = 'Software\Classes\Directory\Background\shell'; Arg = '%V'    },
    @{ ShellPath = 'Software\Classes\Drive\shell';                Arg = '%V'    },
    @{ ShellPath = 'Software\Classes\*\shell';                    Arg = '%1\..' }
)

$ObsoleteKeys = @('Antigravity', 'AntigravityIDE')

# =====================================================================
#  FUNÇÕES
# =====================================================================

function Write-Step([string]$Text) { Write-Host $Text -ForegroundColor Yellow }

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Backup-ContextMenu {
    # Exporta as chaves antes de mexer, para restaurar com um duplo clique no .reg
    $backupDir = Join-Path $env:LOCALAPPDATA 'IA-Hub\backups-registro'
    New-Item -ItemType Directory -Force $backupDir | Out-Null
    $ts = Get-Date -Format 'yyyyMMdd_HHmmss'
    foreach ($suffix in @('Directory_shell', 'Background_shell')) {
        $key  = if ($suffix -eq 'Directory_shell') { 'HKCU\Software\Classes\Directory\shell' } else { 'HKCU\Software\Classes\Directory\Background\shell' }
        $file = Join-Path $backupDir "context-menu_${suffix}_${ts}.reg"
        reg export $key $file /y 2>$null | Out-Null
    }
    return $backupDir
}

function Remove-ContextMenu([string]$Key) {
    foreach ($t in $Targets) {
        try {
            $reg = [Microsoft.Win32.Registry]::CurrentUser.OpenSubKey($t.ShellPath, $true)
            if ($reg) {
                if ($reg.GetSubKeyNames() -contains $Key) { $reg.DeleteSubKeyTree($Key, $false) }
                $reg.Close()
            }
        } catch {}
    }
}

function Find-CliExecutable($Tool) {
    # Só aceita executáveis que o cmd.exe consegue rodar (ignora .ps1 e shims sem extensão do npm)
    foreach ($name in $Tool.Commands) {
        $hit = Get-Command $name -CommandType Application -All -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.exe', '.cmd', '.bat' } |
            Sort-Object { if ($_.Extension -eq '.exe') { 0 } else { 1 } } |
            Select-Object -First 1
        if ($hit) { return $hit.Source }
    }
    foreach ($p in $Tool.Paths) {
        if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    }
    return $null
}

function Convert-PngToIco([string]$PngPath, [string]$IcoPath) {
    # ICO com PNG embutido (suportado desde o Windows Vista) — mantém a transparência e a resolução
    $png = [IO.File]::ReadAllBytes($PngPath)
    $w = ($png[16] -shl 24) -bor ($png[17] -shl 16) -bor ($png[18] -shl 8) -bor $png[19]
    $h = ($png[20] -shl 24) -bor ($png[21] -shl 16) -bor ($png[22] -shl 8) -bor $png[23]

    $ms = New-Object IO.MemoryStream
    $bw = New-Object IO.BinaryWriter($ms)
    $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1)          # cabeçalho: tipo ícone, 1 imagem
    $bw.Write([byte]$(if ($w -ge 256) { 0 } else { $w }))
    $bw.Write([byte]$(if ($h -ge 256) { 0 } else { $h }))
    $bw.Write([byte]0); $bw.Write([byte]0)                                     # paleta, reservado
    $bw.Write([UInt16]1); $bw.Write([UInt16]32)                                # planos, bits por pixel
    $bw.Write([UInt32]$png.Length); $bw.Write([UInt32]22)                      # tamanho, offset
    $bw.Write($png)
    $bw.Flush()
    [IO.File]::WriteAllBytes($IcoPath, $ms.ToArray())
    $bw.Close()
}

function Get-AppxIcon($Tool) {
    # Apps da Microsoft Store (Claude Desktop, ChatGPT/Codex) ficam em pastas versionadas do WindowsApps,
    # então o ícone é copiado para um local fixo para não quebrar quando o app atualizar.
    foreach ($pattern in $Tool.Appx) {
        $pkgs = try { Get-AppxPackage -Name $pattern -ErrorAction Stop } catch { @() }
        foreach ($pkg in $pkgs) {
            $loc = $pkg.InstallLocation
            if (-not $loc -or -not (Test-Path -LiteralPath $loc)) { continue }

            $dest = Join-Path $IconCacheDir "$($Tool.Key).ico"
            New-Item -ItemType Directory -Path $IconCacheDir -Force | Out-Null

            $ico = Get-ChildItem -LiteralPath $loc -Filter *.ico -Recurse -Depth 4 -File -ErrorAction SilentlyContinue |
                Sort-Object Length -Descending | Select-Object -First 1
            if ($ico) {
                Copy-Item -LiteralPath $ico.FullName -Destination $dest -Force
                return $dest
            }

            $png = Get-ChildItem -LiteralPath $loc -Filter *.png -Recurse -Depth 4 -File -ErrorAction SilentlyContinue |
                Where-Object { $_.Name -match 'Logo.*targetsize-\d+' -and $_.Name -notmatch 'light' } |
                Sort-Object @{ Expression = { [int][regex]::Match($_.Name, 'targetsize-(\d+)').Groups[1].Value }; Descending = $true },
                            @{ Expression = { if ($_.Name -match 'unplated') { 0 } else { 1 } }; Descending = $false } |
                Select-Object -First 1
            if ($png) {
                Convert-PngToIco $png.FullName $dest
                return $dest
            }
        }
    }
    return $null
}

function Resolve-ToolIcon($Tool, [string]$Exe) {
    # 1) Ícone personalizado do usuário (icons\<Key>.ico ao lado do script)
    $override = Join-Path $IconOverrides "$($Tool.Key).ico"
    if (Test-Path -LiteralPath $override) { return $override }

    # 2) Instalações tradicionais conhecidas
    foreach ($f in $Tool.IconFiles) {
        if (Test-Path -LiteralPath $f) {
            if ($f -like '*.exe') { return "$f,0" } else { return $f }
        }
    }

    # 3) Apps da Microsoft Store
    $appx = Get-AppxIcon $Tool
    if ($appx) { return $appx }

    # 4) O próprio executável do CLI (.cmd/.bat não têm ícone)
    if ($Exe -like '*.exe') { return "$Exe,0" }

    return $FallbackIcon
}

function Register-ContextMenu($Tool, [string]$Exe, [string]$Icon) {
    $launch = ("`"$Exe`" " + $Tool.Args).Trim()
    foreach ($t in $Targets) {
        $keyPath = "$($t.ShellPath)\$($Tool.Key)"
        # /s + aspas externas: o cmd remove só o par externo e preserva as aspas internas
        $command = "cmd.exe /s /k `"pushd `"$($t.Arg)`" && title $($Tool.Title) && $launch`""

        $k = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey($keyPath)
        $k.SetValue('', $Tool.Label)
        $k.SetValue('Icon', $Icon)
        $k.Close()

        $c = [Microsoft.Win32.Registry]::CurrentUser.CreateSubKey("$keyPath\command")
        $c.SetValue('', $command)
        $c.Close()
    }
}

function Update-Trusted {
    # Pastas confiáveis para os CLIs com permissão ampliada (Claude Code + Antigravity)
    foreach ($sf in @("$env:USERPROFILE\.claude\settings.json", "$env:USERPROFILE\.gemini\antigravity-cli\settings.json")) {
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
}

function Update-Explorer {
    Add-Type -Namespace Win32 -Name Shell -MemberDefinition @'
[DllImport("shell32.dll")]
public static extern void SHChangeNotify(int wEventId, uint uFlags, System.IntPtr dwItem1, System.IntPtr dwItem2);
'@ -ErrorAction SilentlyContinue
    [Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)   # SHCNE_ASSOCCHANGED
    Start-Process -FilePath "$env:SystemRoot\System32\ie4uinit.exe" -ArgumentList '-show' -WindowStyle Hidden -ErrorAction SilentlyContinue
}

# =====================================================================
#  EXECUÇÃO
# =====================================================================

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '   Menu de contexto do Windows - Agentes de IA (IA-Hub)  ' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ''

Write-Step '[1/4] Salvando backup do menu atual...'
$backupDir = Backup-ContextMenu
Write-Host "  ✓ Backup em $backupDir" -ForegroundColor Green
Write-Host ''

Write-Step '[2/4] Limpando registros de menus anteriores...'
foreach ($tool in $Tools) { Remove-ContextMenu $tool.Key }
foreach ($old in $ObsoleteKeys) { Remove-ContextMenu $old }
Write-Host '  ✓ Menus antigos removidos.' -ForegroundColor Green
Write-Host ''

Write-Step '[3/4] Detectando ferramentas e ícones...'
$found = @()
foreach ($tool in $Tools) {
    $exe = Find-CliExecutable $tool
    if (-not $exe) {
        Write-Host "  [-] $($tool.Title) não encontrado (menu não será adicionado)." -ForegroundColor DarkGray
        continue
    }
    $icon = Resolve-ToolIcon $tool $exe
    Write-Host "  [+] $($tool.Title)" -ForegroundColor Green
    Write-Host "      exe:   $exe" -ForegroundColor Gray
    Write-Host "      ícone: $icon" -ForegroundColor Gray
    if ($icon -eq $FallbackIcon) {
        Write-Host "      (ícone genérico — coloque icons\$($tool.Key).ico ao lado deste script para personalizar)" -ForegroundColor DarkYellow
    }
    $found += @{ Tool = $tool; Exe = $exe; Icon = $icon }
}
Write-Host ''

Write-Step '[4/4] Aplicando menus de contexto...'
$applied = @{}
if ($found.Count -eq 0) {
    Write-Host '  Nenhum dos CLIs suportados foi detectado neste computador.' -ForegroundColor Red
} else {
    foreach ($f in $found) {
        try {
            Register-ContextMenu $f.Tool $f.Exe $f.Icon
            $applied[$f.Tool.Key] = "configurado -> $($f.Exe)"
            Write-Host "  ✓ $($f.Tool.Label)" -ForegroundColor Green
        } catch {
            Write-Host "  ✗ Falha em $($f.Tool.Label): $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    Update-Trusted
    Update-Explorer
    Write-Host ''
    Write-Host '✓ Concluído! Menus e cache de ícones do Explorer atualizados.' -ForegroundColor Green
}

# Resultado para o install.ps1 (chaves usadas pelo relatório de instalação)
return [ordered]@{
    ClaudeCLI   = if ($applied['ClaudeCLI'])   { $applied['ClaudeCLI'] }   else { 'nao encontrado - ignorado' }
    OpenCode    = if ($applied['OpenCodeCLI']) { $applied['OpenCodeCLI'] } else { 'nao encontrado - ignorado' }
    CodexCLI    = if ($applied['CodexCLI'])    { $applied['CodexCLI'] }    else { 'nao encontrado - ignorado' }
    AgyCliExe   = if ($applied['AntigravityCLI']) { $applied['AntigravityCLI'] } else { 'nao encontrado - ignorado' }
    Obsoletos   = 'Antigravity e AntigravityIDE removidos (se existiam)'
    Backup      = $backupDir
}
