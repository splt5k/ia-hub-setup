"""Gera instalar.cmd e instalar.sh autocontidos a partir de src/.

Uso:
    python tools/build.py          # reescreve instalar.cmd e instalar.sh
    python tools/build.py --check  # falha se os instaladores não refletem src/

A saída é determinística (mtime/uid zerados, ordem fixa): o mesmo src/ gera
sempre os mesmos bytes na mesma plataforma; --check compara o manifesto do payload embutido
com src/, independente da zlib, e serve de guarda de sincronia fonte <-> instalador.
"""
import base64
import gzip
import hashlib
import io
import json
import sys
import tarfile
import zipfile
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
SRC = ROOT / 'src'
TEMPLATES = Path(__file__).resolve().parent / 'templates'
MARKER = '__IA_HUB_PAYLOAD__'
SKIP_DIRS = {'__pycache__', '.memory-runtime', '.tools', 'Memoria', 'contexto', 'backups'}
SKIP_NAMES = {'payload-manifest.json', 'sync.log'}
SKIP_SUFFIX = {'.pyc', '.log'}
# Texto é normalizado para LF: o resultado não depende do autocrlf/checkout de quem gera. .cmd e binários ficam intactos.
TEXT_SUFFIX = {'.py', '.js', '.json', '.jsonc', '.md', '.html', '.css', '.ps1', '.sh', '.txt', '.lock', '.service', '.toml', ''}


CRLF, LF = bytes([13, 10]), bytes([10])


def normalize(path, data):
    return data.replace(CRLF, LF) if path.suffix in TEXT_SUFFIX else data


def lf(path):
    return (TEMPLATES / path).read_bytes().replace(CRLF, LF).decode('utf-8')


def source_files():
    files = []
    for path in sorted(SRC.rglob('*')):
        relative = path.relative_to(SRC)
        if not path.is_file() or SKIP_DIRS & set(relative.parts) or path.name in SKIP_NAMES or path.suffix in SKIP_SUFFIX:
            continue
        files.append((relative.as_posix(), normalize(path, path.read_bytes())))
    return files


def manifest(files):
    return json.dumps({'files': {name: hashlib.sha256(data).hexdigest() for name, data in files}, 'schema': 1}).encode()


def build_targz(files):
    raw = io.BytesIO()
    with gzip.GzipFile(fileobj=raw, mode='wb', mtime=0, compresslevel=9) as gz:
        with tarfile.open(fileobj=gz, mode='w', format=tarfile.PAX_FORMAT) as tar:
            for name, data in sorted(files + [('payload-manifest.json', manifest(files))]):
                info = tarfile.TarInfo(name)
                info.size, info.mtime, info.uid, info.gid, info.uname, info.gname = len(data), 0, 0, 0, '', ''
                info.mode = 0o755 if name.endswith('.sh') else 0o644
                tar.addfile(info, io.BytesIO(data))
    return raw.getvalue()


def build_zip(files):
    raw = io.BytesIO()
    with zipfile.ZipFile(raw, 'w', zipfile.ZIP_DEFLATED, compresslevel=9) as archive:
        for name, data in sorted(files + [('payload-manifest.json', manifest(files))]):
            info = zipfile.ZipInfo(name, (1980, 1, 1, 0, 0, 0))
            info.compress_type, info.external_attr = zipfile.ZIP_DEFLATED, 0o644 << 16
            archive.writestr(info, data)
    return raw.getvalue()


def wrap(data):
    text = base64.b64encode(data).decode()
    return '\n'.join(text[i:i + 76] for i in range(0, len(text), 76)) + '\n'


def build():
    files = source_files()
    tar_gz, zip_data = build_targz(files), build_zip(files)
    header_sh = lf('header.sh').replace('{{SHA256}}', hashlib.sha256(tar_gz).hexdigest())
    installer_sh = (header_sh + MARKER + '\n' + wrap(tar_gz)).encode()
    ps = lf('bootstrap.ps1').replace('{{SHA256}}', hashlib.sha256(zip_data).hexdigest())
    encoded = base64.b64encode(ps.encode('utf-16le')).decode()
    prefix = lf('cmd-prefix.txt').replace(chr(10), chr(13) + chr(10))
    command = lf('cmd-powershell.txt').rstrip(chr(10))
    body = wrap(zip_data).replace('\n', '\r\n')
    installer_cmd = (prefix + command + encoded + '\r\nexit /b %errorlevel%\r\n' + MARKER + '\r\n' + body).encode('latin-1')
    return {'instalar.sh': installer_sh, 'instalar.cmd': installer_cmd}


def in_sync(name, expected_manifest):
    # Compara conteúdo, não bytes comprimidos: zlib difere entre plataformas/versões do Python.
    path = ROOT / name
    if not path.exists():
        return False
    text = path.read_bytes().decode('latin-1')
    head, sep, body = text.rpartition(MARKER)
    if not sep:
        return False
    archive = base64.b64decode(''.join(body.split()))
    if name.endswith('.sh'):
        if hashlib.sha256(archive).hexdigest() not in head:
            return False
        with tarfile.open(fileobj=io.BytesIO(archive), mode='r:gz') as tar:
            embedded = tar.extractfile('payload-manifest.json').read()
    else:
        with zipfile.ZipFile(io.BytesIO(archive)) as archive_zip:
            embedded = archive_zip.read('payload-manifest.json')
    return json.loads(embedded) == json.loads(expected_manifest)


def main():
    if '--check' in sys.argv:
        expected = manifest(source_files())
        stale = [n for n in ('instalar.sh', 'instalar.cmd') if not in_sync(n, expected)]
        if stale:
            print('Instaladores fora de sincronia com src/: ' + ', '.join(stale) + '. Rode python tools/build.py.')
            return 1
        print('Instaladores em sincronia com src/.')
        return 0
    outputs = build()
    for name, data in outputs.items():
        (ROOT / name).write_bytes(data)
        print(f'{name}: {len(data):,} bytes')
    return 0


if __name__ == '__main__':
    raise SystemExit(main())
