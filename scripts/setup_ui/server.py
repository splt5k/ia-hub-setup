import argparse
import hmac
import json
import secrets
import sys
import threading
import time
import webbrowser
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from setup_ui.actions import Controller


def make_server(controller, port=0):
    token = secrets.token_urlsafe(32)
    assets = Path(__file__).with_name('web')
    class Handler(BaseHTTPRequestHandler):
        def log_message(self, *args):
            pass

        def send(self, code, content, content_type='application/json; charset=utf-8'):
            data = content if isinstance(content, bytes) else content.encode('utf-8')
            self.send_response(code)
            self.send_header('Content-Type', content_type)
            self.send_header('Content-Length', str(len(data)))
            self.send_header('Cache-Control', 'no-store')
            self.send_header('X-Content-Type-Options', 'nosniff')
            self.send_header('Content-Security-Policy', "default-src 'self'; script-src 'self'; style-src 'self'; img-src 'self' data:; connect-src 'self'; frame-ancestors 'none'")
            self.end_headers()
            self.wfile.write(data)

        def authorize(self):
            expected = '127.0.0.1:' + str(self.server.server_port)
            if self.headers.get('Host') != expected:
                self.send(403, '{"error":"Host inválido"}')
                return False
            if not hmac.compare_digest(self.headers.get('Authorization', ''), 'Bearer ' + token):
                self.send(403, '{"error":"Sessão não autorizada"}')
                return False
            self.server.last_activity = time.monotonic()
            return True

        def do_GET(self):
            if self.path.startswith('/api/'):
                if not self.authorize():
                    return
                if self.path == '/api/state':
                    self.send(200, json.dumps(controller.snapshot(), ensure_ascii=False))
                elif self.path in ('/api/export.json', '/api/export.txt'):
                    kind = self.path.rsplit('.', 1)[1]
                    self.send(200, controller.export(kind), 'text/plain; charset=utf-8' if kind == 'txt' else 'application/json; charset=utf-8')
                else:
                    self.send(404, '{}')
                return
            files = {'/': ('index.html', 'text/html'), '/app.js': ('app.js', 'application/javascript'), '/styles.css': ('styles.css', 'text/css')}
            if self.path not in files:
                self.send(404, '{}')
                return
            file, mime = files[self.path]
            self.send(200, (assets / file).read_bytes(), mime + '; charset=utf-8')

        def do_POST(self):
            if not self.authorize():
                return
            if self.headers.get('Origin') != f'http://127.0.0.1:{self.server.server_port}':
                self.send(403, '{"error":"Origem inválida"}')
                return
            try:
                size = int(self.headers.get('Content-Length', '0'))
                if not 0 < size <= 16384 or self.headers.get('Content-Type') != 'application/json':
                    raise ValueError('Corpo inválido.')
                body = json.loads(self.rfile.read(size))
                if self.path == '/api/action':
                    controller.start(body['action'], body.get('components'), body.get('confirmed') is True)
                    self.send(202, '{"accepted":true}')
                elif self.path == '/api/close':
                    if controller.snapshot()['job']['status'] == 'running':
                        raise RuntimeError('Aguarde a operação terminar antes de fechar.')
                    self.send(200, '{"closed":true}')
                    threading.Thread(target=self.server.shutdown, daemon=True).start()
                else:
                    self.send(404, '{}')
            except (ValueError, KeyError, RuntimeError, PermissionError) as error:
                self.send(400, json.dumps({'error': str(error)}, ensure_ascii=False))
    server = ThreadingHTTPServer(('127.0.0.1', port), Handler)
    server.daemon_threads = True
    server.last_activity = time.monotonic()
    server.token = token
    return server


def main(argv=None):
    parser = argparse.ArgumentParser()
    parser.add_argument('--root', type=Path, default=Path(__file__).resolve().parents[2])
    parser.add_argument('--payload', type=Path)
    parser.add_argument('--preview', action='store_true')
    parser.add_argument('--no-browser', action='store_true')
    parser.add_argument('--session-file', type=Path)
    args = parser.parse_args(argv)
    controller = Controller(args.root, preview=args.preview, payload=args.payload)
    server = make_server(controller)
    url = f'http://127.0.0.1:{server.server_port}/#{server.token}'
    if args.session_file:
        args.session_file.parent.mkdir(parents=True, exist_ok=True)
        args.session_file.write_text(json.dumps({'url': url, 'port': server.server_port}), encoding='utf-8')
        args.session_file.chmod(0o600)
    print('IA-Hub: interface local disponível em http://127.0.0.1:' + str(server.server_port), flush=True)
    if not args.no_browser:
        webbrowser.open(url)
    def idle():
        while True:
            time.sleep(30)
            if time.monotonic() - server.last_activity > 1800 and controller.snapshot()['job']['status'] != 'running':
                server.shutdown()
                return
    threading.Thread(target=idle, daemon=True).start()
    try:
        server.serve_forever()
    finally:
        server.server_close()
        if args.session_file:
            args.session_file.unlink(missing_ok=True)
    return controller.snapshot()['job']['exit_code'] or 0


if __name__ == '__main__':
    raise SystemExit(main())
