"""Complementa o plugin quando o CLI encerra antes de concluir callbacks assíncronos.

Somente leitura do banco local; schema verificado na versão 1.18.33.
"""
import json
import sqlite3
import time
from pathlib import Path
from .core import digest


class OpenCodeCapture:
    def __init__(self, memory):
        self.memory = memory
        self.path = Path.home() / '.local' / 'share' / 'opencode' / 'opencode.db'
        with memory.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS capture_meta (name TEXT PRIMARY KEY,value TEXT)')
            c.execute('INSERT OR IGNORE INTO capture_meta VALUES (?,?)', ('opencode_since', str(int(time.time() * 1000))))

    def scan(self):
        if not self.path.exists():
            return 0
        with self.memory.connection() as c:
            since = int(c.execute('SELECT value FROM capture_meta WHERE name=?', ('opencode_since',)).fetchone()[0])
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute("SELECT m.id,m.session_id,m.data,s.directory FROM message m JOIN session s ON s.id=m.session_id WHERE json_extract(m.data,'$.role')='assistant' AND json_extract(m.data,'$.time.completed')>=? ORDER BY json_extract(m.data,'$.time.completed') LIMIT 100", (since,)).fetchall()
            last = since
            count = 0
            for row in rows:
                info = json.loads(row['data'])
                completed = int(info['time']['completed'])
                last = max(last, completed)
                if info.get('finish') != 'stop':
                    continue
                parts = [json.loads(p[0]) for p in db.execute('SELECT data FROM part WHERE message_id=? ORDER BY time_created,id', (row['id'],))]
                text = '\n'.join(p.get('text', '') for p in parts if p.get('type') == 'text' and not p.get('synthetic') and not p.get('ignored'))
                if len(text.strip()) < 40:
                    continue
                self.memory.store(text.splitlines()[0][:120], text, project=row['directory'], source='opencode:session:' + row['session_id'], key='opencode:' + digest(row['session_id'] + '\n' + text), kind='session-observation', tags=['sessão', 'opencode'], status='reported')
                count += 1
            if rows:
                with self.memory.connection() as c:
                    c.execute('UPDATE capture_meta SET value=? WHERE name=?', (str(last + 1), 'opencode_since'))
            return count
        finally:
            db.close()
