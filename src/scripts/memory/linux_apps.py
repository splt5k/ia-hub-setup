"""Official Linux desktop packages, only when requested by a graphical session."""
import hashlib
import json
import os
import platform
import shlex
import shutil
import subprocess
import sys
import tarfile
import tempfile
import time
import urllib.parse
import urllib.request
from pathlib import Path
from .client import ROOT, STATE
from .linux import config_home


def download(url, path, expected=''):
    path.parent.mkdir(parents=True, exist_ok=True)
    digest = hashlib.sha256()
    with urllib.request.urlopen(urllib.request.Request(url, headers={'User-Agent': 'IA-Hub-Setup'}), timeout=90) as response, path.open('wb') as target:
        while data := response.read(1024 * 1024):
            digest.update(data)
            target.write(data)
    if expected and digest.hexdigest() != expected:
        raise RuntimeError('SHA256 divergente: ' + path.name)


def missing_libraries(binary):
    if not binary.is_file():
        return 'Executável removido: ' + str(binary)
    if shutil.which('ldd'):
        libs = subprocess.run(['ldd', str(binary)], capture_output=True, text=True)
        missing = [line.strip() for line in libs.stdout.splitlines() if 'not found' in line]
        if missing:
            return 'Bibliotecas gráficas ausentes: ' + '; '.join(missing)[:350]
    return ''


def portable(name, url, candidates, digest=''):
    existing = shutil.which(name)
    if existing and not existing.startswith('/mnt/'):
        path = Path(existing)
        if path.parent == Path.home() / '.local/bin':
            with path.open('rb') as stream:
                prefix = stream.read(8192).decode('utf-8', errors='replace').replace('\r\n', '\n')
            if prefix.startswith('#!/bin/sh\n# IA-Hub managed launcher\nexec '):
                binary = Path(shlex.split(prefix.splitlines()[2])[1])
                pending = missing_libraries(binary)
                if pending:
                    return {'name': name, 'state': 'pending', 'detail': pending}
        return {'name': name, 'state': 'present', 'detail': 'Instalação existente preservada; abertura não testada'}
    home = Path.home()
    archive = Path(os.environ.get('IA_HUB_WORK_DIR') or ROOT / '.tools') / (name + '.tar.gz')
    download(url, archive, digest)
    apps = Path(os.environ.get('XDG_DATA_HOME') or home / '.local/share') / 'ia-hub/apps'
    apps.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix=name + '-', dir=apps) as temp:
        stage = Path(temp)
        with tarfile.open(archive) as bundle:
            bundle.extractall(stage, filter='data')
        executable = next((p for p in stage.rglob('*') if p.name in candidates and p.is_file() and os.access(p, os.X_OK)), None)
        if executable is None:
            raise RuntimeError('Executável não encontrado no pacote oficial de ' + name)
        dest = apps / (name + '-' + str(archive.stat().st_mtime_ns))
        stage.rename(dest)
        binary = dest / executable.relative_to(stage)
    launcher = home / '.local/bin' / name
    launcher.parent.mkdir(parents=True, exist_ok=True)
    launcher.write_text('#!/bin/sh\n# IA-Hub managed launcher\nexec ' + shlex.quote(str(binary)) + ' "$@"\n', encoding='utf-8')
    launcher.chmod(0o755)
    desktop = Path(os.environ.get('XDG_DATA_HOME') or home / '.local/share') / 'applications' / ('ia-hub-' + name + '.desktop')
    desktop.parent.mkdir(parents=True, exist_ok=True)
    escaped = str(launcher).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%').replace('$', '\\$').replace('`', '\\`')
    arguments = ''
    if name == 'obsidian':
        arguments = ' "obsidian://open?path=' + urllib.parse.quote(str(ROOT), safe='').replace('%', '%%') + '"'
    desktop.write_text(f'[Desktop Entry]\nType=Application\nName={name.title()} (IA-Hub)\nExec="{escaped}"{arguments}\nTerminal=false\nCategories=Development;\n', encoding='utf-8')
    pending = missing_libraries(binary)
    if pending:
        return {'name': name, 'state': 'pending', 'detail': pending}
    return {'name': name, 'state': 'installed', 'detail': 'Pacote oficial e launcher instalados; abertura gráfica e login não testados'}


def package(name, url, manager, digest=''):
    if shutil.which(name):
        return {'name': name, 'state': 'present', 'detail': 'Instalação existente preservada'}
    admin = shutil.which('sudo')
    if not admin:
        return {'name': name, 'state': 'pending', 'detail': 'Instalação oficial requer administrador/sudo'}
    file = Path(os.environ.get('IA_HUB_WORK_DIR') or ROOT / '.tools') / (name + ('.deb' if manager == 'apt-get' else '.rpm'))
    download(url, file, digest)
    elevate = [admin] if sys.stdin.isatty() else [admin, '-n']
    if manager == 'apt-get':
        subprocess.run([*elevate, 'apt-get', 'update'], check=True)
        args = ['apt-get', 'install', '-y', '--no-install-recommends', str(file)]
    else:
        args = ['dnf', 'install', '-y', str(file)]
    subprocess.run([*elevate, *args], check=True)
    return {'name': name, 'state': 'installed', 'detail': 'Login, consentimentos e recursos de virtualização não configurados'}


def register_obsidian_vault():
    # Mesmo critério do Windows: o hub entra na lista de cofres sem apagar os existentes.
    config = Path(os.environ.get('XDG_CONFIG_HOME') or Path.home() / '.config') / 'obsidian' / 'obsidian.json'
    try:
        running = subprocess.run(['pgrep', '-x', 'obsidian'], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL).returncode == 0
    except OSError:
        running = False
    if running:
        return {'name': 'Obsidian cofre', 'state': 'pending', 'detail': 'Feche o Obsidian e rode Reparar para registrar o cofre do hub'}
    try:
        data = json.loads(config.read_text(encoding='utf-8-sig')) if config.exists() else {}
    except ValueError:
        return {'name': 'Obsidian cofre', 'state': 'failed', 'detail': f'{config} não é JSON válido; cofre do hub não registrado'}
    vaults = data.setdefault('vaults', {})
    if any(v.get('path') == str(ROOT) for v in vaults.values()):
        return {'name': 'Obsidian cofre', 'state': 'present', 'detail': 'Cofre do hub já está na lista'}
    vaults[os.urandom(8).hex()] = {'path': str(ROOT), 'ts': int(time.time() * 1000), 'open': True}
    config.parent.mkdir(parents=True, exist_ok=True)
    config.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding='utf-8')
    return {'name': 'Obsidian cofre', 'state': 'installed', 'detail': f'Cofre do hub registrado: {ROOT}'}


def install_apps():
    mode = os.environ.get('IA_HUB_INSTALL_MODE', 'headless')
    try:
        distro = platform.freedesktop_os_release()
    except OSError:
        distro = {'ID': 'unknown'}
    arch = 'arm64' if platform.machine() in ('aarch64', 'arm64') else 'amd64'
    results = []
    tsv = ROOT / 'contexto/bootstrap-linux.tsv'
    if tsv.exists():
        for line in tsv.read_text(encoding='utf-8').splitlines():
            name, state, detail = line.split('\t', 2)
            results.append({'name': name, 'state': state, 'detail': detail})
    if mode == 'headless':
        results.append({'name': 'Aplicativos gráficos', 'state': 'skipped', 'detail': 'Sem sessão gráfica, SSH/WSL ou --headless/--memory-only'})
    else:
        def attempt(name, operation):
            print('Instalando/verificando ' + name + '...', flush=True)
            try:
                results.append(operation())
            except Exception as error:
                results.append({'name': name, 'state': 'failed', 'detail': str(error)[:400]})
        suffix = '-arm64' if arch == 'arm64' else ''
        sha = 'fc212804515713ed85fe5ef5bc4b009872bcc01847c4be4fcc14971deee2a42d' if suffix else 'e70b7cd63787e7f798a84fec453f5c446b91877bd3f612e8fb98e9b76cc81120'
        attempt('Obsidian', lambda: portable('obsidian', f'https://github.com/obsidianmd/obsidian-releases/releases/download/v1.14.4/obsidian-1.14.4{suffix}.tar.gz', ['obsidian'], sha))
        attempt('Obsidian cofre', register_obsidian_vault)
        agy_arch = 'arm' if arch == 'arm64' else 'x64'
        # The IDE also owns an "antigravity" command: never replace or count it as the App.
        attempt('Antigravity App', lambda: portable('antigravity-app', f'https://storage.googleapis.com/antigravity-public/antigravity-hub/2.23.1-6348059836284928/linux-{agy_arch}/Antigravity.tar.gz', ['Antigravity', 'antigravity']))
        distro_id, version = distro.get('ID', ''), distro.get('VERSION_ID', '')
        try:
            major = int(version.split('.')[0])
        except ValueError:
            major = 0
        if (distro_id == 'ubuntu' and major >= 22) or (distro_id == 'debian' and major >= 12):
            def claude():
                if shutil.which('claude-desktop'):
                    return {'name': 'claude-desktop', 'state': 'present', 'detail': 'Instalação existente preservada'}
                index = f'https://downloads.claude.ai/claude-desktop/apt/stable/dists/stable/main/binary-{arch}/Packages'
                with urllib.request.urlopen(index, timeout=60) as response:
                    paragraphs = response.read(5_000_000).decode().split('\n\n')
                records = [dict(line.split(': ', 1) for line in p.splitlines() if ': ' in line) for p in paragraphs]
                records = [r for r in records if r.get('Package') == 'claude-desktop' and r.get('Architecture') == arch]
                if not records:
                    raise RuntimeError('Pacote Claude não encontrado no índice oficial.')
                # Repository records are chronological; prefer dpkg's version comparison.
                best = records[0]
                for record in records[1:]:
                    if subprocess.run(['dpkg', '--compare-versions', record['Version'], 'gt', best['Version']]).returncode == 0:
                        best = record
                filename = best['Filename']
                if not filename.startswith('pool/main/c/claude-desktop/') or '..' in filename:
                    raise RuntimeError('Caminho inesperado no índice Claude.')
                return package('claude-desktop', 'https://downloads.claude.ai/claude-desktop/apt/stable/' + filename, 'apt-get', best['SHA256'])
            attempt('Claude Desktop', claude)
        else:
            results.append({'name': 'Claude Desktop', 'state': 'pending', 'detail': 'Pacote oficial limitado a Ubuntu 22.04+/Debian 12+; CLI configurado'})
        if (distro_id == 'ubuntu' and version in ('24.04', '26.04')) or (distro_id == 'debian' and major == 13):
            attempt('ChatGPT/Codex App', lambda: package('chatgpt', f'https://persistent.oaistatic.com/codex-app-prod/linux/deb/latest/chatgpt_{arch}.deb', 'apt-get'))
        elif distro_id == 'fedora' and major in (43, 44):
            rpm_arch = 'aarch64' if arch == 'arm64' else 'x86_64'
            attempt('ChatGPT/Codex App', lambda: package('chatgpt', f'https://persistent.oaistatic.com/codex-app-prod/linux/rpm/latest/chatgpt.{rpm_arch}.rpm', 'dnf'))
        else:
            results.append({'name': 'ChatGPT/Codex App', 'state': 'pending', 'detail': 'Sem instalação automática validada para esta distro; Codex CLI configurado'})
    report = {'platform': 'linux', 'mode': mode, 'distro': distro.get('PRETTY_NAME', distro.get('ID')), 'components': results}
    (ROOT / 'contexto/bootstrap.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')


def summary():
    report = json.loads((ROOT / 'contexto/bootstrap.json').read_text(encoding='utf-8'))
    for item in report['components']:
        print(f"{item['name']}: {item['state']} — {item['detail']}")
    print('Memória verificada. Relatórios: contexto/bootstrap.json e contexto/.memory/doctor.json.')
    print('Entre nas contas e reabra os aplicativos. Login e captura em apps gráficos não foram comprovados pelo instalador.')
    if any(item['state'] in ('failed', 'pending') for item in report['components']):
        raise SystemExit(2)
