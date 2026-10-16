"""Complementa o plugin quando o CLI encerra antes de concluir callbacks assíncronos.

Somente leitura do banco local; schema verificado na versão 1.18.33.
"""
import json
import os
import sqlite3
import time
from pathlib import Path
from .core import digest


class OpenCodeCapture:
    def __init__(self, memory):
        self.memory = memory
        data = Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share')
        self.path = data / 'opencode/opencode.db'
        with memory.connection() as c:
            c.execute('CREATE TABLE IF NOT EXISTS capture_meta (name TEXT PRIMARY KEY,value TEXT)')
            fresh = c.execute('INSERT OR IGNORE INTO capture_meta VALUES (?,?)', ('opencode_since', str(int(time.time() * 1000)))).rowcount
            if fresh:
                c.execute("INSERT OR REPLACE INTO capture_meta VALUES ('opencode_fresh_baseline','1')")

    def scan(self):
        if not self.path.exists():
            return 0
        with self.memory.connection() as c:
            legacy = int(c.execute('SELECT value FROM capture_meta WHERE name=?', ('opencode_since',)).fetchone()[0])
            cursor = c.execute("SELECT value FROM capture_meta WHERE name='opencode_cursor'").fetchone()
            # Old timestamp-only cursors can have lost ties at any prior page.
            # Migrate once by replaying the source, with existing stable keys
            # deduplicating stored text. Fresh installs retain their time cutoff.
            fresh = c.execute("SELECT 1 FROM capture_meta WHERE name='opencode_fresh_baseline'").fetchone()
            since, after_id = json.loads(cursor[0]) if cursor else (max(0, legacy - 1) if fresh else 0, '')
        db = sqlite3.connect(self.path.as_uri() + '?mode=ro', uri=True, timeout=2)
        db.row_factory = sqlite3.Row
        try:
            rows = db.execute("SELECT m.id,m.session_id,m.data,s.directory FROM message m JOIN session s ON s.id=m.session_id WHERE json_extract(m.data,'$.role')='assistant' AND (json_extract(m.data,'$.time.completed')>? OR (json_extract(m.data,'$.time.completed')=? AND m.id>?)) ORDER BY json_extract(m.data,'$.time.completed'),m.id LIMIT 100", (since, since, after_id)).fetchall()
            last = (since, after_id)
            count = 0
            for row in rows:
                info = json.loads(row['data'])
                completed = int(info['time']['completed'])
                last = (completed, row['id'])
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
                    c.execute('INSERT OR REPLACE INTO capture_meta VALUES (?,?)', ('opencode_cursor', json.dumps(last)))
            return count
        finally:
            db.close()
