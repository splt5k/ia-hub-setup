import hashlib
import importlib.util
import json
import os
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
import sys

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / 'scripts'))
spec = importlib.util.spec_from_file_location('portable_builder', ROOT / 'scripts/build-portable.py')
builder = importlib.util.module_from_spec(spec)
spec.loader.exec_module(builder)


def fixture(path):
    contents = {'install.ps1': 'new', 'instalar.sh': 'new', 'scripts/memory/entry.py': 'new',
                'scripts/setup_ui/web/index.html': 'new', 'regras/nucleo.md': 'default'}
    for name, content in contents.items():
        file = path / name
        file.parent.mkdir(parents=True, exist_ok=True)
        file.write_bytes(content.encode())
    (path / 'payload-manifest.json').write_text(json.dumps({'files': {name: hashlib.sha256(content.encode()).hexdigest() for name, content in contents.items()}}))


class PortableTests(unittest.TestCase):
    def test_invalid_arguments_are_rejected_before_deploy_or_diagnostics(self):
        spec = importlib.util.spec_from_file_location('portable_entry', ROOT / 'scripts/portable/entry.py')
        entry = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(entry)
        with patch.object(sys, 'argv', ['entry.py', '--unknown']), patch.object(entry, 'deploy') as deploy, patch.object(entry, 'discover') as discover:
            with self.assertRaises(ValueError):
                entry.main()
            deploy.assert_not_called()
            discover.assert_not_called()

    def test_bundle_is_deterministic_and_excludes_user_data(self):
        files = builder.public_files(ROOT)
        self.assertIn('scripts/setup_ui/web/app.js', files)
        self.assertIn('scripts/portable/entry.py', files)
        self.assertFalse(any(n.startswith(('contexto/', 'Memoria/', '.tools/', '.setup-runtime/', '.memory-runtime/')) for n in files))
        self.assertEqual(builder.archives(files), builder.archives(files))
        manifest = json.loads(files['payload-manifest.json'])
        for name, digest in manifest['files'].items():
            self.assertEqual(hashlib.sha256(files[name]).hexdigest(), digest)

    def test_deploy_backs_up_code_and_preserves_rules_memory_and_history(self):
        from setup_ui.portable import deploy
        with tempfile.TemporaryDirectory() as tmp:
            source, root = Path(tmp) / 'payload', Path(tmp) / 'installed'
            fixture(source)
            (root / 'regras').mkdir(parents=True)
            (root / 'regras/nucleo.md').write_text('personal')
            (root / 'install.ps1').write_text('old')
            (root / 'contexto/.memory').mkdir(parents=True)
            database = root / 'contexto/.memory/memory.sqlite3'
            database.write_bytes(b'preserved historical data')
            with patch('setup_ui.maintenance.stop_memory'):
                deploy(source, root, lambda *args: None)
            self.assertEqual((root / 'install.ps1').read_text(), 'new')
            self.assertEqual((root / 'regras/nucleo.md').read_text(), 'personal')
            self.assertEqual(database.read_bytes(), b'preserved historical data')
            self.assertEqual(next((root / 'contexto/.setup/backups').glob('*/install.ps1')).read_text(), 'old')

    def test_tampered_payload_stops_before_any_deployment(self):
        from setup_ui.portable import deploy, payload_files
        with tempfile.TemporaryDirectory() as tmp:
            source, root = Path(tmp) / 'payload', Path(tmp) / 'installed'
            fixture(source)
            (source / 'install.ps1').write_text('changed')
            with self.assertRaisesRegex(ValueError, 'Integridade'):
                deploy(source, root, lambda *args: None)
            self.assertFalse(root.exists())
            manifest = source / 'payload-manifest.json'
            manifest.write_text(json.dumps({'files': {'../escape': 'x'}}))
            with self.assertRaisesRegex(ValueError, 'Caminho'):
                payload_files(source)

    def test_worker_cache_is_removed_but_python_base_is_permanent(self):
        from setup_ui.portable import worker_environment
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp) / 'installed'
            with worker_environment(root) as env:
                work = Path(env['IA_HUB_WORK_DIR'])
                self.assertTrue(work.is_dir())
                self.assertTrue(Path(env['TMPDIR']).is_relative_to(work))
                self.assertTrue(Path(env['UV_CACHE_DIR']).is_relative_to(work))
                self.assertEqual(env['UV_PYTHON_INSTALL_DIR'], str(root / '.tools/python'))
                self.assertEqual(env['UV_LINK_MODE'], 'copy')
                (work / 'download').write_text('temporary')
            self.assertFalse(work.exists())


if __name__ == '__main__':
    unittest.main()
