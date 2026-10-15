"""Build two standalone installers from public source, never from user data."""
import argparse
import base64
import gzip
import hashlib
import io
import json
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]


def public_files(root):
    files = {}
    for name in ('instalar.cmd', 'instalar.sh', 'install.ps1', 'sincronizar.cmd', 'README.md', '.gitignore'):
        data = (root / name).read_bytes()
        files[name] = data.replace(b'\r\n', b'\n') if name.endswith('.sh') else data
    for directory in ('scripts', 'regras', 'modelos', 'claude', 'opencode', 'chatgpt', 'docs', '.obsidian', 'assets'):
        for path in sorted((root / directory).rglob('*')):
            relative = path.relative_to(root)
            if path.is_symlink() or not path.is_file() or '__pycache__' in relative.parts:
                continue
            if directory == 'scripts' and (path.name in ('build-portable.py', 'memory-start.ps1') or 'portable' in relative.parts and path.name not in ('entry.py', 'bootstrap.ps1')):
                continue
            if path.suffix not in ('.py', '.ps1', '.sh', '.js', '.md', '.json', '.jsonc', '.css', '.html', '.lock', '.jpg'):
                continue
            if directory == 'assets' and relative.as_posix() != 'assets/instalador.jpg':
                continue
            if path.name.startswith('workspace'):
                continue
            if directory == '.obsidian' and relative.as_posix() not in {'.obsidian/app.json', '.obsidian/appearance.json', '.obsidian/core-plugins.json', '.obsidian/graph.json'}:
                continue
            data = path.read_bytes()
            if path.suffix in ('.py', '.sh', '.ps1', '.js', '.html', '.css'):
                data = data.decode('utf-8-sig').replace('\r\n', '\n').encode('utf-8')
                if path.suffix == '.ps1':
                    data = b'\xef\xbb\xbf' + data  # Windows PowerShell 5.1.
            files[relative.as_posix()] = data
    manifest = {'schema': 1, 'files': {name: hashlib.sha256(data).hexdigest() for name, data in sorted(files.items())}}
    files['payload-manifest.json'] = json.dumps(manifest, ensure_ascii=False, sort_keys=True).encode('utf-8')
    return files


def archives(files):
    zbuffer, tbuffer = io.BytesIO(), io.BytesIO()
    with zipfile.ZipFile(zbuffer, 'w', compression=zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files.items()):
            item = zipfile.ZipInfo(name, (2026, 1, 1, 0, 0, 0))
            item.compress_type = zipfile.ZIP_DEFLATED
            item.external_attr = 0o100644 << 16
            archive.writestr(item, data)
    with tarfile.open(fileobj=tbuffer, mode='w') as archive:
        for name, data in sorted(files.items()):
            item = tarfile.TarInfo(name)
            item.size, item.mode = len(data), 0o755 if name.endswith('.sh') else 0o644
            archive.addfile(item, io.BytesIO(data))
    return zbuffer.getvalue(), gzip.compress(tbuffer.getvalue(), compresslevel=9, mtime=0)


def build(root, destination):
    files = public_files(root)
    windows, linux = archives(files)
    # The small outer bootstrap is encoded so cmd metacharacters/path spaces cannot alter it.
    script = r"""$ErrorActionPreference='Stop'; $ProgressPreference='SilentlyContinue'; $work=Join-Path ([IO.Path]::GetTempPath()) ('ia-hub-setup.'+[guid]::NewGuid().ToString('N')); $code=1
try {
$env:PSModulePath=($PSHOME+'\Modules;'+[Environment]::GetFolderPath('MyDocuments')+'\WindowsPowerShell\Modules;'+$env:ProgramFiles+'\WindowsPowerShell\Modules')
New-Item -ItemType Directory -Path $work | Out-Null
$text=[IO.File]::ReadAllText($env:IA_HUB_PORTABLE_FILE)
$marker='__IA_HUB_'+'PAYLOAD__'
$data=[Convert]::FromBase64String(($text -split ('(?m)^'+$marker+'\r?$'),2)[1])
$sha=[Security.Cryptography.SHA256]::Create(); $hash=([BitConverter]::ToString($sha.ComputeHash($data))).Replace('-','').ToLowerInvariant(); $sha.Dispose()
if($hash -ne '@@SHA256@@') { throw 'Pacote corrompido (SHA256).' }
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
""".replace('@@SHA256@@', hashlib.sha256(windows).hexdigest())
    encoded = base64.b64encode(script.encode('utf-16-le')).decode()
    if len(encoded) > 7600:
        raise ValueError('Bootstrap excedeu o limite do cmd.exe.')
    cmd = '@echo off\r\nsetlocal\r\nset "IA_HUB_PORTABLE_FILE=%~f0"\r\nset "IA_HUB_PORTABLE_MODE="\r\n'
    cmd += 'if /I "%~1"=="--help" (echo Uso: instalar.cmd [--cli ou --preview ou --self-test] & exit /b 0)\r\n'
    for flag in ('--cli', '--preview', '--self-test'):
        cmd += f'if /I "%~1"=="{flag}" set "IA_HUB_PORTABLE_MODE={flag}"\r\n'
    cmd += 'if not "%~1"=="" if "%IA_HUB_PORTABLE_MODE%"=="" (echo Use --cli, --preview ou --self-test. & exit /b 1)\r\n'
    cmd += 'powershell.exe -NoProfile -OutputFormat Text -ExecutionPolicy Bypass -EncodedCommand ' + encoded + '\r\nexit /b %errorlevel%\r\n__IA_HUB_PAYLOAD__\r\n'
    cmd += '\r\n'.join(base64.b64encode(windows).decode()[i:i+120] for i in range(0, len(base64.b64encode(windows)), 120)) + '\r\n'
    shell = (root / 'scripts/portable/wrapper.sh.in').read_text(encoding='utf-8').replace('@@SHA256@@', hashlib.sha256(linux).hexdigest())
    shell += '\n'.join(base64.b64encode(linux).decode()[i:i+120] for i in range(0, len(base64.b64encode(linux)), 120)) + '\n'
    destination.mkdir(parents=True, exist_ok=True)
    (destination / 'instalar.cmd').write_bytes(cmd.encode('ascii'))
    (destination / 'instalar.sh').write_bytes(shell.encode('utf-8'))
    (destination / 'instalar.sh').chmod(0o755)
    return {'files': len(files) - 1, 'windows_bytes': len(cmd), 'linux_bytes': len(shell.encode('utf-8'))}


if __name__ == '__main__':
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--output', type=Path, default=ROOT / 'dist')
    args = parser.parse_args()
    print(json.dumps(build(ROOT, args.output), ensure_ascii=False))
