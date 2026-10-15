# Functions only: safe to dot-source for diagnostics/tests.
$ErrorActionPreference = 'Stop'
$script:HubRoot = Split-Path $PSScriptRoot -Parent

function Write-HubEvent($phase, $status) {
    if ($env:IA_HUB_UI_WORKER -eq '1') { Write-Host ('IA_HUB_EVENT:' + (@{phase=$phase;status=$status} | ConvertTo-Json -Compress)) }
}

function Update-HubPath {
    $extra = @("$env:USERPROFILE\.local\bin", "$env:LOCALAPPDATA\agy\bin", "$env:LOCALAPPDATA\IA-Hub\bin", "$script:HubRoot\.tools\uv", "$env:LOCALAPPDATA\Microsoft\WindowsApps")
    $paths = ($extra + @($env:PATH, [Environment]::GetEnvironmentVariable('PATH','User'), [Environment]::GetEnvironmentVariable('PATH','Machine'))) -join ';'
    $env:PATH = (($paths -split ';' | Where-Object { $_ } | Select-Object -Unique) -join ';')
}

function Find-HubUv {
    Update-HubPath
    $cmd = Get-Command uv.exe -ErrorAction SilentlyContinue
    if ($cmd) { return $cmd.Source }
}

function Invoke-HubUvInstaller {
    $dir = Join-Path $script:HubRoot '.tools\uv'
    New-Item -ItemType Directory -Force $dir | Out-Null
    $file = Join-Path $dir 'install.ps1'
    Invoke-WebRequest 'https://astral.sh/uv/0.11.24/install.ps1' -UseBasicParsing -OutFile $file
    $oldDir = $env:UV_INSTALL_DIR; $oldPath = $env:UV_NO_MODIFY_PATH
    try {
        $env:UV_INSTALL_DIR = $dir; $env:UV_NO_MODIFY_PATH = '1'
        & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $file | Out-Host
        if ($LASTEXITCODE -ne 0) { throw 'uv installer failed.' }
    } finally { $env:UV_INSTALL_DIR = $oldDir; $env:UV_NO_MODIFY_PATH = $oldPath }
}

function Ensure-HubUv {
    $uv = Find-HubUv
    if (-not $uv) { Invoke-HubUvInstaller; $uv = Find-HubUv }
    if (-not $uv) { throw 'uv unavailable after installation.' }
    return $uv
}

function Find-HubWinget {
    Update-HubPath
    $command = Get-Command winget.exe -ErrorAction SilentlyContinue
    if (-not $command) { return $false }
    $null = & $command.Source --version
    return ($LASTEXITCODE -eq 0)
}

function Invoke-HubWingetInstaller {
    [Net.ServicePointManager]::SecurityProtocol = [Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12
    Install-PackageProvider -Name NuGet -MinimumVersion 2.8.5.201 -Scope CurrentUser -Force | Out-Null
    $get = Get-Module PowerShellGet -ListAvailable | Sort-Object Version -Descending | Select-Object -First 1
    if (-not $get -or $get.Version -lt [version]'2.2.5') {
        Install-Module PowerShellGet -Repository PSGallery -Scope CurrentUser -Force -AllowClobber
    }
    # Fresh process loads updated PowerShellGet, not the inbox 1.x already in memory.
    $command = '$ErrorActionPreference="Stop"; [Net.ServicePointManager]::SecurityProtocol=[Net.ServicePointManager]::SecurityProtocol -bor [Net.SecurityProtocolType]::Tls12; Import-Module PowerShellGet -MinimumVersion 2.2.5 -Force; Install-Module Microsoft.WinGet.Client -Repository PSGallery -Scope CurrentUser -Force; Import-Module Microsoft.WinGet.Client; Repair-WinGetPackageManager -Latest -ErrorAction Stop'
    $encoded = [Convert]::ToBase64String([Text.Encoding]::Unicode.GetBytes($command))
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -EncodedCommand $encoded | Out-Host
    if ($LASTEXITCODE -ne 0) { throw 'Microsoft WinGet bootstrap failed; check Windows App Installer policies.' }
}

function Ensure-HubWinget {
    if (Find-HubWinget) { return }
    if ($script:HubWingetError) { throw $script:HubWingetError }
    try {
        Invoke-HubWingetInstaller
        if (-not (Find-HubWinget)) { throw 'winget unavailable after bootstrap.' }
    } catch { $script:HubWingetError = $_.Exception.Message; throw }
}

function Install-HubPackage($id, $source = 'winget') {
    Ensure-HubWinget
    $args = @('install', '--id', $id, '--exact', '--source', $source, '--silent', '--disable-interactivity', '--accept-package-agreements', '--accept-source-agreements')
    if ($source -eq 'winget') { $args += @('--scope','user') }
    & winget.exe @args | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "winget $id exit $LASTEXITCODE" }
}

function Ensure-HubPackage($name, $id, [scriptblock]$detect, $source = 'winget', [scriptblock]$installer) {
    $keys = @{'Claude Code'='claude';'Codex CLI'='codex';'Antigravity CLI'='agy';'OpenCode CLI'='opencode';'Obsidian'='desktop';'Claude Desktop'='desktop';'Antigravity App'='desktop';'Codex App'='desktop'}
    $selected = @($env:IA_HUB_COMPONENTS -split ',' | Where-Object { $_ })
    $force = @($env:IA_HUB_FORCE_COMPONENTS -split ',' | Where-Object { $_ })
    $present = & $detect
    if ($selected.Count -and $keys[$name] -notin $selected) { return [pscustomobject]@{name=$name;state='skipped';detail='Outside selected components'} }
    if ($present -and $keys[$name] -notin $force) { return [pscustomobject]@{name=$name;state='present';detail='Existing installation preserved'} }
    Write-Host "Installing $name ..."
    try {
        if ($installer) { & $installer } else { Install-HubPackage $id $source }
        Update-HubPath
        if (-not (& $detect)) { throw 'Installer completed but application was not found.' }
        return [pscustomobject]@{name=$name;state='installed';detail='Authentication may still be required'}
    } catch { return [pscustomobject]@{name=$name;state='failed';detail=$_.Exception.Message} }
}

function Install-HubNativeScript($url, $name) {
    $dir = if ($env:IA_HUB_WORK_DIR) { $env:IA_HUB_WORK_DIR } else { Join-Path $script:HubRoot '.tools' }
    New-Item -ItemType Directory -Force $dir | Out-Null
    $file = Join-Path $dir "$name-install.ps1"
    Invoke-WebRequest $url -UseBasicParsing -OutFile $file
    & powershell.exe -NoProfile -ExecutionPolicy Bypass -File $file | Out-Host
    if ($LASTEXITCODE -ne 0) { throw "$name installer exit $LASTEXITCODE" }
}

function Install-HubOpenCode {
    if ($env:PROCESSOR_ARCHITECTURE -ne 'AMD64') { throw 'OpenCode bootstrap requires Windows x64.' }
    $dir = if ($env:IA_HUB_WORK_DIR) { $env:IA_HUB_WORK_DIR } else { Join-Path $script:HubRoot '.tools' }
    New-Item -ItemType Directory -Force $dir | Out-Null
    $zip = Join-Path $dir 'opencode.zip'
    Invoke-WebRequest 'https://github.com/anomalyco/opencode/releases/download/v1.18.33/opencode-windows-x64-baseline.zip' -UseBasicParsing -OutFile $zip
    if ((Get-FileHash $zip -Algorithm SHA256).Hash -ne 'D69FCDF88552EACF8BD3140015E629941F284B603A25FA53BB565BD3BECBF59A') { throw 'OpenCode SHA256 mismatch.' }
    $dest = "$env:LOCALAPPDATA\IA-Hub\bin"
    New-Item -ItemType Directory -Force $dest | Out-Null
    Expand-Archive -LiteralPath $zip -DestinationPath $dest -Force
    $userPath = [string][Environment]::GetEnvironmentVariable('PATH','User')
    if ($dest -notin ($userPath -split ';')) { [Environment]::SetEnvironmentVariable('PATH', ($userPath.TrimEnd(';') + ';' + $dest), 'User') }
}

function Invoke-HubBootstrap {
    Update-HubPath
    $null = Ensure-HubUv
    $results = @(
        Ensure-HubPackage 'Claude Code' 'Anthropic.ClaudeCode' { [bool](Get-Command claude -ErrorAction SilentlyContinue) } 'winget' { Install-HubNativeScript 'https://claude.ai/install.ps1' 'claude' }
        Ensure-HubPackage 'Codex CLI' 'OpenAI.Codex' { [bool](Get-Command codex -ErrorAction SilentlyContinue) } 'winget' { Install-HubNativeScript 'https://chatgpt.com/codex/install.ps1' 'codex' }
        Ensure-HubPackage 'Antigravity CLI' '' { [bool](Get-Command agy -ErrorAction SilentlyContinue) } 'winget' { Install-HubNativeScript 'https://antigravity.google/cli/install.ps1' 'antigravity' }
        Ensure-HubPackage 'OpenCode CLI' '' { [bool](Get-Command opencode -ErrorAction SilentlyContinue) } 'winget' { Install-HubOpenCode }
        Ensure-HubPackage 'Obsidian' 'Obsidian.Obsidian' { (Test-Path "$env:LOCALAPPDATA\Programs\Obsidian\Obsidian.exe") -or (Test-Path "$env:ProgramFiles\Obsidian\Obsidian.exe") }
        Ensure-HubPackage 'Claude Desktop' 'Anthropic.Claude' { (Test-Path "$env:LOCALAPPDATA\AnthropicClaude\claude.exe") -or [bool](Get-AppxPackage 'Claude*' -ErrorAction SilentlyContinue) }
        Ensure-HubPackage 'Antigravity App' 'Google.Antigravity' { (Test-Path "$env:LOCALAPPDATA\Programs\Antigravity\Antigravity.exe") -or (Test-Path "$env:LOCALAPPDATA\Programs\Antigravity\antigravity.exe") }
        Ensure-HubPackage 'Codex App' '9PLM9XGG6VKS' { [bool](Get-AppxPackage '*Codex*' -ErrorAction SilentlyContinue) } 'msstore'
    )
    New-Item -ItemType Directory -Force "$script:HubRoot\contexto" | Out-Null
    $results | ConvertTo-Json -Depth 5 | Set-Content "$script:HubRoot\contexto\bootstrap.json" -Encoding UTF8
    return $results
}

function Assert-HubServiceOwnership {
    $socket = New-Object Net.Sockets.TcpClient
    try { $connected = $socket.ConnectAsync('127.0.0.1', 43127).Wait(1000) -and $socket.Connected } catch { $connected = $false } finally { $socket.Dispose() }
    if (-not $connected) { return }
    try {
        $token = [IO.File]::ReadAllText("$script:HubRoot\contexto\.memory\token").Trim()
        $r = Invoke-RestMethod 'http://127.0.0.1:43127/rpc' -Method Post -ContentType 'application/json' -Headers @{Authorization="Bearer $token"} -Body '{"action":"health"}' -TimeoutSec 10
        if ([IO.Path]::GetFullPath($r.result.root) -ne [IO.Path]::GetFullPath($script:HubRoot)) { throw 'Different root' }
    } catch {
        throw 'Port 43127 belongs to another installation. Run instalar.cmd in the original IA-Hub folder; migrate the existing data before activating another clone. No client settings were changed.'
    }
}
