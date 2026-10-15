"""Installer gate: prove service, database, semantic search and projections."""
import json
import time
from .client import ROOT, STATE, request


def check(timeout=900):
    deadline = time.monotonic() + timeout
    while True:
        health = request('health')
        if health.get('root') != str(ROOT):
            raise RuntimeError('O serviço pertence a outro clone do IA-Hub.')
        if health.get('semantic_state') == 'failed':
            raise RuntimeError('Modelo semântico: ' + health.get('last_error', 'falha'))
        if health.get('semantic_state') == 'ready':
            break
        if time.monotonic() >= deadline:
            raise RuntimeError('Tempo esgotado preparando modelo. Consulte contexto/.memory/service.log e execute doctor novamente.')
        time.sleep(2)
    project = 'IA-Hub-E2E-installer'
    record = request('store', {'title': 'Verificação da instalação da memória',
                              'content': 'IA-Hub-E2E-installer: guardar documentos no computador permite consultar conhecimento mesmo desconectado da internet.',
                              'project': project, 'source': 'installer', 'key': 'installer-health-v1',
                              'status': 'reported', 'tags': ['validação']})
    item_id = record['id']
    if request('get', {'item_id': item_id})['id'] != item_id:
        raise RuntimeError('Falha de leitura após gravação.')
    results = request('search', {'query': 'funcionamento offline', 'project': project, 'limit': 5})
    if not any(r['id'] == item_id and 'semantica' in r.get('methods', []) for r in results):
        raise RuntimeError('Busca semântica não recuperou a prova de instalação.')
    request('reconcile')
    health = request('health')
    if health.get('database_integrity') != 'ok' or health.get('pending_projections') or health.get('projection_conflicts') or health.get('last_error'):
        raise RuntimeError('Banco ou projeções precisam de revisão: ' + json.dumps(health, ensure_ascii=False))
    report = {'health': health, 'write_read_semantic_search': 'passed', 'proof_id': item_id,
              'scope': 'Serviço local; não comprova login nem integração de uma sessão de aplicativo.'}
    STATE.mkdir(parents=True, exist_ok=True)
    (STATE / 'doctor.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
    return report
