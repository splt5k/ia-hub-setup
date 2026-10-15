import { spawn } from 'node:child_process';
import { createHash } from 'node:crypto';

// Os caminhos absolutos são substituídos pelo instalador local.
const executable = __PYTHON__;
const entry = __ENTRY__;

function rpc(action, arguments_) {
  return new Promise((resolve, reject) => {
    const child = spawn(executable, [entry, action], { windowsHide: true, stdio: ['pipe', 'pipe', 'pipe'] });
    let output = '';
    const timer = setTimeout(() => { child.kill(); reject(new Error('IA-Hub RPC timeout')); }, 15000);
    child.stdout.on('data', data => { output += data; if (output.length > 256000) child.kill(); });
    child.stderr.resume();
    child.on('error', reject);
    child.on('close', code => {
      clearTimeout(timer);
      if (code !== 0) return reject(new Error('IA-Hub memory RPC failed'));
      try { resolve(JSON.parse(output)); } catch (error) { reject(error); }
    });
    child.stdin.end(JSON.stringify(arguments_));
  });
}

export const IAHubMemory = async ({ client, directory }) => {
  const turns = new Map();
  const activeRuns = new Map();
  const messages = new Map();
  const log = message => client.app.log({ body: { service: 'ia-hub-memory', level: 'warn', message } }).catch(() => {});
  return {
  'chat.message': async (input, output) => {
    if (process.env.IA_HUB_WORKER === '1') return;
    try {
      const prompt = output.parts.filter(p => p.type === 'text' && !p.synthetic && !p.ignored).map(p => p.text).join('\n');
      if (!prompt.trim()) return;
      const model = output.message.model;
      const current_model = model.providerID + '/' + model.modelID;
      const run = await rpc('orchestration_native', {event:'start', prompt:prompt.slice(0,24000), client:'opencode', project:directory,
        current_model, mode:process.env.IA_HUB_ROUTING_MODE || 'auto', session_id:input.sessionID,
        idempotency_key:'opencode:' + output.message.id});
      const selected = run.decision.model;
      const slash = selected.indexOf('/');
      if (slash > 0 && process.env.IA_HUB_ROUTING_MODE !== 'manual') {
        // Mutate the message retained by OpenCode. Replacing output.message has no effect.
        model.providerID = selected.slice(0,slash);
        model.modelID = selected.slice(slash+1);
      }
      const state = {...run, requested:model.providerID+'/'+model.modelID};
      turns.set(input.sessionID,state);
      if (!activeRuns.has(input.sessionID)) activeRuns.set(input.sessionID,new Map());
      activeRuns.get(input.sessionID).set(run.run_id,state);
      messages.set(output.message.id,state);
      if (messages.size > 256) messages.delete(messages.keys().next().value);
      if (turns.size > 256) turns.delete(turns.keys().next().value);
    } catch { await log('Roteamento indisponível; modelo nativo preservado. Consulte o diagnóstico IA-Hub.'); }
  },
  'experimental.chat.system.transform': async (input, output) => {
    try {
      const context = turns.get(input.sessionID)?.context || await rpc('context', { query: '', project: directory });
      if (context.memories.length) output.system.push(JSON.stringify(context));
    } catch {
      await client.app.log({ body: { service: 'ia-hub-memory', level: 'warn', message: 'Não foi possível recuperar contexto; consulte o diagnóstico de memória.' } }).catch(() => {});
    }
  },
  event: async ({ event }) => {
    if (event.type === 'session.error') {
      const sessionID = event.properties.sessionID;
      for (const run of activeRuns.get(sessionID)?.values() || []) {
        try {
          await rpc('orchestration_native',{event:'attempt',run_id:run.run_id,event_id:'session-error',client:'opencode',status:'failed',error:event.properties.error,model_requested:run.requested});
          await rpc('orchestration_native',{event:'finish',run_id:run.run_id,status:'failed'});
        } catch { await log('Falha nativa com telemetria pendente.'); }
      }
      activeRuns.delete(sessionID);
      return;
    }
    if (event.type === 'message.updated') {
      const info = event.properties.info;
      const run = messages.get(info.parentID);
      if (run && info.role === 'assistant' && info.time?.completed && info.tokens) {
        try { await rpc('orchestration_native', {event:'attempt',client:'opencode',run_id:run.run_id,event_id:info.id,
          model_requested:run.requested,model_reported:info.providerID+'/'+info.modelID,status:info.error?'failed':'succeeded',error:info.error,
          cost_reported_usd:info.cost,usage:{input_tokens:info.tokens.input,output_tokens:info.tokens.output,
          reasoning_output_tokens:info.tokens.reasoning,cached_input_tokens:info.tokens.cache?.read,cache_creation_input_tokens:info.tokens.cache?.write}}); }
        catch { await log('Métricas pendentes; execução sem telemetria confirmada.'); }
      }
      return;
    }
    if (event.type !== 'session.idle') return;
    try {
      const sessionID = event.properties.sessionID;
      for (const run of activeRuns.get(sessionID)?.values() || []) {
        await rpc('orchestration_native', {event:'finish',run_id:run.run_id,status:'succeeded'});
      }
      activeRuns.delete(sessionID);
      const response = await client.session.messages({ path: { id: sessionID } });
      const messages = response.data || response;
      const finalMessages = messages.filter(m => m.info?.role === 'assistant' && m.info?.time?.completed && m.info?.finish !== 'tool-calls');
      for (const message of finalMessages.slice(-1)) {
        const text = (message.parts || []).filter(p => p.type === 'text' && !p.synthetic && !p.ignored).map(p => p.text).join('\n');
        if (text.length < 40) continue;
        const hash = createHash('sha256').update(sessionID + '\n' + text).digest('hex');
        await rpc('observe', { title: text.split('\n').find(x => x.trim()).slice(0, 120), content: text, project: directory, source: 'opencode:session:' + sessionID, key: 'opencode:' + hash });
      }
    } catch {
      await client.app.log({ body: { service: 'ia-hub-memory', level: 'warn', message: 'Captura pendente; exporte o diagnóstico IA-Hub para investigar.' } }).catch(() => {});
    }
  }
};
};
