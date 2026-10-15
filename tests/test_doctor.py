import contextlib
import io
import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class DoctorTests(unittest.TestCase):
    def test_waits_for_semantics_and_proves_write_read_and_search(self):
        from memory import doctor
        calls = []
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            def rpc(action, args=None):
                calls.append(action)
                if action == 'health':
                    return {'root': str(root), 'semantic_state': 'loading' if len(calls) == 1 else 'ready', 'database_integrity': 'ok'}
                if action == 'store':
                    self.assertEqual(args['project'], 'IA-Hub-E2E-installer')
                    return {'id': 'proof'}
                if action == 'get':
                    self.assertEqual(args, {'item_id': 'proof'})
                    return {'id': 'proof'}
                if action == 'search':
                    return [{'id': 'proof', 'methods': ['semantica']}]
            with patch.object(doctor, 'ROOT', root), patch.object(doctor, 'STATE', root), patch.object(doctor, 'request', side_effect=rpc), patch.object(doctor.time, 'sleep') as sleep, contextlib.redirect_stdout(io.StringIO()):
                report = doctor.check()
            sleep.assert_called_once_with(2)
            self.assertEqual(report['write_read_semantic_search'], 'passed')
            self.assertTrue((root / 'doctor.json').exists())

    def test_rejects_failed_model_and_different_root(self):
        from memory import doctor
        for health in [{'root': 'wrong'}, {'root': str(doctor.ROOT), 'semantic_state': 'failed', 'last_error': 'offline'}]:
            with patch.object(doctor, 'request', return_value=health), self.assertRaises(RuntimeError):
                doctor.check()

    def test_loading_model_times_out(self):
        from memory import doctor
        with patch.object(doctor, 'request', return_value={'root': str(doctor.ROOT), 'semantic_state': 'loading'}), self.assertRaises(RuntimeError):
            doctor.check(timeout=0)
