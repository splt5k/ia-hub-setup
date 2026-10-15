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

    def test_timestamp_ties_legacy_migration_and_interrupted_replay(self):
        from memory.core import Memory
        from memory.opencode_capture import OpenCodeCapture
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            capture = OpenCodeCapture(memory)
            capture.path = root / 'ties.db'
            with memory.connection() as c:
                # Legacy cursor may have advanced beyond an earlier dropped group.
                c.execute("UPDATE capture_meta SET value='10' WHERE name='opencode_since'")
                c.execute("DELETE FROM capture_meta WHERE name='opencode_fresh_baseline'")
            with sqlite3.connect(capture.path) as c:
                c.executescript('CREATE TABLE session(id TEXT,directory TEXT); CREATE TABLE message(id TEXT,session_id TEXT,data TEXT); CREATE TABLE part(id TEXT,message_id TEXT,data TEXT,time_created INTEGER);')
                c.execute("INSERT INTO session VALUES ('s','scope')")
                for n in range(1000):
                    name = f'{n:04}'
                    c.execute('INSERT INTO message VALUES (?,?,?)', (name, 's', json.dumps({'role':'assistant','finish':'stop','time':{'completed':1}})))
                    c.execute('INSERT INTO part VALUES (?,?,?,?)', (name,name,json.dumps({'type':'text','text':'Conclusão sintética suficientemente longa para captura número '+name}),1))
            c.close()
            original = capture.path.read_bytes()
            with patch.object(memory, 'project_dirty'):
                real_store = memory.store
                calls = [0]
                def interrupted(*a, **kw):
                    calls[0] += 1
                    if calls[0] == 51:
                        raise RuntimeError('interrupção')
                    return real_store(*a, **kw)
                with patch.object(memory, 'store', side_effect=interrupted):
                    with self.assertRaises(RuntimeError):
                        capture.scan()
                self.assertEqual(capture.scan(), 100)
                for _ in range(9):
                    self.assertEqual(capture.scan(), 100)
                self.assertEqual(capture.scan(), 0)
            self.assertEqual(memory.health()['records'], 1000)
            self.assertEqual(capture.path.read_bytes(), original)

    def test_101_timestamp_ties_end_with_single_message(self):
        from memory.core import Memory
        from memory.opencode_capture import OpenCodeCapture
        from unittest.mock import patch
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            memory = Memory(root)
            capture = OpenCodeCapture(memory)
            capture.path = root / '101.db'
            with memory.connection() as c:
                c.execute("UPDATE capture_meta SET value='0' WHERE name='opencode_since'")
            with sqlite3.connect(capture.path) as c:
                c.executescript('CREATE TABLE session(id TEXT,directory TEXT); CREATE TABLE message(id TEXT,session_id TEXT,data TEXT); CREATE TABLE part(id TEXT,message_id TEXT,data TEXT,time_created INTEGER);')
                c.execute("INSERT INTO session VALUES ('s','scope')")
                for n in range(101):
                    name = str(n)
                    c.execute('INSERT INTO message VALUES (?,?,?)',(name,'s',json.dumps({'role':'assistant','finish':'stop','time':{'completed':1}})))
                    c.execute('INSERT INTO part VALUES (?,?,?,?)',(name,name,json.dumps({'type':'text','text':'Conclusão sintética suficientemente longa para captura número '+name}),1))
            c.close()
            with patch.object(memory, 'project_dirty'):
                self.assertEqual(capture.scan(),100)
                self.assertEqual(capture.scan(),1)
                self.assertEqual(capture.scan(),0)
            self.assertEqual(memory.health()['records'],101)
