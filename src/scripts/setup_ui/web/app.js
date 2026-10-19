const $ = id => document.getElementById(id);
const fragment = location.hash.slice(1);
if (fragment) { sessionStorage.setItem('ia-hub-session', fragment); history.replaceState(null, '', '/'); }
const token = fragment || sessionStorage.getItem('ia-hub-session') || '';
let state, selectedAction, alertFilter = false, lastLogSignature = '';
const esc = value => String(value ?? '').replace(/[&<>"']/g, c => ({'&':'&amp;','<':'&lt;','>':'&gt;','"':'&quot;',"'":'&#39;'}[c]));
const phaseNames = [['diagnostic','Diagnóstico'],['runtime','Dependências'],['clients','Aplicativos e CLIs'],['config','Configurações'],['memory','Memória compartilhada'],['validate','Validação']];
const components = [['runtime','Runtime da memória'],['integrations','Integrações e regras'],['claude','Claude Code'],['codex','Codex CLI'],['agy','Antigravity CLI'],['opencode','OpenCode CLI'],['desktop','Aplicativos gráficos']];
async function api(path, body) {
  const response = await fetch('/api/' + path, {method: body ? 'POST':'GET', headers:{Authorization:'Bearer '+token,...(body?{'Content-Type':'application/json'}:{})}, ...(body?{body:JSON.stringify(body)}:{})});
  if (!response.ok) { const error = await response.json(); throw new Error(error.error || 'A operação não pôde ser concluída.'); }
  return response;
}
function toast(message) { $('toast').textContent = message; $('toast').hidden=false; setTimeout(()=>$('toast').hidden=true,5500); }
function render() {
  const d = state.diagnostic, h = d.health || {}, job = state.job, running=job.status==='running';
  $('preview-label').hidden=!state.preview;
  $('notice').hidden=!(state.preview || d.foreign);
  $('notice').textContent=state.preview ? 'Modo de avaliação · diagnóstico real deste computador. Alterações na instalação estão bloqueadas.' : 'Existe uma instalação em outra pasta. Para alterá-la, abra o instalador na pasta ativa mostrada abaixo.';
  $('system-name').textContent=(d.system?.os || 'Ambiente local')+' · '+ (['AMD64','x86_64'].includes(d.system?.arch)?'x86_64':d.system?.arch||'');
  $('installation-badge').innerHTML='<i></i> '+(d.installed?(d.configured===false?'Memória preservada · integração inativa':'Instalação existente encontrada'):'Pronto para a primeira instalação');
  $('metric-apps').textContent=(d.apps||[]).filter(a=>a.present).length+' encontrados';
  $('metric-integrated').textContent=(d.apps||[]).filter(a=>a.kind==='cli' && a.integrated).length+' / 4 configuradas';
  $('metric-records').textContent=h.records !== undefined ? Number(h.records).toLocaleString('pt-BR')+' registros':'Sem resposta do serviço';
  $('metric-semantic').textContent=h.semantic_state==='ready'?'Ativa e local':h.semantic_state==='loading'?'Preparando modelo':'Não verificada';
  $('root-path').textContent=d.root;
  $('root-status').textContent=d.foreign?'Ativa neste PC':'Pasta atual';
  const avatars={claude:['✳','#3e3029','#e0a786'],codex:['⌘','#303534','#e6eeeb'],agy:['A','#283441','#9abbe7'],opencode:['▰','#332d40','#c1addc']};
  $('cli-cards').innerHTML=(d.apps||[]).filter(a=>a.kind==='cli').map(a=>{const [symbol,bg,color]=avatars[a.id]||['◈','#28312d','#bbe0ca'];return `<div class="agent-card"><span class="agent-avatar ${esc(a.id)}">${symbol}</span><div class="agent-copy"><h3>${esc(a.name)}</h3><p class="${a.integrated?'':'pending'}"><i></i>${a.integrated?'MCP configurado':a.present?'Instalado · integrar':'Ainda não encontrado'}</p></div><span class="agent-check">${a.integrated?'✓':'·'}</span></div>`;}).join('');
  $('desktop-apps').innerHTML=(d.apps||[]).filter(a=>a.kind==='app').map(a=>`<span class="desktop-app ${a.present?'found':''}"><span>${a.present?'✓':'·'}</span>${esc(a.name)}</span>`).join('');
  $('verify').disabled=running;
  $('verify').innerHTML=d.installed?'<span>✓</span> Verificar instalação <span class="button-arrow">↗</span>':'<span>＋</span> Configurar meu ambiente <span class="button-arrow">↗</span>';
  for(const id of ['repair','reinstall','remove']) $(id).disabled=running;
  $('close-panel').disabled=running;
  $('maintenance-description').textContent=d.installed?'O ambiente já existe. Verifique ou faça manutenção sem começar do zero.':'Escolha os componentes e prepare sua memória compartilhada.';
  const phases=job.steps.length ? job.steps : phaseNames.map(([id,label])=>({id,label,status:'pending'}));
  const complete=phases.filter(p=>p.status==='done'||p.status==='skipped').length;
  $('steps').innerHTML=phases.map((p,i)=>`<li class="step ${esc(p.status)}"><span class="step-circle">${p.status==='done'?'✓':p.status==='running'?'·':p.status==='failed'?'!':i+1}</span><span>${esc(p.label)}</span><span class="step-state">${({done:'Concluído',running:'Em andamento',failed:'Falhou',skipped:'Ignorado'})[p.status]||''}</span></li>`).join('');
  const pending=d.pending||[];
  $('pending-list').hidden=!pending.length;
  $('pending-list').innerHTML=pending.length?`<h4>Pendências</h4>${pending.map(p=>`<div class="pending-item ${esc(p.state)}"><strong>${esc(p.name)}</strong><span>${p.state==='failed'?'Falhou':'Não disponível nesta máquina'}${p.detail?' · '+esc(p.detail):''}</span></div>`).join('')}<button id="retry-pending" class="button secondary small" ${running||state.preview||d.foreign?'disabled':''}>Tentar pendências de novo</button>`:'';
  const retry=$('retry-pending');
  if(retry) retry.onclick=()=>openAction('repair');
  const titles={idle:'O próximo passo é seu',running:'Seu ambiente está em preparo',completed:job.action==='verify'?'Verificação concluída':job.action==='remove'?'Integração removida':'Tudo pronto por aqui',partial:'Concluído com pendências',failed:'Vamos resolver esta etapa'};
  const descriptions={idle:'Escolha uma ação. Você acompanha cada etapa por aqui.',running:'Acompanhe as etapas e os detalhes no log ao lado.',completed:job.action==='verify'?'Diagnóstico finalizado sem alterar sua configuração.':job.action==='remove'?'Aplicativos, banco e notas preservados. Você pode reconectar o ambiente quando quiser.':'Confira o resultado e os logins pendentes no relatório.',partial:'Alguns componentes precisam de atenção. O log mostra os detalhes.',failed:'Seus dados permanecem preservados. Consulte o log e tente novamente.'};
  $('job-title').textContent=titles[job.status]||titles.idle;
  $('job-description').textContent=descriptions[job.status]||descriptions.idle;
  $('job-pill').textContent=({idle:'EM ESPERA',running:'EM ANDAMENTO',completed:'CONCLUÍDO',partial:'PENDÊNCIAS',failed:'ATENÇÃO'})[job.status];
  $('progress-orb').className='progress-orb '+(running?'running':job.status==='failed'?'failed':'');
  $('progress-bar').style.width=(job.steps.length?100*complete/phases.length:0)+'%';
  $('step-counter').textContent=job.steps.length?`${complete} / ${phases.length}`:'—';
  $('progress-caption').textContent=running?'Etapas confirmadas':job.status==='idle'?'Nenhuma alteração em andamento':'Etapas concluídas';
  $('activity-live').className='live-dot '+(running?'running':'');
  $('log-status').innerHTML='<i></i> '+(running?'Recebendo eventos do instalador':job.status==='idle'?'Ambiente pronto para verificação':'Operação encerrada · log disponível');
  $('log-count').textContent=job.logs.length;
  $('footer-status').textContent=state.preview?'Prévia local · nenhum commit realizado':'Somente neste computador';
  renderLogs();
}
function renderLogs() {
  if(!state)return;
  const logs=state.job.logs, q=$('log-search').value.toLowerCase();
  $('alert-count').textContent=logs.filter(l=>l.level==='warning'||l.level==='error').length;
  const rows=logs.filter(l=>(!alertFilter||['warning','error'].includes(l.level))&&(!q||l.message.toLowerCase().includes(q)));
  const signature=JSON.stringify(rows);
  if(signature===lastLogSignature)return;
  lastLogSignature=signature;
  const el=$('logs'), nearBottom=el.scrollHeight-el.scrollTop-el.clientHeight<35;
  el.innerHTML=rows.length?rows.map(l=>`<div class="log-row ${esc(l.level)}"><span class="log-time">${esc(l.time)}</span><span class="log-level">${({success:'OK',warning:'AVISO',error:'ERRO',info:'INFO'})[l.level]||'INFO'}</span><span class="log-message">${esc(l.message)}</span></div>`).join(''):'<div class="empty-log">Nenhum evento para este filtro.</div>';
  if(nearBottom)el.scrollTop=el.scrollHeight;
}
function updateConfirmation(){const checked=[...document.querySelectorAll('#component-options input:checked')].map(e=>e.value);$('confirm-action').disabled=state.preview||state.diagnostic.foreign||(selectedAction==='reinstall'&&!checked.length)||(selectedAction==='remove'&&!$('remove-confirm').checked);}
function openAction(action) {
  selectedAction=action;
  const details={install:['Configurar meu ambiente','Instala componentes ausentes, integra as ferramentas e valida a memória compartilhada. Você fará os logins depois.','Iniciar configuração'],repair:['Reparar / atualizar','Reaplica as configurações do IA-Hub e tenta instalar o que estiver faltando. Aplicativos existentes e a memória são preservados.','Reparar ambiente'],reinstall:['Reinstalar componentes','Escolha o que será reinstalado. O runtime anterior terá backup; as integrações compartilhadas são verificadas ao final.','Reinstalar seleção'],remove:['Remover integração','Desconecta os MCPs, os mecanismos de captura e a inicialização automática deste usuário. As alterações de configuração terão backup.','Remover integração']};
  const [title,description,button]=details[action];
  $('dialog-title').textContent=title;$('dialog-description').textContent=description;$('confirm-action').textContent=button;
  $('dialog-icon').textContent=action==='remove'?'−':'↻';
  $('confirm-action').className='button '+(action==='remove'?'destructive':'primary');
  $('component-options').hidden=action!=='reinstall';
  $('component-options').innerHTML=action==='reinstall'?components.map(([id,label])=>`<label class="component-option"><input type="checkbox" value="${id}" ${id==='integrations'?'checked':''}>${label}</label>`).join(''):'';
  $('remove-details').hidden=action!=='remove';$('remove-confirm').checked=false;
  $('dialog-blocked').hidden=!(state.preview||state.diagnostic.foreign);
  $('dialog-blocked').textContent=state.preview?'Esta é uma prévia para aprovação visual. Nenhuma alteração na sua máquina pode ser executada nesta sessão.':'Abra o instalador na pasta ativa para realizar esta operação.';
  updateConfirmation();$('action-dialog').showModal();
}
async function refresh(){try{state=await(await api('state')).json();render();}catch(error){$('footer-status').textContent='Conexão com o painel encerrada';if(!state)toast(error.message);}}
$('verify').onclick=async()=>{if(!state)return;if(!state.diagnostic.installed){openAction('install');return;}try{await api('action',{action:'verify'});await refresh();}catch(e){toast(e.message);}};
for(const id of ['repair','reinstall','remove'])$(id).onclick=()=>openAction(id);
$('component-options').onchange=updateConfirmation;$('remove-confirm').onchange=updateConfirmation;
$('confirm-action').onclick=async()=>{try{const components=[...document.querySelectorAll('#component-options input:checked')].map(e=>e.value);await api('action',{action:selectedAction,components,confirmed:true});$('action-dialog').close();await refresh();}catch(e){toast(e.message);}};
$('filter-all').onclick=()=>{alertFilter=false;$('filter-all').classList.add('selected');$('filter-alerts').classList.remove('selected');renderLogs();};
$('filter-alerts').onclick=()=>{alertFilter=true;$('filter-alerts').classList.add('selected');$('filter-all').classList.remove('selected');renderLogs();};
$('log-search').oninput=renderLogs;
$('export-toggle').onclick=()=>{$('export-options').hidden=!$('export-options').hidden;};
for(const button of document.querySelectorAll('[data-export]'))button.onclick=async()=>{try{const kind=button.dataset.export,response=await api('export.'+kind),blob=await response.blob(),url=URL.createObjectURL(blob),link=document.createElement('a');link.href=url;link.download='ia-hub-'+new Date().toISOString().slice(0,10)+'.'+kind;link.click();setTimeout(()=>URL.revokeObjectURL(url),1000);$('export-options').hidden=true;toast('Relatório exportado sem credenciais.');}catch(e){toast(e.message);}};
for(const button of document.querySelectorAll('[data-scroll]'))button.onclick=()=>{document.querySelectorAll('.nav-item').forEach(e=>e.classList.remove('active'));button.classList.add('active');$(button.dataset.scroll).scrollIntoView({behavior:'smooth',block:'start'});};
$('close-panel').onclick=async()=>{try{await api('close',{});clearInterval(poll);$('footer-status').textContent='Painel encerrado · você pode fechar esta aba';toast('Painel encerrado. Sua memória continua preservada.');}catch(e){toast(e.message);}};
document.addEventListener('click',e=>{if(!e.target.closest('.export-menu'))$('export-options').hidden=true;});
refresh();const poll=setInterval(refresh,1100);
