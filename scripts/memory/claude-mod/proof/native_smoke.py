"""Prova opt-in: duas inferências nativas; RPC local simulado, sem alterar instalação."""
import json
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile


def main():
    plugin = Path(__file__).resolve().parents[1]
    binary = Path(os.environ.get('APPDATA', '')) / 'npm/node_modules/@anthropic-ai/claude-code/bin/claude.exe'
    if not binary.exists():
        binary = Path(shutil.which('claude') or 'claude')
    results = []
    with tempfile.TemporaryDirectory(prefix='native-proof-', dir=Path(__file__).parent) as tmp:
        root = Path(tmp)
        fixture = root / 'plugin'
        (fixture / '.claude-plugin').mkdir(parents=True)
        (fixture / 'hooks').mkdir()
        for rel in ('.claude-plugin/plugin.json', 'hooks/hooks.json'):
            shutil.copyfile(plugin / rel, fixture / rel)
        rpc = root / 'rpc.py'
        log = root / 'events.jsonl'
        rpc.write_text('''import json,sys
from pathlib import Path
a=json.load(sys.stdin)
log=Path(__file__).with_name('events.jsonl')
with log.open('a',encoding='utf8') as f: f.write(json.dumps(a)+'\\n')
r={}
if a.get('event')=='start':
 model='claude-haiku-5-5' if '1+1' in a['prompt'] else 'claude-sonnet-5-5'
 r={'run_id':model,'decision':{'model':model,'effort':'low','control':'native_hooks'},'context':{'memories':[]}}
print(json.dumps(r))
''', encoding='utf8')
        source = (plugin / 'hooks/register.js').read_text(encoding='utf8')
        source = source.replace("'__PYTHON__'", json.dumps(sys.executable)).replace("'__ENTRY__'", json.dumps(str(rpc)))
        (fixture / 'hooks/register.js').write_text(source, encoding='utf8')
        env = dict(os.environ)
        env.pop('IA_HUB_WORKER', None)
        env.pop('IA_HUB_ROUTING_MODE', None)
        for prompt, answer in [('Calcule 1+1. Responda apenas o número.', '2'), ('Calcule 2+3. Responda apenas o número.', '5')]:
            r = subprocess.run([str(binary), '-p', prompt, '--plugin-dir', str(fixture),
                                '--output-format', 'json', '--model', 'opus', '--tools', '',
                                '--setting-sources', '', '--strict-mcp-config', '--mcp-config', '{"mcpServers":{}}',
                                '--max-turns', '1'], cwd=root, env=env, capture_output=True,
                               text=True, encoding='utf8', timeout=120)
            output = json.loads(r.stdout) if r.stdout.strip() else {}
            events = [json.loads(line) for line in log.read_text(encoding='utf8').splitlines()] if log.exists() else []
            attempts = [e for e in events if e.get('event') == 'attempt']
            results.append({'prompt':prompt,'expected':answer,'actual':output.get('result'),
                            'exact_match':output.get('result','').strip() == answer,
                            'exit_code':r.returncode,'modelUsage':output.get('modelUsage'),
                            'usage':output.get('usage'),'cost_estimate_usd':output.get('total_cost_usd'),
                            'duration_ms':output.get('duration_ms'),'attempts':attempts,'events':events,
                            'stderr':r.stderr[-1000:]})
            if log.exists(): log.unlink()
    destination = Path(__file__).with_name('latest-results.json')
    destination.write_text(json.dumps(results, ensure_ascii=False, indent=2), encoding='utf8')
    print(json.dumps(results, ensure_ascii=False, indent=2))
    return 0 if all(r['exact_match'] and r['attempts'] and
                    r['attempts'][-1]['model_reported'] == expected
                    for r,expected in zip(results, ['claude-haiku-5-5','claude-sonnet-5-5'])) else 1


if __name__ == '__main__':
    raise SystemExit(main())
