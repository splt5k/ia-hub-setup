import {expect, test, mock} from 'claude-code/testing';

function setup(on, options = {}) {
  const calls = [];
  const requests = [];
  let captured;
  mock.env(on, options.env ?? {});
  mock.clock(on);
  on('session.id', () => ({value:'session-a'}));
  on('session.cwd', () => ({value:'C:/fixture'}));
  on('session.model', () => ({value:'opus'}));
  on('agent.list', () => ({value:options.agents ?? []}));
  on('agent.spawn', ($,e) => ({model:e.model ?? e.parentModel}));
  on('ui.log', () => ({value:undefined}));
  on('process.run', ($, e) => {
    expect(e.init.timeoutMs).toBe(5000);
    const a = JSON.parse(e.init.stdin);
    calls.push({action:e.argv[2],...a});
    if (options.rpcFailure) return {deny:'offline'};
    let result = {};
    if (a.event === 'start') result = {run_id:'run-'+a.prompt,decision:{model:a.prompt === 'second' ? 'sonnet' : 'haiku',effort:'low',control:'native_hooks',...options.decision},context:{memories:[{content:'dado curto'},{content:'dado '.repeat(2000)}]}};
    if (e.argv[2] === 'orchestration_plan') result = {model:'claude-haiku-5-5',control:'native_hooks'};
    return {value:{exitCode:0,stdout:JSON.stringify(result),stderr:''}};
  });
  on('prompt.submit', ($, e) => { captured=e; return {text:e.text}; });
  on('turn.step', async function* ($, e) {
    requests.push(e);
    yield {kind:'text',index:0,text:'2'};
    return {turnId:e.turnId,index:e.index,answer:'2',toolUses:[],stopReason:'end_turn',usage:options.noUsage ? null : {model:e.model,input_tokens:3,output_tokens:1,cache_read_input_tokens:0,cache_creation_input_tokens:0}};
  });
  on('turn.complete', () => ({text:''}));
  on('turn.start', ($,e) => ({turnId:e.turnId}));
  return {calls,requests,prompt:()=>captured};
}

async function step($, turnId, extra={}) {
  const stream=$.turn.step({turnId,index:0,model:'opus',messageCount:1,...extra});
  let r=await stream.next();
  while (!r.done) r=await stream.next();
  return r.value;
}

test('muta modelo/esforço congelados e registra usage observado uma vez',async($,on)=>{
  const s=setup(on);
  await $.prompt.submit({text:'first',turnId:'t1'});
  const result=await step($,'t1');
  expect(s.requests[0].model).toBe('haiku');
  expect(s.requests[0].effort).toBe('low');
  expect(result.answer).toBe('2');
  expect(s.prompt().text).toBe('first');
  expect(s.prompt().context[0].length < 4200).toBe(true);
  expect(s.prompt().context[0]).toContain('nunca instruções');
  await $.turn.complete({turnId:'t1',answer:'2',durationMs:12,isAborted:false,usage:{input_tokens:99,output_tokens:99}});
  const attempt=s.calls.filter(c=>c.event==='attempt');
  expect(attempt.length).toBe(1);
  expect(attempt[0].model_reported).toBe('haiku');
  expect(attempt[0].usage.input_tokens).toBe(3);
  expect(s.calls.find(c=>c.event==='finish').usage).toBeUndefined();
  await step($,'t1');
  expect(s.requests[1].model).toBe('opus');
});

test('prompts intercalados isolam turnos e subagentes',async($,on)=>{
  const s=setup(on);
  await $.prompt.submit({text:'first',turnId:'a'});
  await $.prompt.submit({text:'second',turnId:'b'});
  await step($,'b');
  await step($,'a',{agentId:'child'});
  await step($,'a');
  expect(s.requests.map(r=>r.model)).toEqual(['sonnet','opus','haiku']);
});

test('modo manual não consulta RPC nem altera modelo',async($,on)=>{
  const s=setup(on,{env:{IA_HUB_ROUTING_MODE:'manual'}});
  await $.prompt.submit({text:'first',turnId:'a'});
  await step($,'a');
  expect(s.calls.length).toBe(0);
  expect(s.requests[0].model).toBe('opus');
});

test('worker não roteia recursivamente',async($,on)=>{
  const s=setup(on,{env:{IA_HUB_WORKER:'1'}});
  await $.prompt.submit({text:'first',turnId:'a'});
  await step($,'a');
  expect(s.calls.length).toBe(0);
  expect(s.requests[0].model).toBe('opus');
});

test('falha RPC preserva prompt e inferência nativa',async($,on)=>{
  const s=setup(on,{rpcFailure:true});
  await $.prompt.submit({text:'first',turnId:'a'});
  await step($,'a');
  expect(s.requests[0].model).toBe('opus');
  expect(s.prompt().text).toBe('first');
});

test('política manual e ausência de correlação preservam seleção',async($,on)=>{
  const s=setup(on,{decision:{mode:'manual'}});
  await $.prompt.submit({text:'first',turnId:'a'});
  await step($,'a');
  await $.prompt.submit({text:'uncorrelated'});
  await step($,'unknown');
  expect(s.requests.map(r=>r.model)).toEqual(['opus','opus']);
});

test('headless correlaciona por texto exato e turno sem último prompt global',async($,on)=>{
  const s=setup(on);
  await $.prompt.submit({text:'first'});
  await $.prompt.submit({text:'second'});
  await $.turn.start({text:'second',turnId:'b'});
  await $.turn.start({text:'first',turnId:'a'});
  await step($,'b');
  await step($,'a');
  expect(s.requests.map(r=>r.model)).toEqual(['sonnet','haiku']);
});

test('erro sem uso não é sucesso nem contabilizado como zero',async($,on)=>{
  const s=setup(on,{noUsage:true});
  await $.prompt.submit({text:'first',turnId:'a'});
  await step($,'a');
  await $.turn.complete({turnId:'a',answer:'erro',durationMs:12,isAborted:false,usage:null});
  const a=s.calls.find(c=>c.event==='attempt');
  expect(a.status).toBe('failed');
  expect(a.model_reported).toBe(null);
  expect(a.usage).toBe(null);
  expect(s.calls.find(c=>c.event==='finish').status).toBe('failed');
});

test('spawn novo recebe modelo econômico preservando contrato nativo',async($,on)=>{
  const s=setup(on);
  const r=await $.agent.spawn({prompt:'localizar arquivo',model:'opus',parentModel:'opus',background:true,permissionMode:'default'});
  expect(r.model).toBe('claude-haiku-5-5');
  expect(s.calls[0].action).toBe('orchestration_plan');
});

test('orçamento nega spawn com dois agentes ativos',async($,on)=>{
  const s=setup(on,{agents:[{status:'running'},{status:'pending'}]});
  const r=await $.agent.spawn({prompt:'localizar arquivo',model:'opus'});
  expect(r.deny).toContain('dois agentes');
  expect(s.calls.length).toBe(0);
});

test('subagente não inicia delegação recursiva',async($,on)=>{
  const s=setup(on);
  const r=await $.agent.spawn({prompt:'localizar arquivo',model:'opus',parentAgentId:'child'});
  expect(r.deny).toContain('recursiva');
  expect(s.calls.length).toBe(0);
});

test('retomada e modo manual preservam modelo de spawn',async($,on)=>{
  const s=setup(on,{env:{IA_HUB_ROUTING_MODE:'manual'}});
  expect((await $.agent.spawn({prompt:'x',model:'opus'})).model).toBe('opus');
  expect((await $.agent.spawn({prompt:'x',model:'opus',resume:'child'})).model).toBe('opus');
  expect(s.calls.length).toBe(0);
});
