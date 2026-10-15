import json
import sys
import tempfile
import threading
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from memory.core import Memory
from memory.executor import Executor


def response(text='ok', code=0):
    return (code, json.dumps({'type': 'result', 'result': text}), '')


class ExecutorTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.memory = Memory(self.root)
        self.executor = Executor(self.memory, self.root)
        self.addCleanup(self.tmp.cleanup)
        self.addCleanup(lambda: self.executor.pool.shutdown(wait=True))

    def wait(self, run):
        for _ in range(200):
            status = self.executor.status(run['run_id'])
            if status['status'] != 'running':
                return status
            time.sleep(.01)
        self.fail('Worker did not finish')

    def test_validation_failure_escalates_once_and_measures(self):
        with patch.object(self.executor, '_process', side_effect=[response('wrong'), response('ok')]) as process:
            run = self.executor.submit('Liste', 'claude', validation={'type': 'exact', 'value': 'ok'})
            self.assertEqual(self.wait(run)['status'], 'succeeded')
        report = self.executor.report(run['run_id'])
        self.assertEqual([a['model_requested'] for a in report['attempts']], ['claude-haiku-5-5', 'claude-sonnet-5-5'])
        self.assertEqual(process.call_count, 2)
        self.assertIsNone(report['totals']['cost_reported_usd'])

    def test_exit_zero_without_validator_is_unvalidated(self):
        with patch.object(self.executor, '_process', return_value=response()):
            run = self.executor.submit('Liste', 'claude')
            self.assertEqual(self.wait(run)['status'], 'unvalidated')

    def test_auth_error_never_retries(self):
        with patch.object(self.executor, '_process', return_value=(1, '', 'Authentication required')) as process:
            run = self.executor.submit('Liste', 'claude', validation={'type': 'json'})
            self.assertEqual(self.wait(run)['status'], 'failed')
            self.assertEqual(process.call_count, 1)

    def test_async_idempotency_and_memory_lock_free(self):
        started, release = threading.Event(), threading.Event()
        def process(*args):
            started.set()
            release.wait(2)
            return response()
        with patch.object(self.executor, '_process', side_effect=process) as mocked:
            run = self.executor.submit('Liste', 'claude', project='project-a', idempotency_key='same')
            self.assertTrue(started.wait(1))
            duplicate = self.executor.submit('Liste', 'claude', project='project-a', idempotency_key='same')
            self.assertEqual(run['run_id'], duplicate['run_id'])
            acquired = self.memory.lock.acquire(timeout=.2)
            self.assertTrue(acquired)
            if acquired:
                self.memory.lock.release()
            release.set()
            self.wait(run)
            self.assertEqual(mocked.call_count, 1)

    def test_parallel_children_are_counted_and_guarded(self):
        tasks = [{'prompt': 'Liste A', 'independent': True}, {'prompt': 'Liste B', 'independent': True}]
        with self.assertRaises(ValueError):
            self.executor.submit('Liste', 'codex', subtasks=tasks, parallel_benefit=2)
        with self.assertRaises(ValueError):
            self.executor.submit('Liste', 'claude', subtasks=tasks)
        with patch.object(self.executor, '_process', return_value=response()):
            run = self.executor.submit('Liste', 'claude', subtasks=tasks, parallel_benefit=2)
            self.assertEqual(self.wait(run)['status'], 'unvalidated')
        report = self.executor.report()
        self.assertEqual(len(report['runs']), 3)
        self.assertEqual(report['totals']['attempt_count'], 2)

    def test_bounded_validation_and_argv(self):
        for validation in [{'type': 'shell', 'value': 'rm'}, {'type': 'contains', 'value': ''}]:
            with self.assertRaises(ValueError):
                self.executor.submit('Liste', 'claude', validation=validation)
        argv, env = self.executor._command({'client': 'codex', 'model': 'gpt-6.1-sol', 'effort': 'low'}, 'hello')
        self.assertIsInstance(argv, list)
        self.assertIn('read-only', argv)
        self.assertEqual(env['IA_HUB_WORKER'], '1')

    def test_process_exceptions_are_measured(self):
        with patch.object(self.executor, '_process', side_effect=TimeoutError('timeout')):
            run = self.executor.submit('Liste', 'claude')
            self.assertEqual(self.wait(run)['status'], 'failed')
        report = self.executor.report(run['run_id'])
        self.assertEqual(report['totals']['attempt_count'], 1)
        self.assertIsNone(report['attempts'][0]['usage']['input_tokens'])

    def test_manual_no_retry_and_json_validator(self):
        with patch.object(self.executor, '_process', return_value=response('bad')) as process:
            run = self.executor.submit('Liste', 'claude', mode='manual', current_model='opus', validation={'type': 'json'})
            self.assertEqual(self.wait(run)['status'], 'failed')
            self.assertEqual(process.call_count, 1)
        with patch.object(self.executor, '_process', return_value=response('{"ok":true}')):
            run = self.executor.submit('Liste', 'claude', validation={'type': 'json'})
            self.assertEqual(self.wait(run)['status'], 'succeeded')

    def test_context_is_scoped_bounded_and_only_reported(self):
        with patch.object(self.memory, 'context', return_value={'data': 'x' * 20000}) as context, patch.object(self.executor, '_process', return_value=response('result')) as process:
            run = self.executor.submit('Liste', 'claude', project='test-project')
            self.wait(run)
        context.assert_called_once_with(query='Liste', project='test-project', limit=4, global_fallback=False)
        self.assertLess(len(process.call_args.args[1]), 6400)
        with self.memory.connection() as c:
            record = c.execute('SELECT status,project FROM records WHERE stable_key=?', ('executor:' + run['run_id'],)).fetchone()
        self.assertEqual(record['status'], 'reported')
        self.assertEqual(record['project'], 'test-project')

    def test_parallel_preserves_manual_selection(self):
        tasks = [{'prompt': 'Liste A', 'independent': True}, {'prompt': 'Liste B', 'independent': True}]
        with patch.object(self.executor, '_process', return_value=response()) as process:
            run = self.executor.submit('Liste', 'claude', subtasks=tasks, parallel_benefit=2, mode='manual', current_model='opus')
            self.wait(run)
        self.assertEqual([call.args[0]['model'] for call in process.call_args_list], ['opus', 'opus'])

    def test_native_windows_wrapper_never_uses_shell(self):
        package = self.root / 'node_modules/opencode-ai'
        (package / 'bin').mkdir(parents=True)
        (package / 'bin/opencode.exe').write_bytes(b'fake')
        (package / 'package.json').write_text(json.dumps({'bin': {'opencode': 'bin/opencode.exe'}}), encoding='utf8')
        resolved = self.executor._native_argv(['opencode', 'run', 'hello & calc'], str(self.root / 'opencode.cmd'))
        self.assertEqual(resolved[0], str(package / 'bin/opencode.exe'))
        self.assertEqual(resolved[-1], 'hello & calc')

    def test_cli_permission_guards(self):
        for client in ['claude', 'codex', 'opencode', 'agy']:
            decision = self.executor.router.plan('Liste', client)
            argv, env = self.executor._command(decision, 'x')
            self.assertFalse(any('skip-permissions' in arg or 'bypass' in arg or arg == '--auto' for arg in argv))
            if client == 'claude':
                self.assertIn('--strict-mcp-config', argv)
            if client == 'opencode':
                self.assertEqual(json.loads(env['OPENCODE_PERMISSION'])['*'], 'deny')
                self.assertEqual(json.loads(env['OPENCODE_PERMISSION'])['read'], 'allow')

    def test_output_status_survives_executor_restart(self):
        with patch.object(self.executor, '_process', return_value=response('bounded result')):
            run = self.executor.submit('Liste', 'claude', validation={'type': 'contains', 'value': 'result'})
            self.wait(run)
        restarted = Executor(self.memory, self.root)
        try:
            self.assertEqual(restarted.status(run['run_id'])['output'], 'bounded result')
        finally:
            restarted.pool.shutdown(wait=True)

    def test_interrupted_parent_is_not_reexecuted_or_left_running_after_restart(self):
        decision = self.executor.router.plan('Liste', 'claude')
        decision['execution_mode'] = 'dispatcher'
        parent = self.executor.ledger.start_run('claude', '', 'Liste', {}, decision, idempotency_key='crashed')
        self.executor.ledger.start_run('claude', '', 'child', {}, decision, parent_id=parent)
        restarted = Executor(self.memory, self.root)
        try:
            with patch.object(restarted, '_process') as process:
                result = restarted.submit('Liste', 'claude', idempotency_key='crashed')
                self.assertEqual(result['run_id'], parent)
                self.assertEqual(result['status'], 'interrupted')
                process.assert_not_called()
                self.assertEqual(len(restarted.report(parent)['runs']), 2)
        finally:
            restarted.pool.shutdown(wait=True)

    def test_parallel_parent_validation_is_not_silently_ignored(self):
        with self.assertRaises(ValueError):
            self.executor.submit('Liste', 'claude', validation={'type': 'exact', 'value': 'IMPOSSIBLE'},
                subtasks=[{'prompt': 'child', 'validation': {'type': 'exact', 'value': 'ok'}, 'independent': True}], parallel_benefit=2)

    def test_blocked_by_policy_never_escalates_to_another_attempt(self):
        denied = (0,json.dumps({'type':'result','result':'Command rejected: blocked by policy'}),'')
        with patch.object(self.executor,'_process',return_value=denied) as process:
            run = self.executor.submit('Read file','claude',validation={'type':'exact','value':'ok'})
            self.assertEqual(self.wait(run)['status'],'failed')
            self.assertEqual(process.call_count,1)
