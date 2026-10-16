import hmac
import json
import os
import secrets
import threading
import time
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path
from .client import ROOT, STATE, PORT
from .core import Memory, now
from .capture import Capture
from .opencode_capture import OpenCodeCapture


def main():
    STATE.mkdir(parents=True, exist_ok=True)
    if (STATE / 'migration.lock').exists():
        return
    token_path = STATE / 'token'
    if not token_path.exists():
        try:
            with token_path.open('x', encoding='utf-8') as f:
                f.write(secrets.token_urlsafe(32))
        except FileExistsError:
            pass
    token = token_path.read_text(encoding='utf-8').strip()
    if os.name != 'nt':
        STATE.chmod(0o700)
        token_path.chmod(0o600)
    memory = Memory(ROOT)
    capture = Capture(memory)
    opencode = OpenCodeCapture(memory)
    from .policy import Router
    from .executor import Executor
    from .native import Native
    router = Router(ROOT)
    executor = Executor(memory, ROOT)
    native = Native(memory, router)
    state = {'pid': os.getpid(), 'started': now(), 'semantic_state': 'loading', 'model': '', 'last_error': '', 'last_scan': '', 'automatic_capture': ['claude', 'codex', 'opencode', 'antigravity-hooks']}

    def dispatch(action, args):
        if action == 'shutdown':
            threading.Timer(.2, server.shutdown).start()
            return {'stopping': True}
        if action == 'store':
            result = memory.store(**args)
            return result
        if action == 'search':
            return memory.search(**args)
        if action == 'get':
            return memory.get(**args)
        if action == 'relate':
            return memory.relate(**args)
        if action == 'reconcile':
            memory.reconcile()
            return memory.health()
        if action == 'health':
            return {**memory.health(), **state, 'root': str(ROOT), 'orchestration': {'build': 'distributed-v1', 'native_model_control': ['claude-code-mod'], 'dispatch': ['claude-code', 'codex', 'antigravity'], 'memory_only': ['opencode'], 'quality': 'measured_only_with_validator'}}
        if action.startswith('orchestration_') and str(args.get('client', '')).casefold() == 'opencode':
            raise ValueError('OpenCode usa apenas a memória compartilhada; orquestração desativada por desenho.')
        if action == 'orchestration_plan':
            return router.plan(**args)
        if action == 'orchestration_submit':
            return executor.submit(**args)
        if action == 'orchestration_status':
            return executor.status(**args)
        if action == 'orchestration_report':
            return executor.report(**args)
        if action == 'orchestration_native':
            return native.handle(**args)
        if action == 'validation_session':
            return memory.mark_validation_session(**args)
        if action == 'context':
            return memory.context(**args)
        if action == 'observe':
            text = args['content']
            if len(text.strip()) < 40:
                return {'skipped': 'short'}
            return memory.store(args.get('title', text[:120]), text, project=args.get('project', ''), source=args['source'], key=args.get('key', ''), kind='session-observation', tags=['sessão', args['source']], status='reported')
        if action == 'capture':
            path = Path(args['path']).resolve()
            allowed = [Path.home() / '.claude' / 'projects', Path.home() / '.codex' / 'sessions', Path.home() / '.gemini']
            if not any(path.is_relative_to(root) for root in allowed):
                raise ValueError('Caminho de transcript fora das origens permitidas.')
            return {'captured': capture.ingest(path, args['client'], args.get('project', ''))}
        raise ValueError('Ação desconhecida.')

    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def do_POST(self):
            if self.path != '/rpc' or not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send_error(403)
                return
            size = int(self.headers.get('Content-Length', '0'))
            if size < 1 or size > 256000:
                self.send_error(413)
                return
            try:
                body = json.loads(self.rfile.read(size))
                result = {'result': dispatch(body['action'], body.get('arguments', {}))}
                code = 200
            except Exception as error:
                state['last_error'] = f'{type(error).__name__}: {str(error)[:160]}'
                result, code = {'error': state['last_error']}, 400
            data = json.dumps(result, ensure_ascii=False).encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', 'application/json; charset=utf-8')
            self.send_header('Content-Length', str(len(data)))
            self.end_headers()
            self.wfile.write(data)

    server = ThreadingHTTPServer(('127.0.0.1', PORT), Handler)
    # Servidor ocupa a porta antes da inicialização do modelo, evitando dois workers.
    def background():
        try:
            first = not (STATE / 'capture-initialized').exists()
            if os.environ.get('IA_HUB_TEST_NO_CAPTURE') != '1':
                capture.watch(baseline=first)
            (STATE / 'capture-initialized').touch()
            memory.reconcile()
        except Exception as error:
            state['last_error'] = type(error).__name__ + ': ' + str(error)[:160]
        try:
            if os.environ.get('IA_HUB_TEST_NO_EMBEDDINGS') == '1':
                raise RuntimeError('Embeddings desligados somente neste teste isolado.')
            from .embeddings import Embeddings, MODEL
            embedder = Embeddings(STATE)
            embedder('inicialização da memória compartilhada')
            with memory.lock:
                memory.embedder = embedder
                memory.backfill_vectors()
            state.update(semantic_state='ready', model=MODEL)
        except Exception as error:
            state.update(semantic_state='failed', last_error=type(error).__name__ + ': ' + str(error)[:160])
        while True:
            try:
                if os.environ.get('IA_HUB_TEST_NO_CAPTURE') != '1':
                    capture.watch()
                    opencode.scan()
                memory.reconcile()
                memory.backup()
                state['last_scan'] = now()
                state['last_error'] = ''
            except Exception as error:
                state['last_error'] = type(error).__name__ + ': ' + str(error)[:160]
            time.sleep(10)
    threading.Thread(target=background, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
