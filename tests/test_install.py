import contextlib
import io
import json
import os
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class InstallTests(unittest.TestCase):
    @unittest.skipUnless(os.name == 'nt', 'Instalador Windows')
    def test_main_installer_preserves_opencode_and_antigravity_rules(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory(prefix='hub-install-') as tmp:
            root = Path(tmp) / 'hub'
            root.mkdir()
            for name in ['scripts', 'modelos', 'opencode', 'claude', 'regras']:
                shutil.copytree(repo / name, root / name, ignore=shutil.ignore_patterns('__pycache__'))
            shutil.copy2(repo / 'install.ps1', root / 'install.ps1')
            (root / 'scripts/bootstrap.ps1').write_text("function Assert-HubServiceOwnership {}\nfunction Write-HubEvent {}\nfunction Invoke-HubBootstrap { [pscustomobject]@{name='fixture';state='present';detail='test'} }", encoding='utf-8')
            (root / 'scripts/install-memory.ps1').write_text('# Stub: memory installer is tested separately.', encoding='utf-8')
            home = Path(tmp) / 'home'
            opencode = home / '.config/opencode/opencode.json'
            opencode.parent.mkdir(parents=True)
            opencode.write_text('{"provider":{"custom":{"name":"keep"}}}', encoding='utf-8')
            rules = home / '.gemini/config/rules/custom.md'
            rules.parent.mkdir(parents=True)
            rules.write_text('preserve me', encoding='utf-8')
            env = {**os.environ, 'USERPROFILE': str(home), 'APPDATA': str(home / 'AppData/Roaming'), 'LOCALAPPDATA': str(home / 'AppData/Local')}
            for key in ['APPDATA', 'LOCALAPPDATA']:
                Path(env[key]).mkdir(parents=True)
            mocks = ' '.join('function ' + name + ' {};' for name in ['New-ScheduledTaskAction', 'New-ScheduledTaskTrigger', 'New-ScheduledTaskSettingsSet', 'Register-ScheduledTask'])
            result = subprocess.run(['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-Command', mocks + " & '" + str(root / 'install.ps1') + "'"], env=env, capture_output=True, text=True)
            self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
            self.assertEqual(json.loads(opencode.read_text(encoding='utf-8')), {'provider': {'custom': {'name': 'keep'}}})
            self.assertEqual(rules.read_text(encoding='utf-8'), 'preserve me')

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
            opencode.write_text(json.dumps({'mcp': {'existing': {'type': 'local', 'command': ['custom']}}, 'instructions': ['custom.md']}), encoding='utf-8')
            with patch.object(install, 'WINDOWS', True), patch.object(install.Path, 'home', return_value=home), patch.object(install, 'ROOT', hub), patch.object(install, 'STATE', state), patch.object(install.subprocess, 'run', return_value=SimpleNamespace(returncode=0, stderr='', stdout='Claude_freshpackage\n')) as runner, patch.object(install, 'request', return_value={'records': 0}), contextlib.redirect_stdout(io.StringIO()):
                install.main()
                install.main()  # Reinstalar não duplica hooks, MCPs ou instruções.
            config = tomllib.loads((home / '.codex/config.toml').read_text(encoding='utf-8'))
            self.assertIn('ia_hub', config['mcp_servers'])
            hooks = json.loads(settings.read_text(encoding='utf-8'))['hooks']['SessionStart']
            commands = [h['command'] for group in hooks for h in group['hooks']]
            self.assertIn('custom-hook', commands)
            self.assertEqual(sum('memory/entry.py' in c.replace('\\', '/') for c in commands), 1)
            servers = json.loads(desktop.read_text(encoding='utf-8'))['mcpServers']
            self.assertIn('existing', servers)
            self.assertIn('ia_hub', servers)
            fresh = home / 'AppData/Local/Packages/Claude_freshpackage/LocalCache/Roaming/Claude/claude_desktop_config.json'
            self.assertIn('ia_hub', json.loads(fresh.read_text(encoding='utf-8'))['mcpServers'])
            mcp = json.loads(opencode.read_text(encoding='utf-8'))['mcp']
            self.assertIn('existing', mcp)
            self.assertIn('ia_hub', mcp)
            obj = json.loads(opencode.read_text(encoding='utf-8'))
            self.assertIn('custom.md', obj['instructions'])
            self.assertTrue(any(p.endswith('/ia-hub.md') for p in obj['instructions']))
            self.assertEqual(len(obj['instructions']), 2)
            agy = json.loads((home / '.gemini/antigravity-cli/settings.json').read_text(encoding='utf-8'))
            self.assertEqual(len(agy['permissions']['allow']), 6)
            self.assertTrue((opencode.parent / 'plugins/ia-hub-memory.js').exists())
            self.assertIn("D''Avila", runner.call_args.args[0][-1])
