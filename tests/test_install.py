import contextlib
import io
import json
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class InstallTests(unittest.TestCase):
    def test_jsonc_preserves_urls_and_accepts_trailing_commas(self):
        from memory.install import strip_json_comments
        text = '{"url":"https://example.com/a,}", // comentário\n"nested":{"x":1,},}'
        parsed = json.loads(strip_json_comments(text))
        self.assertEqual(parsed['url'], 'https://example.com/a,}')
        self.assertEqual(parsed['nested'], {'x': 1})

    def test_fresh_home_and_existing_client_settings_are_preserved(self):
        from memory import install
        with tempfile.TemporaryDirectory(prefix="D'Avila-") as tmp:
            root = Path(tmp)
            home = root / 'home'
            hub = root / 'hub'
            state = hub / 'contexto' / '.memory'
            state.mkdir(parents=True)
            (home / '.claude').mkdir(parents=True)
            settings = home / '.claude' / 'settings.json'
            settings.write_text(json.dumps({'hooks': {'SessionStart': [{'hooks': [{'type': 'command', 'command': 'custom-hook'}, {'type': 'command', 'command': 'python D:/old/scripts/memory/entry.py hook claude'}]}]}}), encoding='utf-8')
            desktop = home / 'AppData/Roaming/Claude/claude_desktop_config.json'
            desktop.parent.mkdir(parents=True)
            desktop.write_text(json.dumps({'mcpServers': {'existing': {'command': 'custom'}}}), encoding='utf-8')
            opencode = home / '.config/opencode/opencode.json'
            opencode.parent.mkdir(parents=True)
            opencode.write_text(json.dumps({'mcp': {'existing': {'type': 'local', 'command': ['custom']}}}), encoding='utf-8')
            with patch.object(install.Path, 'home', return_value=home), patch.object(install, 'ROOT', hub), patch.object(install, 'STATE', state), patch.object(install.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='')) as runner, patch.object(install, 'request', return_value={'records': 0}), contextlib.redirect_stdout(io.StringIO()):
                install.main()
            config = tomllib.loads((home / '.codex/config.toml').read_text(encoding='utf-8'))
            self.assertIn('ia_hub', config['mcp_servers'])
            hooks = json.loads(settings.read_text(encoding='utf-8'))['hooks']['SessionStart']
            commands = [h['command'] for group in hooks for h in group['hooks']]
            self.assertIn('custom-hook', commands)
            self.assertEqual(sum('memory/entry.py' in c.replace('\\', '/') for c in commands), 1)
            servers = json.loads(desktop.read_text(encoding='utf-8'))['mcpServers']
            self.assertIn('existing', servers)
            self.assertIn('ia_hub', servers)
            mcp = json.loads(opencode.read_text(encoding='utf-8'))['mcp']
            self.assertIn('existing', mcp)
            self.assertIn('ia_hub', mcp)
            self.assertTrue((opencode.parent / 'plugins/ia-hub-memory.js').exists())
            self.assertIn("D''Avila", runner.call_args.args[0][-1])
