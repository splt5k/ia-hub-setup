import json
import shlex
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
import urllib.request
import urllib.error

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class SetupUITests(unittest.TestCase):
    def test_removal_recognizes_shell_quoted_path_with_apostrophe(self):
        from setup_ui.diagnostics import entry_owned
        from setup_ui.maintenance import remove_configs
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / "a'b hub", Path(tmp) / 'home'
            home.mkdir()
            command = shlex.join(['python', str(root / 'scripts/memory/entry.py'), 'hook', 'claude'])
            self.assertTrue(entry_owned(command, root))
            profile = home / '.profile'
            profile.write_text('custom\n# BEGIN IA-HUB STARTUP\n' + command + '\n# END IA-HUB STARTUP\n')
            remove_configs(root, home, windows=False)
            self.assertEqual(profile.read_text(), 'custom\n\n')

    def test_http_requires_token_and_same_origin_and_preview_cannot_mutate(self):
        from setup_ui.actions import Controller
        from setup_ui.server import make_server
        with tempfile.TemporaryDirectory() as tmp, patch('setup_ui.actions.discover', return_value={'root': tmp, 'foreign': False, 'apps': [], 'health': {}}):
            controller = Controller(Path(tmp), preview=True)
            controller.log('info', 'password="private"')
            server = make_server(controller)
            thread = threading.Thread(target=server.serve_forever, daemon=True)
            thread.start()
            base = f'http://127.0.0.1:{server.server_port}'
            headers = {'Authorization': 'Bearer ' + server.token}
            try:
                with self.assertRaises(urllib.error.HTTPError) as error:
                    urllib.request.urlopen(base + '/api/state')
                self.assertEqual(error.exception.code, 403)
                with urllib.request.urlopen(urllib.request.Request(base + '/api/export.json', headers=headers)) as response:
                    report = json.load(response)
                self.assertNotIn('private', json.dumps(report))
                for origin, expected in [('http://evil.invalid', 403), (base, 400)]:
                    req = urllib.request.Request(base + '/api/action', json.dumps({'action': 'remove', 'confirmed': True}).encode(), {**headers, 'Content-Type': 'application/json', 'Origin': origin})
                    with self.assertRaises(urllib.error.HTTPError) as error:
                        urllib.request.urlopen(req)
                    self.assertEqual(error.exception.code, expected)
            finally:
                server.shutdown()
                server.server_close()
                thread.join(2)

    def test_runtime_backup_preserves_memory_and_separate_ui_runtime(self):
        from setup_ui.maintenance import backup_runtime
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / '.memory-runtime').mkdir()
            (root / '.memory-runtime/python').write_text('runtime')
            (root / '.setup-runtime').mkdir()
            memory = root / 'contexto/.memory/memory.sqlite3'
            memory.parent.mkdir(parents=True)
            memory.write_bytes(b'memory')
            with patch('setup_ui.maintenance.stop_memory'):
                backup_runtime(root, lambda *args: None)
            self.assertFalse((root / '.memory-runtime').exists())
            self.assertTrue((root / '.setup-runtime').exists())
            self.assertEqual(memory.read_bytes(), b'memory')
            self.assertEqual(next((memory.parent / 'backups').glob('runtime-*/python')).read_text(), 'runtime')

    def test_opencode_jsonc_is_detected_when_json_has_no_server(self):
        from setup_ui.diagnostics import discover
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            servers = {'opencode': {}, 'opencode_jsonc': {'command': ['python', str(root / 'scripts/memory/entry.py')]}}
            with patch('setup_ui.diagnostics.configured_servers', return_value=servers), patch('setup_ui.diagnostics.rpc', return_value={'root': str(root)}):
                report = discover(root, root / 'home')
            self.assertTrue(next(a for a in report['apps'] if a['id'] == 'opencode')['integrated'])

    def test_preview_blocks_all_mutations_but_allows_readonly_verification(self):
        from setup_ui.actions import Controller
        with tempfile.TemporaryDirectory() as tmp, patch('setup_ui.actions.discover', return_value={'installed': False, 'root': tmp, 'foreign': False, 'health': {}, 'apps': []}):
            controller = Controller(Path(tmp), preview=True)
            for action in ['install', 'repair', 'reinstall', 'remove']:
                with self.assertRaises(PermissionError):
                    controller.start(action, ['runtime'], confirmed=True)
            controller.start('verify')
            for _ in range(100):
                if controller.snapshot()['job']['status'] != 'running':
                    break
                time.sleep(.01)
            self.assertEqual(controller.snapshot()['job']['status'], 'partial')

    def test_logs_and_export_redact_secrets_and_strip_ansi(self):
        from setup_ui.actions import redact
        text = '\x1b[31mapi_key="secret-short" password=abc Bearer abcdefghijklmnopqrstuvwxyz\x1b[0m'
        result = redact(text)
        self.assertNotIn('secret-short', result)
        self.assertNotIn('password=abc', result)
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz', result)
        self.assertNotIn('\x1b', result)

    def test_reinstall_requires_selection_and_remove_requires_confirmation(self):
        from setup_ui.actions import Controller
        with tempfile.TemporaryDirectory() as tmp, patch('setup_ui.actions.discover', return_value={'installed': True, 'root': tmp, 'foreign': False, 'health': {}, 'apps': []}):
            controller = Controller(Path(tmp))
            with self.assertRaises(ValueError):
                controller.start('reinstall', [])
            with self.assertRaises(ValueError):
                controller.start('reinstall', ['arbitrary-command'])
            with self.assertRaises(PermissionError):
                controller.start('remove')

    def test_remove_preserves_memory_other_servers_and_custom_hooks(self):
        from setup_ui.maintenance import remove_configs
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / 'hub', Path(tmp) / 'home'
            state = root / 'contexto/.memory'
            state.mkdir(parents=True)
            database = state / 'memory.sqlite3'
            database.write_bytes(b'preserve-database')
            home.mkdir()
            entry = str(root / 'scripts/memory/entry.py')
            cfg = home / '.claude.json'
            cfg.write_text(json.dumps({'mcpServers': {'ia_hub': {'args': [entry, 'mcp', 'claude']}, 'custom': {'command': 'keep'}}}))
            hooks = home / '.claude/settings.json'
            hooks.parent.mkdir()
            hooks.write_text(json.dumps({'hooks': {'Stop': [{'hooks': [{'command': entry + ' hook claude'}, {'command': 'custom-hook'}]}]}}))
            result = remove_configs(root, home, windows=True)
            self.assertEqual(database.read_bytes(), b'preserve-database')
            self.assertEqual(list(json.loads(cfg.read_text())['mcpServers']), ['custom'])
            commands = json.loads(hooks.read_text())['hooks']['Stop'][0]['hooks']
            self.assertEqual(commands, [{'command': 'custom-hook'}])
            self.assertTrue(list(Path(result['backup']).iterdir()))

    def test_foreign_mcp_is_preserved_by_removal(self):
        from setup_ui.maintenance import remove_configs
        with tempfile.TemporaryDirectory() as tmp:
            root, home = Path(tmp) / 'hub', Path(tmp) / 'home'
            home.mkdir()
            cfg = home / '.claude.json'
            original = {'mcpServers': {'ia_hub': {'args': ['/other/scripts/memory/entry.py']}}}
            cfg.write_text(json.dumps(original))
            remove_configs(root, home, windows=True)
            self.assertEqual(json.loads(cfg.read_text()), original)
