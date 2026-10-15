"""Nomes legíveis, IDs em metadados e relações sem nó índice artificial."""
import json
import os
import re
import shutil
import sqlite3
import uuid
from pathlib import Path
from .core import digest, normalize, now


def readable(text):
    text = re.sub(r'[<>:"/\\|?*#^\[\]%\x00-\x1f]', ' ', text)
    text = re.sub(r'\s+', ' ', text).strip(' .-_')[:110].rstrip(' .') or 'Conhecimento'
    if re.fullmatch(r'(?i)CON|PRN|AUX|NUL|COM[0-9]|LPT[0-9]', text):
        text = 'Nota ' + text
    return text


class Projector:
    def __init__(self, memory):
        self.m = memory

    def allocate(self, c, folder, title):
        stem = readable(title)
        existing = {r[0].casefold() for r in c.execute("SELECT note_path FROM records WHERE note_path!='' UNION SELECT note_path FROM nodes")}
        for n in range(1, 10000):
            name = stem if n == 1 else f'{stem} ({n})'
            rel = folder + '/' + name + '.md'
            if rel.casefold() not in existing and not (self.m.root / rel).exists():
                return rel
        raise ValueError('Não foi possível reservar nome legível.')

    def move(self, table, item_id, old, target):
        journal = self.m.state / 'moves' / (table + '-' + item_id + '.json')
        self.m.write(journal, json.dumps({'table': table, 'id': item_id, 'from': old.relative_to(self.m.root).as_posix(), 'to': target.relative_to(self.m.root).as_posix()}))
        target.parent.mkdir(parents=True, exist_ok=True)
        old.rename(target)

    def discover_renames(self):
        with self.m.lock, self.m.connection() as c:
            for journal in (self.m.state / 'moves').glob('*.json'):
                move = json.loads(journal.read_text(encoding='utf-8'))
                if move['table'] not in ('records', 'nodes'):
                    continue
                old, target = ((self.m.root / move[k]).resolve() for k in ('from', 'to'))
                if not old.is_relative_to(self.m.root) or not target.is_relative_to(self.m.root):
                    continue
                if not old.exists() and target.exists():
                    row = c.execute('SELECT note_path FROM ' + move['table'] + ' WHERE id=?', (move['id'],)).fetchone()
                    if row and row['note_path'] in ('', move['from']):
                        c.execute('UPDATE ' + move['table'] + ' SET note_path=? WHERE id=?', (move['to'], move['id']))
            candidates = {}
            for folder in [self.m.root / 'Memoria', self.m.state / 'validacoes']:
                for path in folder.rglob('*.md'):
                    with path.open(encoding='utf-8') as f:
                        header = f.read(1024)
                    match = re.match(r'---\s*\nid:\s*([a-z0-9]+)\s*\n', header)
                    if match:
                        candidates.setdefault(match[1], []).append(path)
            for table in ['records', 'nodes']:
                for row in c.execute('SELECT id,note_path FROM ' + table).fetchall():
                    if row['note_path'] and (self.m.root / row['note_path']).exists():
                        continue
                    found = candidates.get(row['id'], [])
                    if len(found) == 1:
                        c.execute('UPDATE ' + table + ' SET note_path=? WHERE id=?', (found[0].relative_to(self.m.root).as_posix(), row['id']))
                        if table == 'nodes':
                            c.execute('UPDATE records SET dirty=1')
                    elif table == 'nodes' and not found:
                        c.execute('UPDATE records SET dirty=1')

    def import_node_edits(self):
        with self.m.lock, self.m.connection() as c:
            nodes = c.execute('SELECT * FROM nodes').fetchall()
        for node in nodes:
            path = self.m.root / node['note_path']
            if not path.exists():
                continue
            text = path.read_text(encoding='utf-8')
            current_hash = digest(text)
            if not node['projection_hash']:
                with self.m.connection() as c:
                    c.execute('UPDATE nodes SET projection_hash=? WHERE id=?', (current_hash, node['id']))
            elif current_hash != node['projection_hash']:
                with self.m.connection() as c:
                    c.execute('UPDATE nodes SET projection_hash=? WHERE id=?', (current_hash, node['id']))
                body = re.sub(r'^---\s*\n[\s\S]*?\n---\s*\n', '', text).strip()
                self.m.store(('Assunto — ' if node['kind'] == 'topic' else 'Projeto — ') + node['title'], body, project=str(self.m.root), source='file:' + str(path), key='node:' + node['id'], tags=[node['title']], kind='topic-note', status='reported')

    def record_path(self, c, row):
        folder = 'contexto/.memory/validacoes' if row['is_test'] else 'Memoria/conhecimentos'
        if row['note_path'] and row['note_path'].startswith(folder + '/') and not re.fullmatch('[0-9a-f]{16,40}', Path(row['note_path']).stem):
            return row['note_path']
        rel = self.allocate(c, folder, row['title'])
        old = self.m.root / row['note_path'] if row['note_path'] else self.m.root / 'Memoria' / 'conhecimentos' / (row['id'] + '.md')
        target = self.m.root / rel
        if old.exists():
            self.move('records', row['id'], old, target)
        c.execute('UPDATE records SET note_path=? WHERE id=?', (rel, row['id']))
        return rel

    def node(self, c, kind, key, title):
        row = c.execute('SELECT * FROM nodes WHERE kind=? AND entity_key=?', (kind, key)).fetchone()
        if row:
            return row['note_path']
        folder = 'Memoria/projetos' if kind == 'project' else 'Memoria/assuntos'
        rel = self.allocate(c, folder, title)
        item_id = uuid.uuid4().hex[:20]
        c.execute('INSERT INTO nodes (kind,entity_key,id,title,note_path) VALUES (?,?,?,?,?)', (kind, key, item_id, title, rel))
        old = self.m.root / folder / (digest(key)[:16] + '.md')
        path = self.m.root / rel
        if old.exists():
            self.move('nodes', item_id, old, path)
        return rel

    @staticmethod
    def link(path, label):
        return '[[' + Path(path).with_suffix('').as_posix() + '|' + str(label).replace('|', ' ').replace('[', '').replace(']', '') + ']]'

    def project(self):
        self.discover_renames()
        with self.m.lock, self.m.connection() as c:
            rows = c.execute('SELECT * FROM records ORDER BY created,id').fetchall()
            for row in rows:
                self.record_path(c, row)
            rows = c.execute('SELECT * FROM records WHERE dirty=1').fetchall()
            for row in rows:
                path = self.m.root / row['note_path']
                if path.exists() and row['projection_hash'] and digest(path.read_text(encoding='utf-8')) != row['projection_hash']:
                    continue
                lines = ['---', f'id: {row["id"]}', 'managed_by: ia-hub', f'revision: {row["revision"]}', 'type: ' + row['kind'], 'status: ' + row['status'], '---', '# ' + row['title'], '', row['content'], '', '<!-- ia-hub:relations -->', '', '## Contexto e relações', '']
                if not row['is_test']:
                    if row['project']:
                        title = row['project'].replace('\\', '/').rstrip('/').split('/')[-1].removeprefix('legacy:')
                        rel = self.node(c, 'project', row['project'], title)
                        lines.append('- Projeto: ' + self.link(rel, title))
                    for tag in json.loads(row['tags']):
                        if tag in ('sessão', 'claude', 'codex', 'antigravity', 'opencode'):
                            continue  # Origem técnica fica na proveniência, não vira assunto artificial.
                        if row['project'] and tag.casefold() == row['project'].replace('\\', '/').split('/')[-1].removeprefix('legacy:').casefold():
                            continue
                        rel = self.node(c, 'topic', normalize(tag), tag)
                        lines.append('- Assunto: ' + self.link(rel, tag))
                    for relation in c.execute('SELECT * FROM relations WHERE a=? OR b=?', (row['id'], row['id'])):
                        other = relation['b'] if relation['a'] == row['id'] else relation['a']
                        target = c.execute('SELECT title,note_path,is_test FROM records WHERE id=?', (other,)).fetchone()
                        if target and not target['is_test']:
                            lines.append(f'- {relation["kind"]}: {self.link(target["note_path"], target["title"])} ({relation["method"]}, {relation["score"]:.3f})')
                lines += ['', '## Proveniência', '', f'- Tipo: {row["kind"]}; estado: {row["status"]}; revisão: {row["revision"]}', '- Atualizado: ' + row['updated']]
                for source in c.execute('SELECT source FROM sources WHERE id=?', (row['id'],)):
                    value = source[0]
                    if value.startswith('file:'):
                        source_path = Path(value[5:]).resolve()
                        if source_path.is_relative_to(self.m.root) and source_path.exists():
                            lines.append('- Fonte original: ' + self.link(source_path.relative_to(self.m.root).as_posix(), source_path.stem))
                            continue
                    lines.append('- ' + value)
                text = '\n'.join(lines) + '\n'
                self.m.write(path, text)
                c.execute('UPDATE records SET projection_hash=?,dirty=0 WHERE id=?', (digest(text), row['id']))
            active_nodes = set()
            for record in c.execute('SELECT project,tags FROM records WHERE is_test=0'):
                if record['project']:
                    active_nodes.add(('project', record['project']))
                active_nodes.update(('topic', normalize(tag)) for tag in json.loads(record['tags']))
            for node in c.execute('SELECT * FROM nodes').fetchall():
                if (node['kind'], node['entity_key']) not in active_nodes:
                    path = self.m.root / node['note_path']
                    if path.exists():
                        target = self.m.state / 'unused-nodes' / (node['id'] + '-' + path.name)
                        target.parent.mkdir(exist_ok=True)
                        if target.exists():
                            target = target.with_stem(target.stem + '-' + uuid.uuid4().hex[:6])
                        path.rename(target)
                    continue
                description = 'Projeto identificado pelo caminho canônico.' if node['kind'] == 'project' else 'Assunto identificado no conteúdo ou informado explicitamente; consulte os backlinks para ver as evidências.'
                text = f'---\nid: {node["id"]}\nmanaged_by: ia-hub\ntype: {node["kind"]}\n---\n# {node["title"]}\n\n{description}\n'
                path = self.m.root / node['note_path']
                if not path.exists():
                    self.m.write(path, text)
                    c.execute('UPDATE nodes SET projection_hash=? WHERE id=?', (digest(text), node['id']))
                elif not node['projection_hash']:
                    c.execute('UPDATE nodes SET projection_hash=? WHERE id=?', (digest(path.read_text(encoding='utf-8')), node['id']))
            # Query renderizada pelo Obsidian não cria arestas no grafo.
            self.m.write(self.m.root / 'Memoria' / 'indice.md', '# Memória compartilhada\n\nConsulta das notas atuais. Relações reais estão nas notas, nos assuntos e nos projetos.\n\n```query\npath:"Memoria/conhecimentos"\n```\n')

    def migrate(self):
        stamp = now().replace(':', '').replace('.', '-')
        backup = self.m.state / 'migrations' / stamp
        backup.mkdir(parents=True)
        old_folder = self.m.root / 'Memoria'
        if old_folder.exists():
            shutil.copytree(old_folder, backup / 'Memoria')
        with self.m.lock, self.m.connection() as c:
            target = sqlite3.connect(backup / 'before.sqlite3')
            try:
                c.backup(target)
            finally:
                target.close()
            before = {'records': c.execute('SELECT count(*) FROM records').fetchone()[0], 'revisions': c.execute('SELECT count(*) FROM revisions').fetchone()[0]}
            c.execute('UPDATE records SET dirty=1')
        self.project()
        # Nós antigos sem uso são arquivados integralmente, sem excluir conteúdo.
        retired = backup / 'retired-nodes'
        for folder in ['assuntos', 'projetos']:
            for path in (self.m.root / 'Memoria' / folder).glob('*.md'):
                if re.fullmatch('[0-9a-f]{16,40}', path.stem):
                    target = retired / folder / path.name
                    target.parent.mkdir(parents=True, exist_ok=True)
                    path.rename(target)
        return {'backup': str(backup), 'preserved': before, 'health': self.m.health()}
