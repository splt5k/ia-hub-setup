"""Bounded live pilot. Explicit --live required; invokes authenticated native CLIs.

This is a reproducible pilot, not a general quality/cost benchmark. No auth copied.
"""
import argparse
import hashlib
import json
import tempfile
import time
from pathlib import Path
from memory.core import Memory
from memory.executor import Executor


def wait(executor, job):
    end = time.monotonic() + 300
    while time.monotonic() < end:
        result = executor.status(job['run_id'])
        if result['status'] != 'running':
            return result
        time.sleep(.25)
    raise TimeoutError('Pilot job timeout')


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--live', action='store_true')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('--memory-only', action='store_true')
    parser.add_argument('--paired-only', action='store_true')
    args = parser.parse_args()
    if not args.live:
        parser.error('--live consome cota/custo dos clientes; leia o script antes de executar.')
    root = Path(__file__).resolve().parents[1]
    report = {'schema': 1, 'scope': 'small_live_pilot_not_general_efficiency_proof', 'cross_memory': [], 'paired': []}
    report['implementation_sha256'] = {name:hashlib.sha256((root/name).read_bytes()).hexdigest() for name in ['scripts/memory/executor.py','scripts/memory/policy.py','scripts/memory/telemetry.py','regras/orchestration.json']}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    def checkpoint():
        args.output.write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    with tempfile.TemporaryDirectory(prefix='hub-cross-') as temp:
        memory = Memory(Path(temp))
        executor = Executor(memory, root)
        cases = [] if args.paired_only else [('claude-code', 'codex', 'Projeto Aurora: código de recuperação', 'AURORA-7319'),
                                             ('codex', 'claude-code', 'Projeto Cedro: código de recuperação', 'CEDRO-8264')]
        for source, target, topic, value in cases:
            # The value is supplied only to writer; reader gets it only via shared retrieval.
            writer = wait(executor, executor.submit(f'Registre esta descoberta em uma frase: {topic} é {value}. Repita o código exatamente.', source, temp,
                validation={'type': 'contains', 'value': value}, idempotency_key='write-' + source))
            reader = wait(executor, executor.submit(f'Qual é o {topic}? Use o conhecimento recuperado. Responda somente o código.', target, temp,
                validation={'type': 'exact', 'value': value}, idempotency_key='read-' + target))
            row = {'source': source, 'target': target, 'writer': writer, 'reader': reader,
                'retrieved_and_used': writer['status'] == reader['status'] == 'succeeded'}
            report['cross_memory'].append(row)
            print(json.dumps({'cross': source + '->' + target, 'passed': row['retrieved_and_used']}), flush=True)
            checkpoint()
        executor.pool.shutdown(wait=True)
    if not args.memory_only:
        for client, baseline in [('claude-code', 'sonnet'), ('codex', 'gpt-6.1-sol')]:
            for index, (prompt, answer) in enumerate([('Responda somente o número: 17 + 28.', '45'), ('Retorne somente a lista JSON dos números pares entre 1 e 6, sem espaços.', '[2,4,6]')]):
                for arm in (('baseline', 'hub') if index % 2 == 0 else ('hub', 'baseline')):
                    # Separate DB/project for each call: memory starts identically empty.
                    with tempfile.TemporaryDirectory(prefix='hub-paired-') as temp:
                        executor = Executor(Memory(Path(temp)), root)
                        start = time.monotonic()
                        job = executor.submit(prompt, client, temp, validation={'type': 'exact', 'value': answer},
                            mode='manual' if arm == 'baseline' else 'auto', current_model=baseline if arm == 'baseline' else '',
                            task_kind='implement' if arm == 'baseline' else '')
                        result = wait(executor, job)
                        report['paired'].append({'client': client, 'task': index, 'arm': arm, 'wall_ms': (time.monotonic()-start)*1000,
                            'result': result, 'attempts': executor.report(job['run_id'])['attempts']})
                        print(json.dumps({'client': client, 'task': index, 'arm': arm, 'status': result['status']}), flush=True)
                        checkpoint()
                        executor.pool.shutdown(wait=True)
    checkpoint()


if __name__ == '__main__':
    main()
