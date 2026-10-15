import sys
import tempfile
import unittest
from pathlib import Path
from unittest.mock import Mock
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from memory.core import Memory


class NativeTests(unittest.TestCase):
    def setUp(self):
        from memory.native import Native
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(Path(self.tmp.name))
        self.router = Mock()
        self.router.plan.return_value = {'model': 'haiku', 'policy_version': 'test', 'control': 'native', 'context_budget': 2000}
        self.native = Native(self.memory, self.router)

    def tearDown(self):
        self.tmp.cleanup()

    def test_attempt_replay_is_idempotent_and_cost_unknown(self):
        run = self.native.handle(event='start', prompt='some task', client='claude-code', project='/demo', idempotency_key='a')
        replay = self.native.handle(event='start', prompt='some task', client='claude-code', project='/demo', idempotency_key='a')
        self.assertEqual(run['run_id'], replay['run_id'])
        args = dict(event='attempt', run_id=run['run_id'], event_id='step1', model_requested='haiku', model_reported='haiku-actual', usage={'input_tokens': 10, 'output_tokens': 2}, status='succeeded')
        self.native.handle(**args)
        self.native.handle(**args)
        report = self.native.ledger.report(run['run_id'])
        self.assertEqual(len(report['attempts']), 1)
        self.assertEqual(report['totals']['input_tokens'], 10)
        self.assertIsNone(report['totals']['cost_reported_usd'])

    def test_no_native_execution_is_promoted_to_quality_validated(self):
        run = self.native.handle(event='start', prompt='query', client='opencode', project='/demo')
        self.native.handle(event='finish', run_id=run['run_id'], status='succeeded', summary='ok')
        row = self.native.ledger.report(run['run_id'])['runs'][0]
        self.assertEqual(row['status'], 'completed_unvalidated')
        self.assertEqual(row['validation'], {'quality': 'not_measured'})

    def test_parent_report_includes_all_child_costs_and_retries(self):
        ledger = self.native.ledger
        parent = ledger.start_run('claude', '/demo', 'parent', {}, {})
        child = ledger.start_run('claude', '/demo', 'child', {}, {}, parent_id=parent)
        grandchild = ledger.start_run('claude', '/demo', 'retry child', {}, {}, parent_id=child)
        ledger.record_attempt(child, 'haiku', 'failed', {'input_tokens': 10, 'output_tokens': 2}, cost_reported_usd=.01)
        ledger.record_attempt(grandchild, 'sonnet', 'succeeded', {'input_tokens': 20, 'output_tokens': 3}, cost_reported_usd=.02)
        report = ledger.report(parent)
        self.assertEqual(len(report['runs']), 3)
        self.assertEqual(report['totals']['input_tokens'], 30)
        self.assertAlmostEqual(report['totals']['cost_reported_usd'], .03)

    def test_context_is_scoped_and_no_full_prompt_in_events(self):
        self.memory.store('other', 'something other project', project='/other', source='test')
        run = self.native.handle(event='start', prompt='something other project', client='claude-code', project='/demo')
        self.assertEqual(run['context']['memories'], [])
        self.assertLessEqual(len(self.native.ledger.report(run['run_id'])['runs'][0]['prompt_snippet']), 240)

    def test_finish_cannot_hide_a_failed_native_attempt(self):
        run = self.native.handle(event='start', prompt='query', client='opencode', project='/demo')
        self.native.handle(event='attempt',run_id=run['run_id'],event_id='a',status='failed')
        result = self.native.handle(event='finish',run_id=run['run_id'],status='succeeded')
        self.assertEqual(result['status'], 'failed')

