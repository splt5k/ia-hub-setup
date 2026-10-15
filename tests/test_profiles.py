import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import tomllib
import unittest
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from memory.profiles import configure_profiles


class ProfileTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)
        self.home = Path(self.tmp.name)
        self.codex = self.home / '.codex'
        self.codex.mkdir()
        self.main = self.codex / 'config.toml'
        self.saved = []

    def save(self, path, text):
        self.saved.append((path, path.read_bytes() if path.exists() else None))
        path.write_text(text, encoding='utf-8')

    def run_config(self, version='0.162.0-alpha.17.2'):
        return configure_profiles(self.home, self.save, version)

    def legacy(self, name='rapido'):
        model, effort = ('gpt-6.1-sol', 'low') if name == 'rapido' else ('gpt-6-astra', 'high')
        return f'\n[profiles.{name}]\n# comentário preservado\nmodel = "{model}"\nmodel_reasoning_effort = "{effort}"\n'

    def test_migrate_preserves_base_metadata_rea_hooks_and_backups(self):
        top = 'model = "custom"\nprofile = "rapido"\napproval_policy = "on-request"\n# base\n'
        tail = '\n[mcp_servers.rea]\ncommand = "wsl.exe"\n[hooks]\ncustom = "keep"\n[metadata]\nunknown = 7\n'
        before = top + self.legacy() + self.legacy('pesado') + tail
        self.main.write_text(before, encoding='utf-8')
        before_bytes = self.main.read_bytes()
        report = self.run_config()
        self.assertEqual(report['format'], 'files')
        result = self.main.read_text(encoding='utf-8')
        self.assertEqual(result, top.replace('profile = "rapido"\n', '') + tail)
        self.assertIn((self.main, before_bytes), self.saved)
        for name in ['rapido', 'pesado']:
            path = self.codex / f'{name}.config.toml'
            self.assertIn('# comentário preservado', path.read_text(encoding='utf-8'))
            self.assertNotIn('mcp_servers', tomllib.loads(path.read_text(encoding='utf-8')))
        self.saved.clear()
        self.run_config()
        self.assertEqual(self.saved, [])

    def test_custom_inline_and_file_preserved_with_warning(self):
        custom = self.legacy().replace('"low"', '"medium"')
        custom += self.legacy('pesado') + '[profiles.pesado.metadata]\nowner = "user"\n'
        self.main.write_text(custom, encoding='utf-8')
        self.assertTrue(self.run_config()['warnings'])
        self.assertEqual(self.main.read_text(encoding='utf-8'), custom)
        self.assertFalse((self.codex / 'rapido.config.toml').exists())
        self.assertFalse((self.codex / 'pesado.config.toml').exists())

    def test_existing_destination_conflict_never_removes_inline(self):
        original = self.legacy()
        self.main.write_text(original, encoding='utf-8')
        target = self.codex / 'rapido.config.toml'
        target.write_text('model = "user"\n', encoding='utf-8')
        self.assertTrue(self.run_config()['warnings'])
        self.assertEqual(self.main.read_text(encoding='utf-8'), original)
        self.assertEqual(target.read_text(encoding='utf-8'), 'model = "user"\n')

    def test_unknown_profiles_metadata_and_custom_file_are_untouched(self):
        original = '[profiles.user]\nmodel = "custom"\n[profiles.user.metadata]\nlabel = "keep"\n'
        self.main.write_text(original, encoding='utf-8')
        target = self.codex / 'rapido.config.toml'
        custom = '# custom\nmodel = "user"\n[metadata]\nowner = "me"\n'
        target.write_text(custom, encoding='utf-8')
        self.assertTrue(self.run_config()['warnings'])
        self.assertEqual(self.main.read_text(encoding='utf-8'), original)
        self.assertEqual(target.read_text(encoding='utf-8'), custom)

    def test_quoted_managed_selector_is_removed(self):
        self.main.write_text('"profile" = "rapido"\n' + self.legacy(), encoding='utf-8')
        self.run_config()
        self.assertNotIn('profile', tomllib.loads(self.main.read_text(encoding='utf-8')))

    def test_old_version_inline_fresh_and_custom_preserved(self):
        self.main.write_text('model = "user"\n[profiles.rapido]\nmodel = "user"\n', encoding='utf-8')
        self.assertEqual(self.run_config('codex-cli 0.133.0')['format'], 'inline')
        data = tomllib.loads(self.main.read_text(encoding='utf-8'))
        self.assertEqual(data['profiles']['rapido'], {'model': 'user'})
        self.assertEqual(data['profiles']['pesado']['model'], 'gpt-6-astra')
        self.assertFalse((self.codex / 'pesado.config.toml').exists())

    def test_boundary_and_unknown_version(self):
        for version in ['0.134.0', '0.134.0-alpha.1', '0.162.0-alpha.17.2']:
            self.assertEqual(self.run_config(version)['format'], 'files')
        self.saved.clear()
        for version in ['nonsense', '', '1.0.0']:
            self.assertEqual(self.run_config(version)['format'], 'skipped')
            self.assertEqual(self.saved, [])
        with patch('memory.profiles.subprocess.run', side_effect=FileNotFoundError):
            self.assertTrue(configure_profiles(self.home, self.save)['warnings'])
            self.assertEqual(self.saved, [])

    def test_detection_uses_version_only(self):
        with patch('memory.profiles.subprocess.run') as run:
            run.return_value.returncode = 0
            run.return_value.stdout = 'codex-cli 0.162.0-alpha.17.2\n'
            self.assertEqual(configure_profiles(self.home, self.save)['format'], 'files')
            self.assertEqual(run.call_args.args[0], ['codex', '--version'])

    @unittest.skipUnless(shutil.which('codex'), 'CLI não instalada')
    def test_real_cli_profiles_load_and_inherit_mcp_without_inference(self):
        version = subprocess.run(['codex', '--version'], capture_output=True, text=True, timeout=15).stdout
        if not version.startswith('codex-cli 0.162.'):
            self.skipTest('Prova de integração para CLI 0.162 instalada')
        self.main.write_text('[mcp_servers.rea]\ncommand = "wsl.exe"\n' + self.legacy() + self.legacy('pesado'), encoding='utf-8')
        self.run_config(version)
        env = {**os.environ, 'CODEX_HOME': str(self.codex)}
        for name in ['rapido', 'pesado']:
            result = subprocess.run(['codex', '--profile', name, 'mcp', 'list', '--json'], cwd=self.home,
                                    env=env, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            self.assertIn('rea', result.stdout)


if __name__ == '__main__':
    unittest.main()
