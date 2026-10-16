$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $work=Join-Path ([IO.Path]::GetTempPath()) ('ia-hub-setup.'+[guid]::NewGuid().ToString('N')); $code=1
try {
$env:PSModulePath=($PSHOME+'\Modules;'+[Environment]::GetFolderPath('MyDocuments')+'\WindowsPowerShell\Modules;'+$env:ProgramFiles+'\WindowsPowerShell\Modules')
New-Item -ItemType Directory -Path $work | Out-Null
$text=[IO.File]::ReadAllText($env:IA_HUB_PORTABLE_FILE)
$marker='__IA_HUB_'+'PAYLOAD__'
$data=[Convert]::FromBase64String(($text -split ('(?m)^'+$marker+'\r?$'),2)[1])
$sha=[Security.Cryptography.SHA256]::Create(); $hash=([BitConverter]::ToString($sha.ComputeHash($data))).Replace('-','').ToLowerInvariant(); $sha.Dispose()
if($hash -ne '{{SHA256}}') { throw 'Pacote corrompido (SHA256).' }
$zip=Join-Path $work 'payload.zip'; [IO.File]::WriteAllBytes($zip,$data)
Add-Type -AssemblyName System.IO.Compression.FileSystem
$app=Join-Path $work 'app'; [IO.Compression.ZipFile]::ExtractToDirectory($zip,$app)
if($env:IA_HUB_PORTABLE_MODE -eq '--self-test') { Write-Host 'Pacote integro. Extracao temporaria verificada.'; $code=0 }
else { & powershell.exe -NoProfile -ExecutionPolicy Bypass -File (Join-Path $app 'scripts\portable\bootstrap.ps1'); $code=$LASTEXITCODE }
} catch { Write-Host $_.Exception.Message -ForegroundColor Red }
finally {
$parent=[IO.Path]::GetFullPath([IO.Path]::GetTempPath()).TrimEnd('\'); $resolved=[IO.Path]::GetFullPath($work)
if(([IO.Path]::GetDirectoryName($resolved) -eq $parent) -and ([IO.Path]::GetFileName($resolved) -match '^ia-hub-setup\.[a-f0-9]{32}$')) {
for($attempt=0;$attempt -lt 5;$attempt++) { try { if(Test-Path -LiteralPath $resolved) { Remove-Item -LiteralPath $resolved -Recurse -Force }; break } catch { Start-Sleep -Milliseconds 300 } }
if(Test-Path -LiteralPath $resolved) { Write-Warning ('Nao foi possivel limpar: '+$resolved); $code=1 }
}
}
exit $code
