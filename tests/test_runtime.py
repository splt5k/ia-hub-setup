"""Real HTTP transport, isolated files and port, no inference or production capture."""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import time
import unittest
import urllib.request
from pathlib import Path


class RuntimeTests(unittest.TestCase):
    def test_daemon_policy_native_metrics_context_and_port_isolation(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='hub-rpc-') as temp:
            root = Path(temp)
            shutil.copytree(repo/'scripts/memory', root/'scripts/memory', ignore=shutil.ignore_patterns('__pycache__', 'proof'))
            shutil.copytree(repo/'regras', root/'regras')
            with socket.socket() as sock:
                sock.bind(('127.0.0.1', 0)); port = sock.getsockname()[1]
            env = {**os.environ, 'IA_HUB_PORT': str(port), 'IA_HUB_TEST_NO_CAPTURE': '1', 'IA_HUB_TEST_NO_EMBEDDINGS': '1'}
            def rpc(action, arguments=None):
                token = (root/'contexto/.memory/token').read_text().strip()
                req = urllib.request.Request(f'http://127.0.0.1:{port}/rpc', json.dumps({'action': action, 'arguments': arguments or {}}).encode(), {'Authorization': 'Bearer '+token, 'Content-Type': 'application/json'})
                with urllib.request.urlopen(req, timeout=5) as response:
                    return json.load(response)['result']
            with (root/'server.log').open('w') as log:
                process = subprocess.Popen([sys.executable, str(root/'scripts/memory/entry.py'), 'daemon'], env=env, stdout=log, stderr=log, stdin=subprocess.DEVNULL)
                try:
                    for _ in range(60):
                        try:
                            health = rpc('health'); break
                        except OSError:
                            time.sleep(.1)
                    else:
                        self.fail('Isolated daemon failed to start')
                    self.assertEqual(Path(health['root']), root)
                    self.assertEqual(health['orchestration']['build'], 'distributed-v1')
                    rpc('store', {'title': 'Aurora', 'content': 'Aurora recupera descoberta no projeto certo.', 'project': '/aurora', 'source': 'test'})
                    self.assertEqual(rpc('context', {'query': 'Aurora', 'project': '/other'})['memories'], [])
                    run = rpc('orchestration_native', {'event': 'start', 'prompt': 'Liste Aurora', 'client': 'claude-code', 'project': '/aurora'})
                    self.assertEqual(run['decision']['model'], 'claude-haiku-5-5')
                    self.assertEqual(len(run['context']['memories']), 1)
                    attempt = dict(event='attempt', run_id=run['run_id'], event_id='step1', model_reported='claude-haiku-5-5', usage={'input_tokens': 10})
                    rpc('orchestration_native', attempt); rpc('orchestration_native', attempt)
                    rpc('orchestration_native', {'event': 'finish', 'run_id': run['run_id'], 'status': 'succeeded'})
                    report = rpc('orchestration_report', {'run_id': run['run_id']})
                    self.assertEqual(report['totals']['attempt_count'], 1)
                    self.assertFalse(report['totals']['native_children_complete'])
                    self.assertEqual(report['runs'][0]['status'], 'completed_unvalidated')
                finally:
                    try:
                        rpc('shutdown')
                        process.wait(timeout=5)
                    except (OSError, subprocess.TimeoutExpired):
                        process.kill(); process.wait(timeout=5)
