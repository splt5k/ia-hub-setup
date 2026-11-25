# Configura o menu de contexto do Windows (HKCU) para os CLIs do IA-Hub.
# Idempotente: remove as entradas gerenciadas e recria so as ferramentas encontradas.
#
# Entradas gerenciadas (ver $Tools): Antigravity CLI, Claude CLI, Codex CLI, OpenCode CLI.
# Onde aparecem (ver $Targets): pastas, fundo de pasta e unidades.
# Antigravity, AntigravityIDE e OpenCode (versoes antigas) sao removidos se existirem.
#
# Nao altera: VSCode, Visual Studio, Terminal nem nenhuma outra chave.

$ErrorActionPreference = 'Stop'
[Console]::OutputEncoding = [System.Text.Encoding]::UTF8

# =====================================================================
#  CONFIGURACAO
# =====================================================================

$IconCacheDir  = Join-Path $env:LOCALAPPDATA 'IA-Hub\icons'
$LaunchersDir  = Join-Path $env:LOCALAPPDATA 'AgentesIA\launchers'
$IconOverrides = Join-Path $PSScriptRoot 'icons'   # icons\<Key>.ico ao lado do script tem prioridade
$FallbackIcon  = "$env:SystemRoot\System32\WindowsPowerShell\v1.0\powershell.exe,0"

$Tools = @(
    @{
        Key       = 'AntigravityCLI'
        ToolId    = 'antigravity'
        Label     = 'Abrir com Antigravity CLI'
        Title     = 'Antigravity CLI'
        Commands  = @('agy')
        Paths     = @(
            "$env:LOCALAPPDATA\agy\bin\agy.exe",
            "$env:LOCALAPPDATA\Programs\Antigravity CLI\agy.exe",
            "$env:LOCALAPPDATA\Programs\Antigravity\bin\agy.exe"
        )
        Args      = @('--dangerously-skip-permissions', '--model', 'gemini-3.8-flash-medium')
        Env       = @{}
        IconFiles = @(
            "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe",
            "$env:ProgramFiles\Antigravity\Antigravity.exe",
            "$env:LOCALAPPDATA\agy\antigravity.ico"
        )
        Appx      = @('*Antigravity*')
    },
    @{
        Key       = 'ClaudeCLI'
        ToolId    = 'claude'
        Label     = 'Abrir com Claude CLI'
        Title     = 'Claude CLI'
        Commands  = @('claude')
        Paths     = @(
            "$env:USERPROFILE\.local\bin\claude.exe",
            "$env:LOCALAPPDATA\Microsoft\WinGet\Links\claude.exe",
            "$env:APPDATA\npm\claude.ps1",
            "$env:APPDATA\npm\claude.cmd",
            "$env:APPDATA\npm\node_modules\@anthropic-ai\claude-code\bin\claude.exe",
            "$env:LOCALAPPDATA\Programs\claude\claude.exe",
            "$env:LOCALAPPDATA\AnthropicClaude\app\claude.exe"
        )
        Args      = @('--dangerously-skip-permissions', '--model', 'sonnet', '--advisor', 'opus', '--chrome')
        Env       = @{ CLAUDE_CODE_SUBAGENT_MODEL = 'haiku' }
        IconFiles = @(
            "$env:LOCALAPPDATA\AgentesIA\icons\ClaudeCLI.ico",
            "$env:LOCALAPPDATA\AnthropicClaude\app.ico",
            "$env:LOCALAPPDATA\AnthropicClaude\claude.exe",
            "$env:ProgramFiles\AnthropicClaude\claude.exe"
        )
        Appx      = @('*Claude*')
    },
    @{
        Key       = 'CodexCLI'
        ToolId    = 'codex'
        Label     = 'Abrir com Codex CLI'
        Title     = 'Codex CLI'
        Commands  = @('codex')
        Paths     = @(
            "$env:LOCALAPPDATA\Programs\OpenAI\Codex\bin\codex.exe",
            "$env:LOCALAPPDATA\Microsoft\WinGet\Links\codex.exe",
            "$env:USERPROFILE\.codex\bin\codex.exe",
            "$env:APPDATA\npm\codex.ps1",
            "$env:APPDATA\npm\codex.cmd"
        )
        Args      = @('--dangerously-bypass-approvals-and-sandbox', '--dangerously-bypass-hook-trust', '-c', 'model=\"gpt-6.2-sol\"', '-c', 'model_reasoning_effort=\"medium\"', '--search')
        Env       = @{}
        IconFiles = @(
            "$env:LOCALAPPDATA\IA-Hub\icons\CodexCLI.ico",
            "$env:LOCALAPPDATA\AgentesIA\icons\CodexCLI.ico",
            "$env:USERPROFILE\.codex\codex.ico"
        )
        Appx      = @('*Codex*', '*ChatGPT*')
    },
    @{
        Key       = 'OpenCodeCLI'
        ToolId    = 'opencode'
        Label     = 'Abrir com OpenCode CLI'
        Title     = 'OpenCode CLI'
        Commands  = @('opencode')
        Paths     = @(
            "$env:APPDATA\npm\node_modules\opencode-ai\bin\opencode.exe",
            "$env:LOCALAPPDATA\Programs\@opencode-aidesktop\opencode.exe",
            "$env:APPDATA\npm\opencode.ps1",
            "$env:APPDATA\npm\opencode.cmd"
        )
        Args      = @('--auto')
        Env       = @{}
        IconFiles = @()
        Appx      = @()
    }
)

# Onde cada menu aparece. %V = pasta clicada/fundo/unidade.
$Targets = @(
    @{ ShellPath = 'Software\Classes\Directory\shell';            Arg = '%V' },
    @{ ShellPath = 'Software\Classes\Directory\Background\shell'; Arg = '%V' },
    @{ ShellPath = 'Software\Classes\Drive\shell';                Arg = '%V' }
)

$CleanupTargets = $Targets + @(
    @{ ShellPath = 'Software\Classes\*\shell'; Arg = '%1\..' }
)

$ObsoleteKeys = @('Antigravity', 'AntigravityIDE', 'OpenCode')

# =====================================================================
#  FUNCOES
# =====================================================================

function Write-Step([string]$Text) { Write-Host $Text -ForegroundColor Yellow }

function Write-Utf8NoBom([string]$Path, [string]$Content) {
    [System.IO.File]::WriteAllText($Path, $Content, [System.Text.UTF8Encoding]::new($false))
}

function Backup-ContextMenu {
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
    foreach ($t in $CleanupTargets) {
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
    foreach ($name in $Tool.Commands) {
        $hit = Get-Command $name -All -ErrorAction SilentlyContinue |
            Where-Object { $_.Extension -in '.exe', '.ps1', '.cmd', '.bat' } |
            Sort-Object {
                switch ($_.Extension) {
                    '.exe' { 0 }
                    '.ps1' { 1 }
                    '.cmd' { 2 }
                    '.bat' { 3 }
                    default { 9 }
                }
            } |
            Select-Object -First 1
        if ($hit -and (Test-Path -LiteralPath $hit.Source)) { return $hit.Source }
    }
    foreach ($p in $Tool.Paths) {
        if (Test-Path -LiteralPath $p) { return (Resolve-Path -LiteralPath $p).Path }
    }
    return $null
}

function Convert-PngToIco([string]$PngPath, [string]$IcoPath) {
    $png = [IO.File]::ReadAllBytes($PngPath)
    $w = ($png[16] -shl 24) -bor ($png[17] -shl 16) -bor ($png[18] -shl 8) -bor $png[19]
    $h = ($png[20] -shl 24) -bor ($png[21] -shl 16) -bor ($png[22] -shl 8) -bor $png[23]

    $ms = New-Object IO.MemoryStream
    $bw = New-Object IO.BinaryWriter($ms)
    $bw.Write([UInt16]0); $bw.Write([UInt16]1); $bw.Write([UInt16]1)
    $bw.Write([byte]$(if ($w -ge 256) { 0 } else { $w }))
    $bw.Write([byte]$(if ($h -ge 256) { 0 } else { $h }))
    $bw.Write([byte]0); $bw.Write([byte]0)
    $bw.Write([UInt16]1); $bw.Write([UInt16]32)
    $bw.Write([UInt32]$png.Length); $bw.Write([UInt32]22)
    $bw.Write($png)
    $bw.Flush()
    [IO.File]::WriteAllBytes($IcoPath, $ms.ToArray())
    $bw.Close()
}

function Get-AppxIcon($Tool) {
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
    $override = Join-Path $IconOverrides "$($Tool.Key).ico"
    if (Test-Path -LiteralPath $override) { return $override }

    foreach ($f in $Tool.IconFiles) {
        if (Test-Path -LiteralPath $f) {
            if ($f -like '*.exe') { return "$f,0" } else { return $f }
        }
    }

    $appx = Get-AppxIcon $Tool
    if ($appx) { return $appx }

    if ($Exe -like '*.exe') { return "$Exe,0" }

    return $FallbackIcon
}

function Install-Launchers($FoundTools) {
    New-Item -ItemType Directory -Force $LaunchersDir | Out-Null

    $cfgMap = @{}
    foreach ($f in $FoundTools) {
        $cfgMap[$f.Tool.ToolId] = @{
            Title = $f.Tool.Title
            Exe   = $f.Exe
            Args  = $f.Tool.Args
            Env   = $f.Tool.Env
        }
    }
    Write-Utf8NoBom (Join-Path $LaunchersDir 'tools-config.json') ($cfgMap | ConvertTo-Json -Depth 5)

    $ps1Path = Join-Path $LaunchersDir 'launch-wt.ps1'
    $ps1Content = @'
param(
    [Parameter(Mandatory = $true)]
    [string]$Tool,
    [string]$Target = ''
)

$ErrorActionPreference = 'Stop'

$dir = $HOME
if (-not [string]::IsNullOrWhiteSpace($Target)) {
    $clean = $Target.Trim('"')
    if (Test-Path -LiteralPath $clean -PathType Container) {
        $dir = (Resolve-Path -LiteralPath $clean).Path
    } elseif (Test-Path -LiteralPath $clean -PathType Leaf) {
        $dir = Split-Path -Path (Resolve-Path -LiteralPath $clean).Path -Parent
    }
}

$cfgPath = Join-Path $PSScriptRoot 'tools-config.json'
$allCfg = Get-Content -LiteralPath $cfgPath -Raw -Encoding UTF8 | ConvertFrom-Json
$cfg = $allCfg.$Tool
if (-not $cfg) { throw "Ferramenta nao configurada: $Tool" }

$lines = New-Object System.Collections.Generic.List[string]
$lines.Add('$Host.UI.RawUI.WindowTitle = ' + "'" + $cfg.Title.Replace("'", "''") + "'")
$lines.Add('Set-Location -LiteralPath ' + "'" + $dir.Replace("'", "''") + "'")

if ($cfg.Env) {
    foreach ($prop in $cfg.Env.PSObject.Properties) {
        $lines.Add('$env:' + $prop.Name + ' = ' + "'" + ([string]$prop.Value).Replace("'", "''") + "'")
    }
}

$quotedArgs = @()
if ($cfg.Args) {
    $quotedArgs = @($cfg.Args | ForEach-Object { "'" + ([string]$_).Replace("'", "''") + "'" })
}
$argStr = $quotedArgs -join ' '
$lines.Add('& ' + "'" + ([string]$cfg.Exe).Replace("'", "''") + "' " + $argStr)

$scriptText = $lines -join "`n"
$encoded = [Convert]::ToBase64String([System.Text.Encoding]::Unicode.GetBytes($scriptText))

$wtCmd = Get-Command 'wt.exe' -ErrorAction SilentlyContinue | Select-Object -First 1
if ($wtCmd) {
    $profileArg = 'Windows PowerShell'
    $wtSettingsCandidates = @(
        "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminal_8wekyb3d8bbwe\LocalState\settings.json",
        "$env:LOCALAPPDATA\Packages\Microsoft.WindowsTerminalPreview_8wekyb3d8bbwe\LocalState\settings.json",
        "$env:LOCALAPPDATA\Microsoft\Windows Terminal\settings.json"
    )
    foreach ($sPath in $wtSettingsCandidates) {
        if (Test-Path -LiteralPath $sPath) {
            try {
                $wtJson = Get-Content -LiteralPath $sPath -Raw -Encoding UTF8 | ConvertFrom-Json
                $psProfile = $wtJson.profiles.list | Where-Object { $_.name -eq 'Windows PowerShell' -or $_.name -eq 'PowerShell' } | Select-Object -First 1
                if ($psProfile -and $psProfile.guid) {
                    $profileArg = $psProfile.guid
                    break
                } elseif ($wtJson.defaultProfile) {
                    $profileArg = $wtJson.defaultProfile
                    break
                }
            } catch {}
        }
    }
    $wtDir = if ($dir.EndsWith('\')) { "$dir." } else { $dir }
    $wtArgs = '-p "' + $profileArg + '" -d "' + $wtDir + '" -- powershell.exe -NoExit -EncodedCommand ' + $encoded
    Start-Process -FilePath $wtCmd.Source -ArgumentList $wtArgs
} else {
    Start-Process -FilePath 'powershell.exe' -WorkingDirectory $dir -ArgumentList @('-NoExit', '-EncodedCommand', $encoded)
}
'@
    Write-Utf8NoBom $ps1Path $ps1Content

    $vbsPath = Join-Path $LaunchersDir 'launch-wt.vbs'
    $vbsContent = @"
Dim tool, target, ps1, cmd, shell
If WScript.Arguments.Count < 1 Then WScript.Quit 1
tool = WScript.Arguments(0)
target = ""
If WScript.Arguments.Count >= 2 Then target = WScript.Arguments(1)

If Right(target, 1) = "\" Then target = target & "."
target = Replace(target, """", "")

ps1 = "$ps1Path"
cmd = "powershell.exe -NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File """ & ps1 & """ -Tool " & tool & " -Target """ & target & """"

Set shell = CreateObject("WScript.Shell")
shell.Run cmd, 0, False
"@
    [IO.File]::WriteAllText($vbsPath, $vbsContent, [System.Text.Encoding]::ASCII)
    return $vbsPath
}

function Register-ContextMenu($Tool, [string]$VbsPath, [string]$Icon) {
    $command = "wscript.exe `"$VbsPath`" $($Tool.ToolId) `"%V`""
    foreach ($t in $Targets) {
        $keyPath = "$($t.ShellPath)\$($Tool.Key)"
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
    [Win32.Shell]::SHChangeNotify(0x08000000, 0, [IntPtr]::Zero, [IntPtr]::Zero)
    Start-Process -FilePath "$env:SystemRoot\System32\ie4uinit.exe" -ArgumentList '-show' -WindowStyle Hidden -ErrorAction SilentlyContinue
}

# =====================================================================
#  EXECUCAO
# =====================================================================

Write-Host '========================================================' -ForegroundColor Cyan
Write-Host '   Menu de contexto do Windows - Agentes de IA (IA-Hub)  ' -ForegroundColor Cyan
Write-Host '========================================================' -ForegroundColor Cyan
Write-Host ''

Write-Step '[1/4] Salvando backup do menu atual...'
$backupDir = Backup-ContextMenu
Write-Host "  [OK] Backup em $backupDir" -ForegroundColor Green
Write-Host ''

Write-Step '[2/4] Limpando registros de menus anteriores...'
foreach ($tool in $Tools) { Remove-ContextMenu $tool.Key }
foreach ($old in $ObsoleteKeys) { Remove-ContextMenu $old }
Write-Host '  [OK] Menus antigos removidos.' -ForegroundColor Green
Write-Host ''

Write-Step '[3/4] Detectando ferramentas e icones...'
$found = @()
foreach ($tool in $Tools) {
    $exe = Find-CliExecutable $tool
    if (-not $exe) {
        Write-Host "  [-] $($tool.Title) nao encontrado (menu nao sera adicionado)." -ForegroundColor DarkGray
        continue
    }
    $icon = Resolve-ToolIcon $tool $exe
    Write-Host "  [+] $($tool.Title)" -ForegroundColor Green
    Write-Host "      exe:   $exe" -ForegroundColor Gray
    Write-Host "      icone: $icon" -ForegroundColor Gray
    if ($icon -eq $FallbackIcon) {
        Write-Host "      (icone generico — coloque icons\$($tool.Key).ico ao lado deste script para personalizar)" -ForegroundColor DarkYellow
    }
    $found += @{ Tool = $tool; Exe = $exe; Icon = $icon }
}
Write-Host ''

Write-Step '[4/4] Aplicando menus de contexto...'
$applied = @{}
if ($found.Count -eq 0) {
    Write-Host '  Nenhum dos CLIs suportados foi detectado neste computador.' -ForegroundColor Red
} else {
    $vbsPath = Install-Launchers $found
    foreach ($f in $found) {
        try {
            Register-ContextMenu $f.Tool $vbsPath $f.Icon
            $applied[$f.Tool.Key] = "configurado -> $($f.Exe)"
            Write-Host "  [OK] $($f.Tool.Label)" -ForegroundColor Green
        } catch {
            Write-Host "  [ERRO] Falha em $($f.Tool.Label): $($_.Exception.Message)" -ForegroundColor Red
        }
    }
    Update-Trusted
    Update-Explorer
    Write-Host ''
    Write-Host '[OK] Concluido! Menus e cache de icones do Explorer atualizados.' -ForegroundColor Green
}

# Resultado para o install.ps1 (chaves usadas pelo relatorio de instalacao)
return [ordered]@{
    ClaudeCLI   = if ($applied['ClaudeCLI'])   { $applied['ClaudeCLI'] }   else { 'nao encontrado - ignorado' }
    OpenCode    = if ($applied['OpenCodeCLI']) { $applied['OpenCodeCLI'] } else { 'nao encontrado - ignorado' }
    CodexCLI    = if ($applied['CodexCLI'])    { $applied['CodexCLI'] }    else { 'nao encontrado - ignorado' }
    AgyCliExe   = if ($applied['AntigravityCLI']) { $applied['AntigravityCLI'] } else { 'nao encontrado - ignorado' }
    Obsoletos   = 'Antigravity e AntigravityIDE removidos (se existiam)'
    Backup      = $backupDir
}
