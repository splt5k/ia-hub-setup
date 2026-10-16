import copy
from contextlib import nullcontext
import json
import os
import re
import shutil
import sqlite3
import subprocess
import threading
from datetime import datetime
from pathlib import Path
from .diagnostics import discover, rpc

COMPONENTS = {'runtime', 'integrations', 'claude', 'codex', 'agy', 'opencode', 'desktop'}
PHASES = [('diagnostic', 'Diagnóstico'), ('runtime', 'Dependências'), ('clients', 'Aplicativos e CLIs'),
          ('config', 'Configurações'), ('memory', 'Memória compartilhada'), ('validate', 'Validação')]


def redact(text):
    text = re.sub(r'\x1b\[[0-?]*[ -/]*[@-~]', '', str(text))
    text = re.sub(r'(?i)(Bearer\s+)\S+', r'\1[REMOVIDO]', text)
    text = re.sub(r'''(?i)(["']?(?:api[_-]?key|password|senha|secret|access[_-]?token|refresh[_-]?token|token)["']?\s*[:=]\s*)(?:["'][^"']*["']|[^\s,;}]+)''', r'\1[REMOVIDO]', text)
    return re.sub(r'\b(?:sk-[A-Za-z0-9_-]{20,}|gh[pousr]_[A-Za-z0-9]{20,})\b', '[REMOVIDO]', text)


class Controller:
    def __init__(self, root, preview=False, payload=None):
        self.payload = payload
        self.root, self.preview = root.resolve(), preview
        self.lock = threading.RLock()
        self.diagnostic = discover(self.root)
        self.job = {'status': 'idle', 'action': '', 'steps': [], 'logs': [], 'exit_code': None}
        self.log('info', f"{self.diagnostic.get('system', {}).get('os', os.name)} · diagnóstico inicial concluído.")
        self.log('info', 'Pasta identificada: ' + self.diagnostic['root'])
        health = self.diagnostic.get('health', {})
        if health:
            self.log('success', f"Memória respondeu: {health.get('records', 0)} registros · integridade {health.get('database_integrity', '?')}.")
        if preview:
            self.log('info', 'Prévia ativa: operações que alteram a máquina estão bloqueadas.')

    def log(self, level, message):
        with self.lock:
            self.job['logs'].append({'time': datetime.now().strftime('%H:%M:%S'), 'level': level, 'message': redact(message)[:4000]})

    def snapshot(self, full=False):
        def clean(value):
            if isinstance(value, str):
                return redact(value)
            if isinstance(value, dict):
                return {k: clean(v) for k, v in value.items()}
            if isinstance(value, list):
                return [clean(v) for v in value]
            return value
        with self.lock:
            job = {**self.job, 'logs': self.job['logs'] if full else self.job['logs'][-600:], 'log_total': len(self.job['logs'])}
            return clean(copy.deepcopy({'preview': self.preview, 'diagnostic': self.diagnostic, 'job': job}))

    def phase(self, name, status='running'):
        with self.lock:
            for step in self.job['steps']:
                if step['id'] == name:
                    step['status'] = status

    def start(self, action, components=None, confirmed=False):
        if action not in ('verify', 'install', 'repair', 'reinstall', 'remove'):
            raise ValueError('Ação desconhecida.')
        selected = set(components or [])
        if not selected <= COMPONENTS or action == 'reinstall' and not selected:
            raise ValueError('Selecione componentes válidos.')
        with self.lock:
            if self.job['status'] == 'running':
                raise RuntimeError('Já existe uma operação em andamento.')
            if action != 'verify' and (self.preview or self.diagnostic.get('foreign')):
                raise PermissionError('Alterações bloqueadas nesta prévia/cópia. Use a pasta da instalação ativa.')
            if action in ('remove', 'reinstall') and not confirmed:
                raise PermissionError('Confirme a operação e os componentes na interface.')
            phases = [('diagnostic', 'Diagnóstico'), ('validate', 'Verificação')] if action == 'verify' else [('diagnostic', 'Diagnóstico'), ('config', 'Remover registros'), ('memory', 'Preservar memória')] if action == 'remove' else PHASES
            self.job = {'status': 'running', 'action': action, 'steps': [{'id': k, 'label': v, 'status': 'pending'} for k, v in phases], 'logs': [], 'exit_code': None}
            threading.Thread(target=self._run, args=(action, selected), daemon=True).start()

    def _run(self, action, selected):
        try:
            self.phase('diagnostic')
            self.log('info', 'Verificando a instalação e a propriedade do serviço local...')
            self.diagnostic = discover(self.root)
            if action != 'verify' and self.diagnostic.get('foreign'):
                raise PermissionError('Outra instalação foi identificada. Abra a pasta ativa antes de alterar o ambiente.')
            self.phase('diagnostic', 'done')
            if action == 'verify':
                self.phase('validate')
                active_root = Path(self.diagnostic['root'])
                database = active_root / 'contexto/.memory/memory.sqlite3'
                if database.exists():
                    with sqlite3.connect(database.resolve().as_uri() + '?mode=ro', uri=True, timeout=5) as connection:
                        result = connection.execute('PRAGMA quick_check').fetchone()[0]
                    if result != 'ok':
                        raise RuntimeError('Integridade do banco: ' + result)
                    self.log('success', 'Banco íntegro (consulta somente leitura).')
                health = self.diagnostic.get('health', {})
                if health:
                    self.log('success', f"Serviço disponível · busca semântica {health.get('semantic_state', 'desconhecida')}.")
                else:
                    self.log('warning', 'Serviço não respondeu. A verificação não inicia nem modifica a memória.')
                pending = not health or health.get('semantic_state') != 'ready' or health.get('projection_conflicts') or health.get('pending_projections') or health.get('last_error')
                if pending and health:
                    self.log('warning', 'Há pendências na memória: modelo semântico, projeções ou erro do serviço. Consulte o relatório.')
                self.phase('validate', 'done')
                code = 2 if pending else 0
            elif action == 'remove':
                from .maintenance import remove_integration
                self.phase('config')
                result = remove_integration(self.root, self.log)
                self.phase('config', 'done')
                self.phase('memory', 'done')
                self.log('success', 'Integração removida. Aplicativos, banco, notas e histórico preservados.')
                self.log('info', 'Backup: ' + result['backup'])
                code = 0
            else:
                if self.payload:
                    from .portable import deploy
                    deploy(self.payload, self.root, self.log)
                if action == 'reinstall' and 'runtime' in selected:
                    from .maintenance import backup_runtime
                    backup_runtime(self.root, self.log)
                env = dict(os.environ, PYTHONIOENCODING='utf-8', PYTHONUNBUFFERED='1', IA_HUB_UI_WORKER='1')
                from .portable import worker_environment
                with worker_environment(self.root) if self.payload else nullcontext(env) as env:
                    if action == 'reinstall':
                        env['IA_HUB_COMPONENTS'] = ','.join(sorted(selected))
                        env['IA_HUB_FORCE_COMPONENTS'] = env['IA_HUB_COMPONENTS']
                    command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(self.root / 'install.ps1')] if os.name == 'nt' else ['bash', str(self.root / 'instalar.sh'), '--cli', '--desktop' if os.environ.get('IA_HUB_INSTALL_MODE') == 'desktop' else '--headless']
                    self.log('info', 'Executando o instalador compartilhado. Componentes existentes e dados serão preservados.')
                    worker = subprocess.Popen(command, cwd=self.root, env=env, stdout=subprocess.PIPE, stderr=subprocess.STDOUT, text=True, encoding='utf-8', errors='replace', creationflags=subprocess.CREATE_NO_WINDOW if os.name == 'nt' else 0)
                    for line in worker.stdout:
                        if line.startswith('IA_HUB_EVENT:'):
                            try:
                                event = json.loads(line.split(':', 1)[1])
                                self.phase(event['phase'], event.get('status', 'running'))
                                continue
                            except (ValueError, KeyError):
                                pass
                        line = line.strip()
                        if line:
                            level = 'error' if re.search(r'(?i)falha|failed|exception', line) else 'info'
                            self.log(level, line)
                    code = worker.wait()
                    if code not in (0, 2):
                        raise RuntimeError(f'Instalador terminou com código {code}. Consulte o log para corrigir e tentar novamente.')
                    if code == 2:
                        self.log('warning', 'Instalação parcial: há componentes pendentes no relatório.')
            refreshed = discover(self.root)
            self.log('success' if code == 0 else 'warning', 'Operação concluída.' if code == 0 else 'Operação concluída com pendências.')
            with self.lock:
                self.diagnostic = refreshed
                self.job['status'] = 'completed' if code == 0 else 'partial'
                self.job['exit_code'] = code
        except Exception as error:
            self.log('error', str(error))
            with self.lock:
                self.job['status'] = 'failed'
                self.job['exit_code'] = 1
                for step in self.job['steps']:
                    if step['status'] == 'running':
                        step['status'] = 'failed'

    def export(self, kind='json'):
        state = self.snapshot(full=True)
        if kind == 'txt':
            return '\n'.join(f"[{r['time']}] {r['level'].upper()}: {r['message']}" for r in state['job']['logs'])
        return json.dumps(state, ensure_ascii=False, indent=2)
