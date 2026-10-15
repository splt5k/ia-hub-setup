import json
import sys
import tempfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class ModInstallTests(unittest.TestCase):
    def test_old_cli_preserves_existing_hooks_and_does_not_claim_installed(self):
        from memory.mods import install_mod
        with tempfile.TemporaryDirectory() as tmp:
            with patch('memory.mods.shutil.which', return_value='/claude'), patch('memory.mods.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='2.1.200 (Claude Code)', stderr='')) as runner:
                result = install_mod(Path(tmp), Path(tmp), '/python', '/entry', lambda *_: None, Path(tmp)/'backups')
            self.assertFalse(result['installed'])
            self.assertEqual(runner.call_count, 1)

    def test_persistent_install_renders_paths_and_backs_up_settings(self):
        from memory.mods import install_mod
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            home = Path(tmp)/'home'; home.mkdir()
            settings = home/'.claude/settings.json'; settings.parent.mkdir(); settings.write_text('{"custom":true}')
            saved = {}
            def save(path, text):
                saved[str(path)] = text
                path.parent.mkdir(parents=True, exist_ok=True)
                path.write_text(text, encoding='utf-8')
            runs = []
            def run(argv, **kwargs):
                runs.append(argv)
                return SimpleNamespace(returncode=0, stdout='2.1.299 (Claude Code)' if '--version' in argv else '{}', stderr='')
            # Source template in repo, destination in temporary root, no global config touched.
            with patch('memory.mods.shutil.which', return_value='/claude'), patch('memory.mods.subprocess.run', side_effect=run), patch('memory.mods.TEMPLATE', repo/'scripts/memory/claude-mod'):
                result = install_mod(Path(tmp)/'hub', home, '/python path', '/entry path', save, Path(tmp)/'backups')
            self.assertTrue(result['installed'])
            script = next(v for k,v in saved.items() if k.endswith('register.js'))
            self.assertIn(json.dumps('/python path'), script)
            self.assertNotIn('__PYTHON__', script)
            self.assertTrue(any((Path(tmp)/'backups').iterdir()))
            self.assertTrue(any('install' in a for a in runs))
            self.assertFalse(any('--yes' in a or '-y' in a for a in runs))
