import json
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))
from memory.policy import Router


class PolicyTests(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.router = Router(self.root)
        self.addCleanup(self.tmp.cleanup)

    def test_complexity_and_client_models(self):
        self.assertEqual(self.router.plan('Liste arquivos', 'claude')['model'], 'claude-haiku-5-5')
        self.assertEqual(self.router.plan('Corrigir bug', 'claude')['model'], 'claude-sonnet-5-5')
        self.assertEqual(self.router.plan('Decisão de arquitetura', 'claude')['model'], 'claude-opus-5-5')
        self.assertEqual(self.router.plan('List files', 'codex')['effort'], 'low')
        self.assertEqual(self.router.plan('Implementar função', 'codex')['effort'], 'medium')
        self.assertEqual(self.router.plan('Arquitetura distribuída', 'codex')['model'], 'gpt-6-astra')
        self.assertEqual(self.router.plan('Liste', 'opencode')['model'], 'google/gemini-3.1-flash-lite')
        self.assertEqual(self.router.plan('Implemente', 'opencode')['model'], 'openai/gpt-5.6-sol')
        self.assertEqual(self.router.plan('Liste', 'agy')['model'], 'gemini-3.8-flash-low')

    def test_controls_and_manual_provider_preservation(self):
        for client in ['codex', 'agy']:
            decision = self.router.plan('Liste', client)
            self.assertEqual(decision['control'], 'dispatch_only')
            self.assertFalse(decision['allow_parallel'])
        self.assertTrue(self.router.plan('Liste', 'claude')['allow_parallel'])
        decision = self.router.plan('Arquitetura', 'opencode', current_model='account-x/private-model', mode='manual')
        self.assertEqual(decision['model'], 'account-x/private-model')
        self.assertEqual(decision['max_attempts'], 1)

    def test_validation_and_policy_limits(self):
        for kwargs in [{'client': 'bad'}, {'client': 'codex', 'mode': 'bad'}, {'client': 'codex', 'prompt': ''}, {'client': 'codex', 'current_model': '--evil', 'mode': 'manual'}]:
            args = dict(prompt='Liste', **{'client': 'codex'})
            args.update(kwargs)
            with self.assertRaises(ValueError):
                self.router.plan(**args)
        (self.root / 'regras').mkdir()
        (self.root / 'regras/orchestration.json').write_text(json.dumps({'version': 2, 'clients': {'codex': {'context_budget': 2000, 'max_attempts': 1}}}), encoding='utf8')
        decision = Router(self.root).plan('Liste', 'codex')
        self.assertEqual(decision['context_budget'], 2000)
        self.assertEqual(decision['max_attempts'], 1)
        (self.root / 'regras/orchestration.json').write_text(json.dumps({'clients': {'codex': {'max_attempts': 99}}}), encoding='utf8')
        with self.assertRaises(ValueError):
            Router(self.root).plan('Liste', 'codex')

    def test_provider_is_preserved_during_escalation(self):
        decision = self.router.plan('Liste', 'opencode', current_model='account-x/private-model')
        self.assertEqual(self.router.escalate(decision)['model'], 'account-x/private-model')

    def test_aliases_and_provider_profiles(self):
        for alias in ['claude-code', 'claude-desktop']:
            self.assertEqual(self.router.plan('Liste', alias)['client'], 'claude')
        self.assertEqual(self.router.plan('Liste', 'antigravity')['client'], 'agy')
        self.assertEqual(self.router.plan('Liste', 'opencode', current_model='openai/gpt-5.6-sol')['model'], 'openai/gpt-5.6-luna')
        self.assertEqual(self.router.plan('Implementar', 'opencode', current_model='google/gemini-3.1-flash-lite')['model'], 'google/gemini-3.6-flash')
        self.assertEqual(self.router.plan('Liste', 'claude-desktop')['control'], 'dispatch_only')
        self.assertFalse(self.router.plan('Liste', 'claude-desktop')['allow_parallel'])

    def test_malformed_config_is_rejected(self):
        (self.root / 'regras').mkdir()
        for config in [{'clients': []}, {'clients': {'claude': {'allow_parallel': 'false'}}}, {'clients': {'claude': {'profiles': [[4, 'low']] * 3}}}]:
            (self.root / 'regras/orchestration.json').write_text(json.dumps(config), encoding='utf8')
            with self.assertRaises(ValueError):
                self.router.plan('Liste', 'claude')
