import json
import shutil
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path


@unittest.skipUnless(shutil.which('node'), 'Node necessário para executar plugin real')
class PluginTests(unittest.TestCase):
    def test_model_is_mutated_in_place_context_uses_prompt_and_metrics_deduplicate_ids(self):
        repo = Path(__file__).resolve().parents[1]
        with tempfile.TemporaryDirectory() as tmp:
            directory = Path(tmp)
            stub = directory / 'rpc.py'
            stub.write_text('import sys,json\na=json.load(sys.stdin)\n'
                'with open(sys.argv[1],"a") as f:f.write(json.dumps(a)+"\\n")\n'
                'print(json.dumps({"run_id":a.get("idempotency_key","r1"),"decision":{"model":"google/flash","control":"native"},"context":{"memories":[{"content":"project fact"}]}}))\n', encoding='utf-8')
            log = directory / 'calls.jsonl'
            plugin = (repo / 'scripts/memory/opencode-plugin.js').read_text(encoding='utf-8')
            # The installed module uses exactly the same source; only executable paths are rendered.
            plugin = plugin.replace('__PYTHON__', json.dumps(sys.executable)).replace('__ENTRY__', json.dumps(str(stub)))
            # Stub receives action as argv2; use argv1 to choose the log, preserving stdin contract.
            stub.write_text(stub.read_text(encoding='utf-8').replace('sys.argv[1]', repr(str(log))), encoding='utf-8')
            (directory / 'plugin.mjs').write_text(plugin, encoding='utf-8')
            script = '''import {IAHubMemory} from './plugin.mjs';
const p=await IAHubMemory({directory:'/project',client:{app:{log:async()=>{}},session:{messages:async()=>({data:[]})}}});
const message={id:'u1',model:{providerID:'openai',modelID:'old'}};
const ref=message;
await p['chat.message']({sessionID:'s1'},{message,parts:[{type:'text',text:'Find special project evidence'}]});
if(message!==ref||message.model.providerID!=='google'||message.model.modelID!=='flash')throw Error('model not mutated');
const output={system:[]}; await p['experimental.chat.system.transform']({sessionID:'s1'},output);
if(!output.system.join('').includes('project fact'))throw Error('missing context');
const event={type:'message.updated',properties:{info:{id:'a1',parentID:'u1',sessionID:'s1',role:'assistant',providerID:'google',modelID:'flash',time:{completed:1},tokens:{input:10,output:2,reasoning:1,cache:{read:3,write:0}},cost:0}}};
await p.event({event}); await p.event({event});
await p['chat.message']({sessionID:'s1'},{message:{id:'u2',model:{providerID:'google',modelID:'flash'}},parts:[{type:'text',text:'second prompt'}]});
await p.event({event:{type:'session.idle',properties:{sessionID:'s1'}}});
console.log('ok');'''
            (directory / 'test.mjs').write_text(script, encoding='utf-8')
            result = subprocess.run(['node', 'test.mjs'], cwd=directory, capture_output=True, text=True, timeout=20)
            self.assertEqual(result.returncode, 0, result.stderr)
            calls = [json.loads(line) for line in log.read_text().splitlines()]
            self.assertEqual(calls[0]['prompt'], 'Find special project evidence')
            attempts = [a for a in calls if a.get('event') == 'attempt']
            self.assertEqual(len(attempts), 2)  # Ledger deduplicates stable event IDs across restarts too.
            self.assertEqual(attempts[0]['event_id'], attempts[1]['event_id'])
            self.assertEqual(attempts[0]['model_reported'], 'google/flash')
            self.assertEqual(attempts[0]['usage']['cached_input_tokens'], 3)
            finished = [a['run_id'] for a in calls if a.get('event') == 'finish']
            self.assertEqual(set(finished), {'opencode:u1', 'opencode:u2'})
