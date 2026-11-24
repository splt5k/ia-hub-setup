import json
import sqlite3
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class OpenCodeCaptureTests(unittest.TestCase):
    def test_readonly_final_messages_and_replay(self):
        from memory.core import Memory
        from memory.opencode_capture import OpenCodeCapture
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            capture = OpenCodeCapture(memory)
            capture.path = root / 'opencode.db'
            with memory.connection() as c:
                c.execute("UPDATE capture_meta SET value='0' WHERE name='opencode_since'")
            with sqlite3.connect(capture.path) as c:
                c.executescript('CREATE TABLE session(id TEXT,directory TEXT); CREATE TABLE message(id TEXT,session_id TEXT,data TEXT); CREATE TABLE part(id TEXT,message_id TEXT,data TEXT,time_created INTEGER);')
                c.execute('INSERT INTO session VALUES (?,?)', ('s', 'D:/Dev/projeto'))
                for item_id, finish, completed in [('intermediate', 'tool-calls', 1), ('final', 'stop', 2)]:
                    c.execute('INSERT INTO message VALUES (?,?,?)', (item_id, 's', json.dumps({'role': 'assistant', 'finish': finish, 'time': {'completed': completed}})))
                    text = 'A decisão final preserva o histórico e a origem das descobertas para permitir que ferramentas diferentes recuperem e enriqueçam o mesmo conhecimento local.'
                    c.execute('INSERT INTO part VALUES (?,?,?,?)', (item_id, item_id, json.dumps({'type': 'text', 'text': text}), completed))
                    c.execute('INSERT INTO part VALUES (?,?,?,?)', ('reason-' + item_id, item_id, json.dumps({'type': 'reasoning', 'text': 'SEGREDO'}), completed))
            c.close()
            self.assertEqual(capture.scan(), 1)
            self.assertEqual(capture.scan(), 0)
            self.assertEqual(memory.health()['records'], 1)
            self.assertEqual(memory.search('histórico')[0]['project'], 'd:/dev/projeto')
            self.assertFalse(memory.search('SEGREDO'))
