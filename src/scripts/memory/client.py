import json
import os
import socket
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'contexto' / '.memory'
DEFAULT_PORT = 43127


def read_port(state):
    """Porta da instalação: IA_HUB_PORT, senão o arquivo `port` da pasta de estado, senão o padrão."""
    value = os.environ.get('IA_HUB_PORT')
    if value is None:
        try:
            value = (Path(state) / 'port').read_text(encoding='utf-8').strip()
        except OSError:
            value = str(DEFAULT_PORT)
    port = int(value)
    if not 1024 <= port <= 65535:
        raise ValueError('A porta do IA-Hub precisa estar entre 1024 e 65535.')
    return port


PORT = read_port(STATE)
URL = f'http://127.0.0.1:{PORT}/rpc'


def _busy(port):
    try:
        with socket.create_connection(('127.0.0.1', port), timeout=2):
            return True
    except OSError:
        return False


def preflight():
    """Garante uma porta própria. Um serviço de outra instalação nunca é encerrado: usa-se outra porta."""
    global PORT, URL
    if not _busy(PORT):
        return
    try:
        if Path(request('health', autostart=False)['root']).resolve() == ROOT.resolve():
            return
    except Exception:
        pass
    if os.environ.get('IA_HUB_PORT'):
        raise RuntimeError(f'Porta {PORT} (IA_HUB_PORT) ocupada por outro serviço; escolha outra.')
    for candidate in range(DEFAULT_PORT + 1, DEFAULT_PORT + 200):
        if not _busy(candidate):
            STATE.mkdir(parents=True, exist_ok=True)
            (STATE / 'port').write_text(str(candidate), encoding='utf-8')
            PORT, URL = candidate, f'http://127.0.0.1:{candidate}/rpc'
            return
    raise RuntimeError('Nenhuma porta local livre para o IA-Hub.')


def request(action, arguments=None, autostart=True):
    token_file = STATE / 'token'
    if autostart and not token_file.exists():
        start()
    data = json.dumps({'action': action, 'arguments': arguments or {}}, ensure_ascii=False).encode('utf-8')
    for attempt in range(2):
        try:
            token = token_file.read_text(encoding='utf-8').strip()
            req = urllib.request.Request(URL, data, {'Authorization': 'Bearer ' + token, 'Content-Type': 'application/json'})
            with urllib.request.urlopen(req, timeout=90) as response:
                result = json.load(response)
            if 'error' in result:
                raise RuntimeError(result['error'])
            return result['result']
        except (urllib.error.URLError, FileNotFoundError):
            if not autostart or attempt:
                raise
            start()
    raise RuntimeError('Serviço de memória indisponível.')


def start():
    STATE.mkdir(parents=True, exist_ok=True)
    preflight()
    if (STATE / 'migration.lock').exists():
        raise RuntimeError('Memória em migração protegida; aguarde concluir antes de tentar novamente.')
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
        executable = executable.with_name('pythonw.exe')
    # O daemon sobrevive ao instalador: não pode herdar pasta temporária (o Windows impediria apagá-la).
    scratch = STATE / 'tmp'
    scratch.mkdir(parents=True, exist_ok=True)
    env = {k: v for k, v in os.environ.items() if k not in ('IA_HUB_WORK_DIR', 'IA_HUB_UI_WORKER') and not k.startswith('UV_')}
    env.update(TMPDIR=str(scratch), TEMP=str(scratch), TMP=str(scratch))
    with (STATE / 'service.log').open('a', encoding='utf-8') as log:
        subprocess.Popen([str(executable), str(Path(__file__).with_name('entry.py')), 'daemon'], cwd=ROOT, env=env, start_new_session=os.name != 'nt', stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(50):
        time.sleep(0.2)
        try:
            request('health', autostart=False)
            return
        except (OSError, RuntimeError):
            pass
    raise RuntimeError('Falha ao iniciar memória. Consulte contexto/.memory/service.log.')
