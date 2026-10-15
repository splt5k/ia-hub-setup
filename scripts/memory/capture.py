"""Somente mensagens finais; nunca raciocínio, prompts ou saídas de ferramentas."""
import json
import time
from datetime import datetime
from pathlib import Path
from .core import digest


class Capture:
    def __init__(self, memory):
        self.memory = memory
        self.last_error = ''
        with memory.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS capture_context (path TEXT PRIMARY KEY,project TEXT)')
            c.execute('CREATE TABLE IF NOT EXISTS capture_meta (name TEXT PRIMARY KEY,value TEXT)')
            c.execute('INSERT OR IGNORE INTO capture_meta VALUES (?,?)', ('capture_since', str(time.time())))
            self.since = float(c.execute('SELECT value FROM capture_meta WHERE name=?', ('capture_since',)).fetchone()[0])

    def ingest(self, path, client, project=''):
        path = Path(path).resolve()
        if not path.exists():
            return 0
        captured = 0
        antigravity_final = ''
        with self.memory.lock:
            with self.memory.connection() as c:
                row = c.execute('SELECT offset FROM cursors WHERE path=?', (str(path),)).fetchone()
                context = c.execute('SELECT project FROM capture_context WHERE path=?', (str(path),)).fetchone()
                project = project or (context[0] if context else '')
            offset = row[0] if row else 0
            if path.stat().st_size < offset:
                offset = 0
            with path.open('rb') as stream:
                stream.seek(offset)
                for _ in range(2000):
                    start = stream.tell()
                    line = stream.readline(2 * 1024 * 1024)
                    if len(line) == 2 * 1024 * 1024 and not line.endswith(b'\n'):
                        # Anexos grandes são ignorados sem acumular seu conteúdo na memória.
                        while line and not line.endswith(b'\n'):
                            line = stream.readline(2 * 1024 * 1024)
                        if line.endswith(b'\n'):
                            continue
                    if not line or not line.endswith(b'\n'):
                        stream.seek(start)
                        break
                    try:
                        event = json.loads(line)
                    except (ValueError, UnicodeDecodeError):
                        continue
                    timestamp = event.get('timestamp') or event.get('created_at')
                    if isinstance(timestamp, str):
                        try:
                            if datetime.fromisoformat(timestamp.replace('Z', '+00:00')).timestamp() < self.since:
                                continue
                        except ValueError:
                            pass
                    text = ''
                    project = event.get('cwd') or project
                    if client == 'claude' and event.get('type') == 'assistant':
                        message = event.get('message', {})
                        if message.get('stop_reason') == 'end_turn':
                            text = '\n'.join(x.get('text', '') for x in message.get('content', []) if isinstance(x, dict) and x.get('type') == 'text')
                    elif client == 'codex':
                        payload = event.get('payload', {})
                        if event.get('type') == 'session_meta':
                            project = payload.get('cwd') or project
                        if event.get('type') == 'response_item' and payload.get('role') == 'assistant' and payload.get('phase', payload.get('channel')) in ('final_answer', 'final'):
                            text = '\n'.join(x.get('text', '') for x in payload.get('content', []) if x.get('type') == 'output_text')
                    elif client == 'antigravity' and event.get('source') == 'MODEL' and event.get('type') == 'PLANNER_RESPONSE' and event.get('status') == 'DONE':
                        antigravity_final = event.get('content', '')
                    if len(text.strip()) >= 40:
                        # Source por conteúdo idempotente, inclusive se hook e observador lerem juntos.
                        key = 'capture:' + digest(str(path) + '\n' + text)
                        first = next((x.lstrip('# -*') for x in text.splitlines() if x.strip()), 'Sessão')[:120]
                        self.memory.store(first, text, project=project, source=f'{client}:transcript:{path.name}', key=key, kind='session-observation', tags=['sessão', client], status='reported')
                        captured += 1
                offset = stream.tell()
            if len(antigravity_final.strip()) >= 40:
                key = 'capture:' + digest(str(path) + '\n' + antigravity_final)
                self.memory.store(antigravity_final.splitlines()[0][:120], antigravity_final, project=project, source=f'antigravity:transcript:{path.parent.parent.parent.name}', key=key, kind='session-observation', tags=['sessão', 'antigravity'], status='reported')
                captured += 1
            with self.memory.connection() as c:
                c.execute('INSERT OR REPLACE INTO cursors VALUES (?,?,?)', (str(path), offset, path.stat().st_size))
                c.execute('INSERT OR REPLACE INTO capture_context VALUES (?,?)', (str(path), project))
        return captured

    def watch(self, baseline=False):
        roots = [(Path.home() / '.claude' / 'projects', 'claude'), (Path.home() / '.codex' / 'sessions', 'codex')]
        count = 0
        for root, client in roots:
            if not root.exists():
                continue
            paths = sorted(root.rglob('*.jsonl'), key=lambda p: p.stat().st_mtime, reverse=True)[:48]
            for path in paths:
                with self.memory.connection() as c:
                    known = c.execute('SELECT offset FROM cursors WHERE path=?', (str(path.resolve()),)).fetchone()
                    if not known and baseline:
                        c.execute('INSERT INTO cursors VALUES (?,?,?)', (str(path.resolve()), path.stat().st_size, path.stat().st_size))
                        continue
                if not baseline and (not known or known[0] != path.stat().st_size):
                    count += self.ingest(path, client)
        return count
