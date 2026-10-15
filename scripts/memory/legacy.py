"""Importação incremental de fontes autorais, sem modificar os originais."""
import json
import re
from .core import project_id, digest, normalize


def sync_decisions(memory, document, decisions, project, path):
    with memory.connection() as c:
        c.execute('CREATE TABLE IF NOT EXISTS source_decisions (document_id TEXT,slot INTEGER,record_id TEXT,PRIMARY KEY(document_id,slot))')
        old = {r['slot']: dict(r) for r in c.execute('SELECT d.slot,r.id,r.stable_key,r.content,r.title FROM source_decisions d JOIN records r ON r.id=d.record_id WHERE d.document_id=?', (document['id'],))}
    assigned, used = {}, set()
    # Primeiro preserva identidades das linhas que apenas mudaram de posição.
    for slot, decision in enumerate(decisions):
        for previous in old.values():
            if previous['id'] not in used and normalize(previous['content']) == normalize(decision):
                assigned[slot] = previous
                used.add(previous['id'])
                break
    for slot, decision in enumerate(decisions):
        if slot not in assigned and slot in old and old[slot]['id'] not in used:
            assigned[slot] = old[slot]
            used.add(old[slot]['id'])
    current = []
    for slot, decision in enumerate(decisions):
        label = re.sub(r'^\d{4}-\d{2}-\d{2}[: ]*', '', decision).replace('`', '').strip()
        key = assigned[slot]['stable_key'] if slot in assigned else 'extract:' + document['id'] + ':' + digest(normalize(decision))
        record = memory.store('Decisão — ' + label[:105], decision, project=project, source='file:' + str(path), key=key, kind='decision', status='documented')
        current.append(record['id'])
        with memory.connection() as c:
            inserted = c.execute('INSERT OR IGNORE INTO relations VALUES (?,?,?,?,?)', (record['id'], document['id'], 'documentado em', 'source-extracted', 1.0)).rowcount
            if inserted:
                c.execute('UPDATE records SET dirty=1 WHERE id IN (?,?)', (record['id'], document['id']))
    for previous in old.values():
        if previous['id'] not in current:
            memory.store(previous['title'], previous['content'], project=project, source='file:' + str(path), key=previous['stable_key'], kind='decision', status='superseded')
    with memory.connection() as c:
        c.execute('DELETE FROM source_decisions WHERE document_id=?', (document['id'],))
        c.executemany('INSERT INTO source_decisions VALUES (?,?,?)', [(document['id'], slot, item_id) for slot, item_id in enumerate(current)])


def sync(memory):
    root = memory.root
    paths = list((root / 'contexto').rglob('*.md')) if (root / 'contexto').exists() else []
    paths += list((root / 'regras').glob('*.md')) if (root / 'regras').exists() else []
    if (root / 'README.md').exists():
        paths.append(root / 'README.md')
    plans = root / 'docs' / 'superpowers' / 'plans'
    if plans.exists():
        paths += list(plans.glob('*.md'))
    for path in sorted(paths):
        if '.memory' in path.parts or path.name.startswith('_'):
            continue
        text = path.read_text(encoding='utf-8-sig')[:48000]
        title = next((x[2:] for x in text.splitlines() if x.startswith('# ')), path.stem)
        rel = path.relative_to(root).as_posix()
        key = 'legacy:' + rel
        project = root
        if path.parent.name == 'projetos' and path.stem.casefold() != root.name.casefold():
            candidate = root.parent / path.stem
            project = candidate if candidate.exists() else 'project:' + path.stem
        project = project_id(project)
        with memory.connection() as c:
            existing = c.execute('SELECT id,project FROM records WHERE stable_key=?', (key,)).fetchone()
            if existing and existing['project'] != project:
                c.execute('UPDATE records SET project=?,dirty=1 WHERE id=?', (project, existing['id']))
        kind = 'project-note' if 'contexto/projetos/' in rel else 'reference-document'
        document = memory.store(title, text, project=project, source='file:' + str(path), key=key, kind=kind, status='reference')
        # Extração literal, sem inferir fatos novos a partir de instruções operacionais.
        if kind == 'project-note':
            section = ''
            decisions = []
            for line in text.splitlines():
                if line.startswith('## '):
                    section = normalize(line[3:])
                if section != 'decisões' or not line.startswith('- '):
                    continue
                decision = line[2:].strip()
                if len(decision) < 20:
                    continue
                decisions.append(decision)
            sync_decisions(memory, document, decisions, project, path)
