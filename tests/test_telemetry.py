import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from memory import telemetry
from memory.core import Memory


def lines(*items):
    return '\n'.join(json.dumps(x) for x in items)


class ParserTests(unittest.TestCase):
    def test_unknown_fields_stay_unknown(self):
        result = telemetry.parse_result('codex', lines({'type': 'turn.completed'}))
        self.assertEqual(result['status'], 'succeeded')
        self.assertTrue(all(x is None for x in result['usage'].values()))
        self.assertIsNone(result['cost_reported_usd'])
        self.assertEqual(result['cost_kind'], 'unknown')

    def test_codex_final_usage_is_not_summed_and_message_is_extracted(self):
        final = {'type': 'turn.completed', 'usage': {'input_tokens': 100, 'output_tokens': 20, 'cached_input_tokens': 50}}
        result = telemetry.parse_result('codex', lines({'type': 'item.completed', 'item': {'type': 'agent_message', 'text': 'feito'}}, final, final))
        self.assertEqual(result['output'], 'feito')
        self.assertEqual(result['usage']['input_tokens'], 100)
        self.assertEqual(result['usage']['output_tokens'], 20)
        self.assertEqual(result['usage']['cached_input_tokens'], 50)

    def test_claude_result_usage_not_model_usage_or_stream_duplicate(self):
        final = {'type': 'result', 'subtype': 'success', 'result': 'pronto', 'usage': {'input_tokens': 12, 'output_tokens': 8, 'cache_read_input_tokens': 4, 'cache_creation_input_tokens': 3}, 'total_cost_usd': .02, 'modelUsage': {'claude-test': {'inputTokens': 12, 'outputTokens': 8}}}
        result = telemetry.parse_result('claude', lines({'type': 'assistant', 'message': {'usage': {'input_tokens': 12}}}, final, final))
        self.assertEqual(result['usage']['input_tokens'], 12)
        self.assertEqual(result['usage']['cached_input_tokens'], 4)
        self.assertEqual(result['usage']['cache_creation_input_tokens'], 3)
        self.assertEqual(result['cost_reported_usd'], .02)
        self.assertEqual(result['model_reported'], 'claude-test')
        self.assertEqual(result['output'], 'pronto')

    def test_agy_uses_last_cumulative_usage(self):
        result = telemetry.parse_result('antigravity', lines({'type': 'result', 'usage': {'input_tokens': 10, 'output_tokens': 2}}, {'type': 'result', 'output': 'fim', 'model': 'gemini-test', 'usage': {'input_tokens': 14, 'output_tokens': 5}}))
        self.assertEqual(result['usage']['input_tokens'], 14)
        self.assertEqual(result['usage']['output_tokens'], 5)
        self.assertEqual(result['model_reported'], 'gemini-test')

    def test_opencode_step_totals_deduplicate_and_zero_is_not_free(self):
        step = {'type': 'step_finish', 'part': {'id': 'a', 'cost': 0, 'tokens': {'input': 10, 'output': 2, 'reasoning': 1, 'cache': {'read': 3, 'write': 4}}}}
        last = {'type': 'step_finish', 'part': {'id': 'b', 'cost': 0, 'tokens': {'input': 15, 'output': 3}}}
        result = telemetry.parse_result('opencode', lines({'type': 'text', 'part': {'text': 'ok'}}, step, step, last))
        self.assertEqual(result['output'], 'ok')
        self.assertEqual(result['usage']['input_tokens'], 25)
        self.assertEqual(result['usage']['output_tokens'], 5)
        self.assertIsNone(result['usage']['cached_input_tokens'])  # Second step omitted cache, so total is unknown.
        self.assertEqual(result['cost_reported_usd'], 0)
        self.assertEqual(result['cost_kind'], 'reported_zero_not_verified_free')

    def test_failed_auth_and_nonzero_cannot_succeed(self):
        result = telemetry.parse_result('codex', lines({'type': 'error', 'message': 'authentication failed'}), 1)
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['errors'])
        self.assertEqual(telemetry.parse_result('claude', '{broken')['status'], 'failed')
        self.assertEqual(telemetry.parse_result('claude', lines({'type': 'result', 'is_error': True, 'result': 'denied'}))['status'], 'failed')


    def test_claude_model_usage_fallback_is_final_not_stream(self):
        result = telemetry.parse_result('claude', json.dumps({'type': 'result', 'result': 'ok', 'modelUsage': {'a': {'inputTokens': 4, 'outputTokens': 2}, 'b': {'inputTokens': 6, 'outputTokens': 3}}}))
        self.assertEqual(result['usage']['input_tokens'], 10)
        self.assertEqual(result['usage']['output_tokens'], 5)
        self.assertIsNone(result['model_reported'])

    def test_structured_error_without_type_fails(self):
        result = telemetry.parse_result('antigravity', json.dumps({'error': {'code': 401, 'message': 'authentication denied'}, 'usage': {'input_tokens': 0}}))
        self.assertEqual(result['status'], 'failed')
        self.assertTrue(result['errors'])

    def test_malformed_optional_metrics_remain_unknown(self):
        result = telemetry.parse_result('opencode', lines({'type': 'step_finish', 'part': {'tokens': {'input': -1, 'output': True, 'cache': 'unavailable'}, 'cost': 'unknown'}}))
        self.assertTrue(all(v is None for v in result['usage'].values()))
        self.assertIsNone(result['cost_reported_usd'])

    def test_unfinished_stream_and_unknown_harness_fail(self):
        self.assertEqual(telemetry.parse_result('codex', lines({'type': 'thread.started'}))['status'], 'failed')
        self.assertEqual(telemetry.parse_result('unknown', '{}')['status'], 'failed')

class LedgerTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.memory = Memory(self.tmp.name)
        self.ledger = telemetry.Ledger(self.memory)

    def tearDown(self):
        self.tmp.cleanup()

    def start(self, **extra):
        return self.ledger.start_run('codex', 'C:/project', 'tarefa', {'version': 1}, {'reason': 'fixture'}, **extra)

    def test_additive_schema_idempotency_and_restart(self):
        first = self.start(idempotency_key='same')
        self.assertEqual(first, self.start(idempotency_key='same'))
        self.assertNotEqual(first, self.ledger.start_run('claude', 'C:/project', 'tarefa', {}, {}, idempotency_key='same'))
        self.assertNotEqual(self.start(), self.start())
        report = telemetry.Ledger(self.memory).report(first)
        self.assertEqual(report['runs'][0]['id'], first)
        with self.memory.connection() as c:
            self.assertIsNotNone(c.execute("SELECT name FROM sqlite_master WHERE name='records'").fetchone())

    def test_attempts_accumulate_but_unknown_cost_stays_unknown(self):
        run = self.start()
        self.ledger.record_attempt(run, 'cheap', 'failed', {'input_tokens': 10}, cost_reported_usd=.01, error='bad')
        self.ledger.record_attempt(run, 'large', 'succeeded', {'input_tokens': 20, 'output_tokens': 5}, model_reported='actual', validation={'passed': True})
        self.ledger.finish_run(run, 'succeeded', 'done', {'passed': True})
        report = self.ledger.report(run)
        self.assertEqual(len(report['attempts']), 2)
        self.assertEqual(report['totals']['input_tokens'], 30)
        self.assertIsNone(report['totals']['cost_reported_usd'])
        self.assertEqual(report['runs'][0]['status'], 'succeeded')
        self.assertEqual(report['attempts'][1]['model_reported'], 'actual')

    def test_redacts_secrets_and_does_not_store_full_prompt(self):
        secret = 'sk-' + 'a' * 30
        run = self.ledger.start_run('codex', 'x', secret + ' x' * 300, {}, {})
        self.ledger.event(run, 'error', {'api_key': secret, 'prompt': 'conversation should not persist'})
        self.ledger.record_attempt(run, 'm', 'failed', error=secret, validation={'token': secret})
        self.ledger.finish_run(run, 'failed', secret)
        report = self.ledger.report(run)
        self.assertNotIn(secret, json.dumps(report))
        self.assertNotIn('conversation should not persist', json.dumps(report))
        self.assertLessEqual(len(report['runs'][0]['prompt_snippet']), 240)
        self.assertEqual(len(report['runs'][0]['prompt_hash']), 64)


if __name__ == '__main__':
    unittest.main()
