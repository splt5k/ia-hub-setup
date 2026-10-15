import json
import os
import subprocess
import sys
import time
import urllib.error
import urllib.request
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
STATE = ROOT / 'contexto' / '.memory'
URL = 'http://127.0.0.1:43127/rpc'


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
    if (STATE / 'migration.lock').exists():
        raise RuntimeError('Memória em migração protegida; aguarde concluir antes de tentar novamente.')
    executable = Path(sys.executable)
    if os.name == 'nt' and executable.with_name('pythonw.exe').exists():
        executable = executable.with_name('pythonw.exe')
    with (STATE / 'service.log').open('a', encoding='utf-8') as log:
        subprocess.Popen([str(executable), str(Path(__file__).with_name('entry.py')), 'daemon'], cwd=ROOT, stdin=subprocess.DEVNULL, stdout=log, stderr=log, creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
    for _ in range(50):
        time.sleep(0.2)
        try:
            request('health', autostart=False)
            return
        except (OSError, RuntimeError):
            pass
    raise RuntimeError('Falha ao iniciar memória. Consulte contexto/.memory/service.log.')
