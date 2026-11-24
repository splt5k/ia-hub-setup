import json
import re
import sys
import tempfile
import unittest
from pathlib import Path
sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class ReadableGraphTests(unittest.TestCase):
    def setUp(self):
        from memory.core import Memory
        self.tmp = tempfile.TemporaryDirectory()
        self.root = Path(self.tmp.name)
        self.memory = Memory(self.root)

    def tearDown(self):
        self.tmp.cleanup()

    def test_human_names_stable_ids_and_no_index_star(self):
        a = self.memory.store('Decisão de persistência', 'A memória usa SQLite e MCP para compartilhar decisões.', project='IA-Hub', tags=['memória compartilhada'])
        path = self.memory.note_file(a['id'])
        self.assertIn('Decisão de persistência', path.stem)
        self.assertNotIn(a['id'], path.stem)
        self.assertIn('id: ' + a['id'], path.read_text(encoding='utf-8'))
        index = self.root / 'Memoria' / 'indice.md'
        self.assertNotIn('[[', index.read_text(encoding='utf-8'))
        for note in (self.root / 'Memoria').rglob('*.md'):
            self.assertNotIn('[[Memoria/indice', note.read_text(encoding='utf-8'))

    def test_title_collisions_do_not_merge_distinct_records(self):
        a = self.memory.store('Decisão', 'Usar SQLite.', project='a')
        b = self.memory.store('Decisão', 'Usar PostgreSQL.', project='b')
        self.assertNotEqual(self.memory.note_file(a['id']), self.memory.note_file(b['id']))
        self.assertTrue(self.memory.note_file(a['id']).exists())
        self.assertTrue(self.memory.note_file(b['id']).exists())

    def test_legacy_sources_are_linked_and_originals_untouched(self):
        source = self.root / 'contexto' / 'projetos' / 'IA-Hub.md'
        source.parent.mkdir(parents=True)
        content = '# IA-Hub\n\nDecisão: usar SQLite para preservar revisões e conectar agentes via MCP.\n'
        source.write_text(content, encoding='utf-8')
        self.memory.reconcile()
        item = self.memory.search('preservar revisões')[0]
        note = self.memory.note_file(item['id']).read_text(encoding='utf-8')
        self.assertIn('[[contexto/projetos/IA-Hub', note)
        self.assertEqual(source.read_text(encoding='utf-8'), content)
        self.assertTrue(any('SQLite' in p.stem for p in (self.root / 'Memoria' / 'assuntos').glob('*.md')))

    def test_rules_are_imported_with_history_without_modifying_source(self):
        source = self.root / 'regras' / 'nucleo.md'
        source.parent.mkdir(parents=True)
        source.write_text('# Regras compartilhadas\n\nMemória persistente entre Claude Code e Codex usando MCP.', encoding='utf-8')
        self.memory.reconcile()
        item = self.memory.search('Regras compartilhadas')[0]
        source.write_text('# Regras compartilhadas\n\nMemória persistente com SQLite, MCP e proveniência.', encoding='utf-8')
        self.memory.reconcile()
        self.assertEqual(self.memory.get(item['id'])['revision'], 2)

    def test_migration_preserves_ids_revisions_and_original_bytes(self):
        a = self.memory.store('Decisão legada', 'Conteúdo que precisa sobreviver à migração.', key='legacy')
        self.memory.store('Decisão legada', 'Conteúdo atualizado que precisa sobreviver à migração.', key='legacy')
        path = self.memory.note_file(a['id'])
        hashed = self.root / 'Memoria' / 'conhecimentos' / (a['id'] + '.md')
        if path != hashed:
            path.rename(hashed)
        with self.memory.connection() as c:
            c.execute("UPDATE records SET note_path='' WHERE id=?", (a['id'],))
        before = self.memory.get(a['id'])['revisions']
        report = self.memory.migrate_readable()
        self.assertEqual(self.memory.get(a['id'])['revisions'], before)
        self.assertTrue(self.memory.note_file(a['id']).exists())
        self.assertFalse(hashed.exists())
        self.assertTrue(Path(report['backup']).exists())

    def test_synthetic_validation_is_preserved_outside_knowledge_graph(self):
        a = self.memory.store('Decisão IA-Hub-E2E-012345', 'Dado sintético IA-Hub-E2E-012345 de validação entre agentes.', project='IA-Hub-E2E-012345')
        self.assertTrue(self.memory.note_file(a['id']).exists())
        self.assertNotIn('Memoria/conhecimentos', self.memory.note_file(a['id']).as_posix())
        self.assertEqual(self.memory.search('IA-Hub-E2E-012345', project='IA-Hub-E2E-012345')[0]['id'], a['id'])

    def test_legacy_decisions_become_distinct_sourced_knowledge(self):
        source = self.root / 'contexto' / 'projetos' / 'IA-Hub.md'
        source.parent.mkdir(parents=True)
        source.write_text('# IA-Hub\n\n## Decisões\n- 2026-10-15 Usar SQLite para preservar revisões.\n- 2026-10-15 Compartilhar descobertas por MCP.\n', encoding='utf-8')
        self.memory.reconcile()
        with self.memory.connection() as c:
            decisions = c.execute("SELECT id FROM records WHERE kind='decision'").fetchall()
        self.assertEqual(len(decisions), 2)
        for decision in decisions:
            record = self.memory.get(decision['id'])
            self.assertTrue(any(r['method'] == 'source-extracted' for r in record['relations']))
        count = self.memory.health()['records']
        self.memory.reconcile()
        self.assertEqual(self.memory.health()['records'], count)

    def test_obsidian_rename_is_reconciled_by_frontmatter_id(self):
        a = self.memory.store('Nome antigo', 'Decisão inicial que precisa continuar vinculada ao mesmo identificador.')
        old = self.memory.note_file(a['id'])
        renamed = old.with_name('Nome escolhido no Obsidian.md')
        old.rename(renamed)
        renamed.write_text(renamed.read_text(encoding='utf-8').replace('Decisão inicial', 'Decisão enriquecida'), encoding='utf-8')
        self.memory.reconcile()
        self.assertEqual(self.memory.note_file(a['id']), renamed)
        self.assertFalse(old.exists())
        self.assertIn('Decisão enriquecida', self.memory.get(a['id'])['content'])

    def test_topic_edits_are_preserved_and_searchable(self):
        self.memory.store('Banco', 'Persistência em SQLite.', tags=['SQLite'])
        path = self.root / 'Memoria' / 'assuntos' / 'SQLite.md'
        path.write_text(path.read_text(encoding='utf-8') + '\nAnotação humana: a configuração orquídea usa checkpoints periódicos.\n', encoding='utf-8')
        self.memory.store('Outra', 'Uma nova captura não deve apagar a anotação do assunto.')
        self.memory.reconcile()
        self.assertIn('orquídea', path.read_text(encoding='utf-8'))
        self.assertTrue(self.memory.search('orquídea'))

    def test_corrected_legacy_decision_has_history_and_current_content(self):
        source = self.root / 'contexto' / 'projetos' / 'IA-Hub.md'
        source.parent.mkdir(parents=True)
        source.write_text('# IA-Hub\n\n## Decisões\n- Usar SQLite no laboratório violeta.\n', encoding='utf-8')
        self.memory.reconcile()
        with self.memory.connection() as c:
            item_id = c.execute("SELECT id FROM records WHERE kind='decision'").fetchone()[0]
        source.write_text('# IA-Hub\n\n## Decisões\n- Usar PostgreSQL no laboratório violeta.\n', encoding='utf-8')
        self.memory.reconcile()
        decision = self.memory.get(item_id)
        self.assertEqual(decision['content'], 'Usar PostgreSQL no laboratório violeta.')
        self.assertEqual(decision['revision'], 2)

    def test_real_reference_that_mentions_test_marker_is_not_hidden(self):
        source = self.root / 'README.md'
        source.write_text('# Como validar a memória\n\nO procedimento usa o marcador IA-Hub-E2E para validar recuperação entre agentes.', encoding='utf-8')
        self.memory.reconcile()
        result = self.memory.search('procedimento')[0]
        self.assertIn('Memoria/conhecimentos', self.memory.note_file(result['id']).as_posix())

    def test_failed_projection_after_move_recovers_from_journal(self):
        from unittest.mock import patch
        a = self.memory.store('Nota preservada', 'Uma edição precisa sobreviver mesmo se a projeção falhar depois do movimento.')
        old = self.memory.note_file(a['id'])
        hashed = old.with_name(a['id'] + '.md')
        old.rename(hashed)
        with self.memory.connection() as c:
            c.execute('UPDATE records SET note_path=? WHERE id=?', (hashed.relative_to(self.root).as_posix(), a['id']))
        write = self.memory.write
        def fail_after_move(path, text):
            if 'conhecimentos' in path.parts:
                raise OSError('Falha de projeção simulada após rename')
            return write(path, text)
        with patch.object(self.memory, 'write', side_effect=fail_after_move):
            with self.assertRaises(OSError):
                self.memory.migrate_readable()
        self.memory.reconcile()
        self.assertTrue(self.memory.note_file(a['id']).exists())
        self.assertNotEqual(self.memory.note_file(a['id']).stem, a['id'])
        self.assertFalse(hashed.exists())
        self.assertEqual(self.memory.get(a['id'])['revision'], 1)

    def test_removed_legacy_decision_is_superseded_and_not_searched(self):
        source = self.root / 'contexto' / 'projetos' / 'IA-Hub.md'
        source.parent.mkdir(parents=True)
        source.write_text('# IA-Hub\n\n## Decisões\n- Usar SQLite no laboratório ametista.\n', encoding='utf-8')
        self.memory.reconcile()
        with self.memory.connection() as c:
            item_id = c.execute("SELECT id FROM records WHERE kind='decision'").fetchone()[0]
        source.write_text('# IA-Hub\n\n## Decisões\n', encoding='utf-8')
        self.memory.reconcile()
        self.assertEqual(self.memory.get(item_id)['status'], 'superseded')
        self.assertFalse(self.memory.search('ametista'))

    def test_explicit_validation_query_can_recover_archived_test(self):
        a = self.memory.store('Descoberta sintética', 'A descoberta de teste tem o identificador fictício verde.', project='IA-Hub-AUTO-CLAUDE-12345')
        self.assertEqual(self.memory.search('IA-Hub-AUTO-CLAUDE-12345 verde')[0]['id'], a['id'])
        self.assertFalse(self.memory.search('verde'))
