"""Deployment of the public payload. Never includes the user's memory or credentials."""
import hashlib
import json
import os
import shutil
import tempfile
from contextlib import contextmanager
from datetime import datetime
from pathlib import Path, PurePosixPath

PERSONAL = {'regras', 'modelos', 'claude', 'opencode', 'chatgpt', '.obsidian'}


def payload_files(source):
    manifest = json.loads((source / 'payload-manifest.json').read_text(encoding='utf-8'))
    result = []
    for name, digest in manifest['files'].items():
        relative = PurePosixPath(name)
        if relative.is_absolute() or '..' in relative.parts or '\\' in name or ':' in name:
            raise ValueError('Caminho inválido no pacote.')
        path = source.joinpath(*relative.parts)
        if path.is_symlink() or not path.is_file() or not path.resolve().is_relative_to(source.resolve()):
            raise ValueError('Arquivo inválido no pacote: ' + name)
        if hashlib.sha256(path.read_bytes()).hexdigest() != digest:
            raise ValueError('Integridade inválida: ' + name)
        result.append((relative, path))
    required = {'install.ps1', 'instalar.sh', 'scripts/memory/entry.py', 'scripts/setup_ui/web/index.html'}
    if not required <= {str(p) for p, _ in result}:
        raise ValueError('Pacote incompleto.')
    return result


def deploy(source, target, log):
    files = payload_files(source)
    target = target.resolve()
    # Reject redirected subdirectories before copying anything.
    for relative, _ in files:
        dest = target.joinpath(*relative.parts)
        if not dest.resolve().is_relative_to(target) or dest.is_symlink():
            raise ValueError('Destino redirecionado; nenhum arquivo foi alterado: ' + str(dest))
    from .maintenance import stop_memory
    stop_memory(target, log)
    backup = target / 'contexto/.setup/backups' / datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    if not backup.resolve().is_relative_to(target):
        raise ValueError('Pasta de backup redirecionada; instalação interrompida.')
    for relative, path in files:
        dest = target.joinpath(*relative.parts)
        if dest.exists():
            if relative.parts[0] in PERSONAL or str(relative) in ('README.md', '.gitignore'):
                continue
            if dest.read_bytes() == path.read_bytes():
                continue
            saved = backup.joinpath(*relative.parts)
            saved.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(dest, saved)
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, dest)
        if dest.suffix == '.sh':
            dest.chmod(0o700)
    log('info', 'Código instalado em ' + str(target) + '. Regras pessoais e memória preservadas.')
    if backup.exists():
        log('info', 'Backup do código anterior: ' + str(backup))


@contextmanager
def worker_environment(root):
    # uv's Python base MUST survive extraction cleanup (venvs reference it).
    with tempfile.TemporaryDirectory(prefix='ia-hub-worker-') as directory:
        env = dict(os.environ)
        env.update(IA_HUB_WORK_DIR=directory, UV_CACHE_DIR=str(Path(directory) / 'cache'),
                   UV_PYTHON_INSTALL_DIR=str(root / '.tools/python'), UV_PYTHON_PREFERENCE='only-managed',
                   UV_LINK_MODE='copy', PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1',
                   IA_HUB_UI_WORKER='1')
        temporary = Path(directory) / 'tmp'
        temporary.mkdir()
        env.update(TMPDIR=str(temporary), TEMP=str(temporary), TMP=str(temporary))
        env.pop('UV_INSTALL_DIR', None)
        yield env
