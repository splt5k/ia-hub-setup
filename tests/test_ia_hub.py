"""Testes auditáveis do payload em src/. Rodar: python -m unittest discover -s tests -v

Cobrem comportamento real (daemon + SQLite + notas Markdown em pasta temporária).
NÃO substituem testes com CLIs logados: ver docs/validacao.md.
"""
import json
import os
import shutil
import socket
import subprocess
import sys
import tempfile
import unittest
import unittest.mock
from pathlib import Path

REPO = Path(__file__).resolve().parents[1]
SRC = REPO / 'src'
sys.path.insert(0, str(SRC / 'scripts'))


def free_port():
    with socket.socket() as s:
        s.bind(('127.0.0.1', 0))
        return s.getsockname()[1]


class BuildSync(unittest.TestCase):
    def test_installers_match_source(self):
        r = subprocess.run([sys.executable, str(REPO / 'tools/build.py'), '--check'], capture_output=True, text=True)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)


class RiskAwareRouting(unittest.TestCase):
    def test_security_wording_never_falls_to_low_tier(self):
        from memory.policy import Router
        router = Router(SRC)
        self.assertEqual(router.plan('revise as permissões de acesso', 'claude-code')['tier'], 2)
        self.assertIn('risk_sensitive_floor_high', router.plan('revise as permissões de acesso', 'claude-code')['reasons'])

    def test_destructive_operation_floors_to_medium(self):
        from memory.policy import Router
        plan = Router(SRC).plan('ajuste a migração do banco', 'claude-code')
        self.assertEqual(plan['tier'], 1)
        self.assertIn('risk_operation_floor_medium', plan['reasons'])

    def test_single_hard_word_does_not_reach_opus(self):
        from memory.policy import Router
        self.assertEqual(Router(SRC).plan('isso é complexo? some 17 + 28', 'claude-code')['tier'], 1)
        self.assertEqual(Router(SRC).plan('proponha a arquitetura do cache', 'claude-code')['tier'], 1)

    def test_accumulated_signals_escalate_to_high(self):
        from memory.policy import Router
        plan = Router(SRC).plan('investigue o bug intermitente de concorrência e corrija', 'claude-code')
        self.assertEqual((plan['tier'], plan['effort']), (2, 'high'))
        self.assertIn('signal_heavy', plan['reasons'])

    def test_claude_subagents_never_get_opus(self):
        from memory.policy import Router
        plan = Router(SRC).plan('revise as permissões de acesso em produção e corrija o bug intermitente', 'claude-code')
        self.assertEqual((plan['tier'], plan['model'], plan['effort']), (2, 'claude-sonnet-5-5', 'high'))
        self.assertEqual(plan['max_active_agents'], 0)

    def test_escalation_after_failure_still_reaches_high(self):
        from memory.policy import Router
        router = Router(SRC)
        self.assertEqual(router.escalate(router.plan('corrija o bug', 'claude-code'))['tier'], 2)

    def test_plain_question_stays_low(self):
        from memory.policy import Router
        self.assertEqual(Router(SRC).plan('qual a diferença entre listas e tuplas?', 'claude-code')['tier'], 0)


class OpenCodeIsMemoryOnly(unittest.TestCase):
    def test_router_rejects_opencode(self):
        from memory.policy import Router
        router = Router(SRC)
        self.assertEqual(router.plan('corrija o bug', 'claude-code')['client'], 'claude')
        with self.assertRaises(ValueError):
            router.plan('qualquer coisa', 'opencode')

    def test_policy_and_config_have_no_opencode_routing(self):
        policy = json.loads((SRC / 'regras/orchestration.json').read_text(encoding='utf-8'))
        self.assertNotIn('opencode', policy['clients'])
        cfg = (SRC / 'opencode/opencode.jsonc').read_text(encoding='utf-8')
        for forbidden in ('default_agent', 'subagent_depth', 'whitelist', 'orchestrator'):
            self.assertNotIn(forbidden, cfg)
        self.assertFalse((SRC / 'opencode/agents').exists())

    @unittest.skipUnless(shutil.which('node'), 'node ausente')
    def test_plugins_have_valid_javascript_syntax(self):
        for name in ('scripts/memory/opencode-plugin.js',):
            code = (SRC / name).read_text(encoding='utf-8').replace('__PYTHON__', '"python"').replace('__ENTRY__', '"entry.py"')
            with tempfile.TemporaryDirectory() as d:
                target = Path(d) / 'plugin.mjs'
                target.write_text(code, encoding='utf-8')
                r = subprocess.run(['node', '--check', str(target)], capture_output=True, text=True)
                self.assertEqual(r.returncode, 0, name + ': ' + r.stderr[-400:])

    def test_plugin_never_calls_orchestration(self):
        js = (SRC / 'scripts/memory/opencode-plugin.js').read_text(encoding='utf-8')
        for forbidden in ('orchestration', 'modelID', 'providerID', 'chat.message', 'IA_HUB_ROUTING_MODE'):
            self.assertNotIn(forbidden, js)
        self.assertIn("rpc('context'", js)
        self.assertIn("rpc('observe'", js)

    def test_mcp_exposes_orchestration_only_outside_opencode(self):
        text = (SRC / 'scripts/memory/server.py').read_text(encoding='utf-8')
        guard = text.index("if client != 'opencode'")
        self.assertLess(guard, text.index('def orchestration_plan'))
        self.assertGreater(guard, text.index('def memory_health'))

    def test_legacy_cleanup_preserves_customizations(self):
        from memory.opencode_cleanup import clean_config, clean_files
        legacy = {'default_agent': 'orchestrator', 'subagent_depth': 1, 'model': 'meu/modelo',
                  'provider': {'openai': {'whitelist': ['gpt-5.6-luna', 'gpt-5.6-sol', 'gpt-5.6-terra']}, 'x': {'a': 1}},
                  'mcp': {'ia_hub': {}}}
        removed = clean_config(legacy)
        self.assertIn('default_agent', removed)
        self.assertEqual(legacy['model'], 'meu/modelo')          # personalizado: fica
        self.assertEqual(legacy['provider'], {'x': {'a': 1}})     # só o bloco exato do hub sai
        with tempfile.TemporaryDirectory() as d:
            agents = Path(d) / 'agents'
            agents.mkdir()
            (agents / 'architect.md').write_text('meu agente próprio', encoding='utf-8')
            self.assertEqual(clean_files(d, lambda p: None), [])
            self.assertTrue((agents / 'architect.md').exists())


class WindowsHookCommand(unittest.TestCase):
    def test_hook_command_survives_bash_and_has_no_backslashes(self):
        from memory.install import windows_command
        python = 'C:' + chr(92) + 'Users' + chr(92) + 'Fulano Silva' + chr(92) + 'IA-Hub' + chr(92) + 'python.exe'
        entry = 'C:' + chr(92) + 'Users' + chr(92) + 'Fulano Silva' + chr(92) + 'IA-Hub' + chr(92) + 'entry.py'
        command = windows_command([python, entry, 'hook', 'claude'])
        self.assertNotIn(chr(92), command)
        self.assertEqual(command, '"C:/Users/Fulano Silva/IA-Hub/python.exe" "C:/Users/Fulano Silva/IA-Hub/entry.py" hook claude')
        bash = shutil.which('bash')
        if bash and 'system32' in bash.lower():
            git_bash = Path(os.environ.get('ProgramFiles', 'C:/Program Files')) / 'Git/bin/bash.exe'
            bash = str(git_bash) if git_bash.exists() else None
        if bash:   # o bash precisa enxergar os mesmos quatro argumentos
            r = subprocess.run([bash, '-c', 'for a in ' + command + '; do echo "[$a]"; done'], capture_output=True, text=True)
            self.assertIn('[C:/Users/Fulano Silva/IA-Hub/python.exe]', r.stdout)
            self.assertIn('[C:/Users/Fulano Silva/IA-Hub/entry.py]', r.stdout)


    @unittest.skipUnless(shutil.which('powershell') or shutil.which('pwsh'), 'PowerShell ausente')
    def test_antigravity_hook_command_parses_in_powershell(self):
        from memory.install import powershell_command
        shell = shutil.which('powershell') or shutil.which('pwsh')
        sep = chr(92)
        for base in ('C:' + sep + 'Users' + sep + 'Fulano' + sep + 'IA-Hub', 'C:' + sep + 'Users' + sep + 'Fulano Silva' + sep + 'IA-Hub'):
            command = powershell_command([base + sep + 'python.exe', base + sep + 'entry.py', 'hook', 'antigravity-context'])
            check = "$e=$null; [void][System.Management.Automation.Language.Parser]::ParseInput($env:HUB_CMD,[ref]$null,[ref]$e); $e.Count"
            r = subprocess.run([shell, '-NoProfile', '-Command', check], capture_output=True, text=True, env=dict(os.environ, HUB_CMD=command))
            self.assertEqual(r.stdout.strip(), '0', command + ' ' + r.stderr[-300:])


class CliOutputParsing(unittest.TestCase):
    def test_antigravity_1_3_json_is_parsed(self):
        from memory.telemetry import parse_result
        raw = json.dumps({'conversation_id': 'x', 'status': 'SUCCESS', 'response': '45' + chr(10), 'num_turns': 1,
                          'usage': {'input_tokens': 17811, 'output_tokens': 2, 'thinking_tokens': 0, 'cache_read_tokens': 5, 'total_tokens': 17813}})
        r = parse_result('agy', raw, 0)
        self.assertEqual(r['status'], 'succeeded')
        self.assertEqual(r['output'].strip(), '45')
        self.assertEqual((r['usage']['input_tokens'], r['usage']['cached_input_tokens'], r['usage']['reasoning_output_tokens']), (17811, 5, 0))

    def test_failed_status_is_not_success(self):
        from memory.telemetry import parse_result
        self.assertEqual(parse_result('agy', json.dumps({'status': 'FAILED', 'response': ''}), 0)['status'], 'failed')


class OpenCodeLegacySignature(unittest.TestCase):
    def test_full_legacy_set_with_older_content_is_removed_but_lone_agent_is_kept(self):
        from memory.opencode_cleanup import LEGACY_AGENTS, ORCHESTRATOR_SIGNATURE, clean_files
        with tempfile.TemporaryDirectory() as d:
            agents = Path(d) / 'agents'
            agents.mkdir()
            for name in LEGACY_AGENTS:
                (agents / name).write_text('geração antiga ' + name, encoding='utf-8')
            (agents / 'orchestrator.md').write_text('---\ndescription: ' + ORCHESTRATOR_SIGNATURE + '\n---', encoding='utf-8')
            saved = []
            removed = clean_files(d, saved.append)
            self.assertEqual(len(removed), len(LEGACY_AGENTS))
            self.assertEqual(len(saved), len(LEGACY_AGENTS))             # backup antes de remover
            self.assertEqual(list(agents.iterdir()), [])
        with tempfile.TemporaryDirectory() as d:
            agents = Path(d) / 'agents'
            agents.mkdir()
            (agents / 'architect.md').write_text('meu próprio architect', encoding='utf-8')
            self.assertEqual(clean_files(d, lambda p: None), [])


class PortCoexistence(unittest.TestCase):
    def test_foreign_listener_gets_other_port_and_is_left_alone(self):
        from unittest import mock
        from memory import client
        with socket.socket() as foreign, tempfile.TemporaryDirectory() as d:
            foreign.bind(('127.0.0.1', 0))
            foreign.listen()
            busy = foreign.getsockname()[1]
            env = {k: v for k, v in os.environ.items() if k != 'IA_HUB_PORT'}
            with mock.patch.dict(os.environ, env, clear=True), mock.patch.object(client, 'STATE', Path(d)),                     mock.patch.object(client, 'DEFAULT_PORT', busy), mock.patch.object(client, 'PORT', busy):
                client.preflight()
                chosen = int((Path(d) / 'port').read_text())
                self.assertNotEqual(chosen, busy)
                self.assertEqual(client.read_port(Path(d)), chosen)
                self.assertEqual(client.PORT, chosen)
            self.assertEqual(foreign.getsockname()[1], busy)   # o serviço alheio continua intacto


class LockIsNotHeldDuringSlowWork(unittest.TestCase):
    """O lock global serializa todo RPC: trabalho lento de fundo não pode retê-lo (hook corta em 20 s)."""

    def setUp(self):
        from memory.core import Memory
        self.root = Path(tempfile.mkdtemp(prefix='ia-hub-lock-'))
        (self.root / 'contexto').mkdir()
        self.memory = Memory(self.root)

    def tearDown(self):
        shutil.rmtree(self.root, ignore_errors=True)

    def test_transcript_parse_runs_outside_global_lock(self):
        from memory import capture as capture_module
        cap = capture_module.Capture(self.memory)
        transcript = self.root / 'sessao.jsonl'
        message = {'type': 'assistant', 'cwd': str(self.root),
                   'message': {'stop_reason': 'end_turn', 'content': [{'type': 'text', 'text': 'Resposta final longa o bastante para ser capturada pelo hub.'}]}}
        transcript.write_text(json.dumps(message) + '\n', encoding='utf-8')
        held, original = [], capture_module.json.loads
        def spy(*a, **k):
            if isinstance(a[0], bytes):   # só linhas do transcript; tags do store são str
                held.append(self.memory.lock._is_owned())
            return original(*a, **k)
        with unittest.mock.patch.object(capture_module.json, 'loads', spy):
            self.assertEqual(cap.ingest(transcript, 'claude'), 1)
        self.assertEqual(held, [False])
        self.assertEqual(cap.ingest(transcript, 'claude'), 0)   # cursor avançou: sem recaptura

    def test_reconcile_skips_legacy_sync_when_files_unchanged(self):
        import memory.legacy as legacy
        note = self.root / 'contexto' / 'nota.md'
        note.write_text('# Nota\n\nConteúdo do usuário.\n', encoding='utf-8')
        calls = []
        with unittest.mock.patch.object(legacy, 'sync', lambda m: calls.append(1)):
            self.memory.reconcile()
            self.memory.reconcile()
            self.assertEqual(len(calls), 1)
            note.write_text('# Nota\n\nConteúdo do usuário, editado.\n', encoding='utf-8')
            self.memory.reconcile()
            self.assertEqual(len(calls), 2)


    def test_archived_unused_node_does_not_dirty_every_record(self):
        from memory.layout import Projector
        self.memory.store('Registro', 'Conteúdo qualquer para projetar no cofre do hub.', project=str(self.root), tags=['assunto-x'])
        self.memory.project_dirty()
        with self.memory.connection() as c:
            c.execute('UPDATE records SET tags=?', (json.dumps([]),))   # assunto-x deixa de ser usado
            c.execute('UPDATE records SET dirty=1')
        self.memory.project_dirty()                                   # arquiva a nota do nó sem uso
        self.assertTrue(list((self.memory.state / 'unused-nodes').glob('*.md')))
        Projector(self.memory).discover_renames()
        with self.memory.connection() as c:
            self.assertEqual(c.execute('SELECT count(*) FROM records WHERE dirty=1').fetchone()[0], 0)


    def test_backfill_embeds_outside_lock_and_only_missing_vectors(self):
        self.memory.store('Com vetor', 'Registro que já tinha vetor antes do embedder existir.', project=str(self.root))
        with self.memory.connection() as c:
            c.execute('UPDATE records SET vector=?', (json.dumps([1.0, 0.0]),))
        self.memory.store('Sem vetor', 'Registro gravado sem embedder ainda carregado.', project=str(self.root))
        held, related = [], []
        def embedder(text):
            held.append(self.memory.lock._is_owned())
            return [1.0, 0.0]
        self.memory.embedder = embedder
        original = self.memory.semantic_relations
        self.memory.semantic_relations = lambda c, item_id, vector: (related.append(item_id), original(c, item_id, vector))
        self.memory.backfill_vectors()
        self.assertEqual(held, [False])
        self.assertEqual(len(related), 1)   # só o registro sem vetor; não recalcula todos contra todos


class ExclusiveDaemonPort(unittest.TestCase):
    def test_second_daemon_cannot_bind_same_port(self):
        from memory.daemon import ExclusiveServer
        from http.server import BaseHTTPRequestHandler
        first = ExclusiveServer(('127.0.0.1', 0), BaseHTTPRequestHandler)
        try:
            with self.assertRaises(OSError):
                ExclusiveServer(('127.0.0.1', first.server_address[1]), BaseHTTPRequestHandler)
        finally:
            first.server_close()


class RealMemoryRoundTrip(unittest.TestCase):
    """Daemon real em pasta temporária: escrita por um cliente, leitura por outro, nota no cofre."""

    @classmethod
    def setUpClass(cls):
        cls.tmp = Path(tempfile.mkdtemp(prefix='ia-hub-test-'))
        shutil.copytree(SRC / 'scripts', cls.tmp / 'scripts', ignore=shutil.ignore_patterns('__pycache__', 'web'))
        shutil.copytree(SRC / 'regras', cls.tmp / 'regras')
        cls.env = dict(os.environ, IA_HUB_PORT=str(free_port()), IA_HUB_TEST_NO_EMBEDDINGS='1',
                       IA_HUB_TEST_NO_CAPTURE='1', PYTHONIOENCODING='utf-8')
        cls.entry = str(cls.tmp / 'scripts/memory/entry.py')

    @classmethod
    def tearDownClass(cls):
        import signal, time
        try:
            pid = json.loads(subprocess.run([sys.executable, cls.entry, 'health'], env=cls.env, capture_output=True,
                                            text=True, timeout=60).stdout)['pid']
            os.kill(pid, signal.SIGTERM)   # o daemon de teste é nosso; porta aleatória, pasta temporária
        except Exception:
            pass
        if os.name == 'nt':   # launcher/pythonw pode ter PID distinto do informado no health
            subprocess.run(['powershell', '-NoProfile', '-Command',
                            "Get-CimInstance Win32_Process | ? { $_.CommandLine -like '*" + cls.tmp.name + "*' } | % { Stop-Process -Id $_.ProcessId -Force }"],
                           capture_output=True)
        for _ in range(20):
            time.sleep(.5)
            shutil.rmtree(cls.tmp, ignore_errors=True)
            if not cls.tmp.exists():
                break

    def rpc(self, action, args=None, check=True):
        r = subprocess.run([sys.executable, self.entry, action], input=json.dumps(args or {}), env=self.env,
                           capture_output=True, text=True, encoding='utf-8', timeout=90)
        if check:
            self.assertEqual(r.returncode, 0, r.stderr[-800:])
            return json.loads(r.stdout)
        return r

    def test_cross_client_memory_and_vault_note(self):
        project = str(self.tmp / 'projeto-x')
        stored = self.rpc('store', dict(title='Decisão de teste', content='Usar SQLite WAL para a memória compartilhada local do hub.',
                                        project=project, source='claude-code', key='teste:decisao', tags=['teste']))
        again = self.rpc('store', dict(title='Decisão de teste', content='Usar SQLite WAL para a memória compartilhada local do hub.',
                                       project=project, source='codex', key='teste:decisao', tags=['teste']))
        self.assertEqual(stored['id'], again['id'])                      # dedup por key estável
        ctx = self.rpc('context', dict(query='SQLite WAL memória', project=project))   # leitura como outro cliente
        self.assertTrue(any('SQLite WAL' in m['content'] for m in ctx['memories']))
        notes = list((self.tmp / 'Memoria').rglob('*.md'))
        self.assertTrue(any('SQLite WAL' in n.read_text(encoding='utf-8') for n in notes), 'sem nota Markdown no cofre')

    def test_product_docs_are_not_imported_as_memory(self):
        (self.tmp / 'README.md').write_text('# Produto\nTexto do produto, nao e conhecimento.', encoding='utf-8')
        (self.tmp / 'contexto/projetos').mkdir(parents=True, exist_ok=True)
        (self.tmp / 'contexto/projetos/meuapp.md').write_text('# Meu app\n## Decisões\n- Usar PostgreSQL por causa de JSON e transações.\n', encoding='utf-8')
        self.rpc('reconcile')
        found = self.rpc('search', dict(query='PostgreSQL JSON transações', limit=5))
        self.assertTrue(any('PostgreSQL' in r['content'] for r in found))
        titles = [r['title'] for r in self.rpc('search', dict(query='Texto do produto conhecimento', limit=5))]
        self.assertNotIn('Produto', titles)

    def test_installer_backups_are_not_imported_and_old_product_records_are_retired(self):
        backup = self.tmp / 'contexto/.setup/backups/20260101-000000/docs'
        backup.mkdir(parents=True, exist_ok=True)
        (backup / 'copia.md').write_text('# Copia de backup do instalador\nTexto de backup unico zorblax.', encoding='utf-8')
        self.rpc('store', dict(title='Doc antigo do produto', content='Plano antigo do produto quuxplan.', project=str(self.tmp),
                               source='file:docs', key='legacy:docs/superpowers/plans/antigo.md', kind='reference-document', status='reference'))
        self.assertTrue(self.rpc('search', dict(query='quuxplan', limit=5)))      # antes: recuperável
        for _ in range(3):
            self.rpc('reconcile')
        self.assertEqual(self.rpc('search', dict(query='zorblax backup', limit=5)), [])   # backup nunca importado
        self.assertEqual(self.rpc('search', dict(query='quuxplan', limit=5)), [])         # registro do produto aposentado

    def test_daemon_refuses_opencode_orchestration(self):
        r = self.rpc('orchestration_plan', dict(prompt='x', client='opencode'), check=False)
        self.assertNotEqual(r.returncode, 0)
        ok = self.rpc('orchestration_plan', dict(prompt='implemente feature', client='claude-code'))
        self.assertEqual(ok['model'], 'claude-sonnet-5-5')


if __name__ == '__main__':
    unittest.main()
