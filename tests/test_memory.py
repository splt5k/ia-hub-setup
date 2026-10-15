import concurrent.futures
import sys
import tempfile
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class MemoryTests(unittest.TestCase):
    def setUp(self):
        from memory.core import Memory
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.memory = Memory(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_persistence_and_exact_deduplication_across_agents(self):
        a = self.memory.store('Decisão', 'Utilizar SQLite para preservar decisões.', project='teste', source='claude')
        b = self.memory.store('Mesma decisão', 'Utilizar SQLite para preservar decisões.', project='teste', source='codex')
        self.assertEqual(a['id'], b['id'])
        self.assertTrue(b['deduplicated'])
        from memory.core import Memory
        saved = Memory(self.root).get(a['id'])
        self.assertEqual(saved['content'], 'Utilizar SQLite para preservar decisões.')
        self.assertEqual(set(saved['sources']), {'claude', 'codex'})

    def test_correction_keeps_revision_and_project_scope(self):
        a = self.memory.store('Porta', 'A porta é 1234.', project='a', key='porta')
        self.memory.store('Porta', 'A porta é 5678.', project='a', key='porta')
        other = self.memory.store('Porta', 'A porta é 5678.', project='b', key='porta')
        saved = self.memory.get(a['id'])
        self.assertEqual(saved['revision'], 2)
        self.assertEqual(saved['revisions'][0]['content'], 'A porta é 1234.')
        self.assertNotEqual(a['id'], other['id'])

    def test_concurrent_writes_are_not_lost(self):
        def write(i):
            return self.memory.store(f'Nota {i}', f'Conhecimento concorrente número {i}.', key=str(i))
        with concurrent.futures.ThreadPoolExecutor(max_workers=6) as pool:
            result = list(pool.map(write, range(18)))
        self.assertEqual(len({x['id'] for x in result}), 18)
        self.assertEqual(self.memory.health()['records'], 18)

    def test_search_handles_accents_and_punctuation_and_scopes(self):
        item = self.memory.store('Autenticação', 'A autenticação utiliza certificado local.', project='a')
        self.memory.store('Outro', 'Somente escopo diferente.', project='b')
        result = self.memory.search('autenticacao " certificado?!', project='a')
        self.assertEqual(result[0]['id'], item['id'])
        self.assertFalse(self.memory.search('certificado', project='b'))

    def test_relations_produce_resolved_obsidian_links(self):
        a = self.memory.store('Banco', 'Persistência com SQLite.', project='hub', tags=['memória'])
        b = self.memory.store('Busca', 'Recuperação do conhecimento.', project='hub', tags=['memória'])
        self.memory.relate(a['id'], b['id'], 'complementa')
        self.assertTrue(self.memory.get(a['id'])['relations'])
        note = self.memory.note_file(a['id'])
        text = note.read_text(encoding='utf-8')
        self.assertIn('[[Memoria/conhecimentos/' + self.memory.note_file(b['id']).stem, text)
        self.assertTrue((self.root / 'Memoria' / 'indice.md').exists())

    def test_manual_edit_is_imported_as_revision(self):
        item = self.memory.store('Manual', 'Texto original.', project='teste')
        note = self.memory.note_file(item['id'])
        note.write_text(note.read_text(encoding='utf-8').replace('Texto original.', 'Texto editado no Obsidian.'), encoding='utf-8')
        self.memory.reconcile()
        result = self.memory.get(item['id'])
        self.assertEqual(result['content'], 'Texto editado no Obsidian.')
        self.assertEqual(result['revision'], 2)

    def test_missing_projection_rebuild_and_legacy_import_are_idempotent(self):
        legacy = self.root / 'contexto' / 'projetos' / 'legado.md'
        legacy.parent.mkdir(parents=True)
        legacy.write_text('# Legado\n\nConhecimento preexistente sobre migração.', encoding='utf-8')
        self.memory.reconcile()
        count = self.memory.health()['records']
        item = self.memory.search('migração')[0]
        note = self.memory.note_file(item['id'])
        note.unlink()
        self.memory.reconcile()
        self.assertTrue(note.exists())
        self.assertEqual(self.memory.health()['records'], count)

    def test_secret_is_redacted(self):
        item = self.memory.store('Credencial', 'Authorization: Bearer abcdefghijklmnopqrstuvwxyz123456')
        self.assertNotIn('abcdefghijklmnopqrstuvwxyz123456', self.memory.get(item['id'])['content'])

    def test_projection_retries_transient_windows_sharing_violation(self):
        from unittest.mock import patch
        import os
        replace = os.replace
        attempts = [0]
        def transient(a, b):
            attempts[0] += 1
            if attempts[0] < 3:
                raise PermissionError('Obsidian está lendo o arquivo')
            return replace(a, b)
        with patch('memory.core.os.replace', side_effect=transient):
            item = self.memory.store('Compartilhamento', 'Gravação deve sobreviver ao bloqueio transitório de leitura.')
        self.assertEqual(self.memory.get(item['id'])['revision'], 1)

    def test_backfill_also_builds_semantic_relations(self):
        a = self.memory.store('Persistência', 'SQLite preserva conhecimento com histórico.')
        b = self.memory.store('Histórico', 'As revisões do conhecimento são mantidas no banco.')
        self.memory.embedder = lambda text: [1.0, 0.0]
        self.memory.backfill_vectors()
        self.assertTrue(self.memory.get(a['id'])['relations'])

    def test_json_and_codeblock_secrets_are_redacted(self):
        item = self.memory.store('Configuração', '```json\n{"api_key": "abcdef123456789012345", "password": "shortpass"}\n```\nTOKEN="somesecret12345678901234"')
        text = self.memory.get(item['id'])['content']
        for secret in ['abcdef123456789012345', 'shortpass', 'somesecret12345678901234']:
            self.assertNotIn(secret, text)

    def test_metadata_can_be_enriched_without_changing_fact(self):
        a = self.memory.store('Decisão', 'Utilizar um banco local.', key='db', tags=['persistência'])
        self.memory.store('Decisão validada', 'Utilizar um banco local.', key='db', tags=['SQLite'], status='validated')
        result = self.memory.get(a['id'])
        self.assertEqual(result['status'], 'validated')
        self.assertIn('SQLite', result['tags'])
        self.assertIn('persistência', result['tags'])

    def test_structural_conflict_is_visible(self):
        a = self.memory.store('Manual', 'Não perder edições com estrutura alterada.')
        path = self.memory.note_file(a['id'])
        path.write_text('Edição humana sem estrutura gerenciada', encoding='utf-8')
        self.memory.reconcile()
        self.assertEqual(self.memory.health()['projection_conflicts'], 1)
        self.assertEqual(path.read_text(encoding='utf-8'), 'Edição humana sem estrutura gerenciada')

    def test_project_filter_precedes_textual_limit(self):
        with self.memory.connection() as c:
            for i in range(105):
                c.execute('INSERT INTO text_search VALUES (?,?,?,?)', ('noise-' + str(i), 'certificado certificado', 'certificado', ''))
        a = self.memory.store('Certificado', 'certificado local', project='meu-projeto')
        self.assertEqual(self.memory.search('certificado', project='meu-projeto')[0]['id'], a['id'])

    def test_online_backup_preserves_consistent_revision(self):
        import sqlite3
        a = self.memory.store('Backup', 'Revisão anterior.', key='backup')
        snapshot = self.memory.backup()
        self.memory.store('Backup', 'Revisão posterior.', key='backup')
        with sqlite3.connect(snapshot) as c:
            self.assertEqual(c.execute('SELECT content FROM records WHERE id=?', (a['id'],)).fetchone()[0], 'Revisão anterior.')
        c.close()


if __name__ == '__main__':
    unittest.main()
