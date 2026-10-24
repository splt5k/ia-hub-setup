# Claude mod: implementação e provas

2026-10-15, Windows, Claude Code 2.1.299. Trabalho restrito à cópia de desenvolvimento; sem instalar plugin de produção, mudar confiança/permissões, reiniciar daemon ou copiar credenciais.

## Contrato implementado

`scripts/memory/claude-mod` contém manifesto, marketplace local, hooks, doze testes oficiais offline e prova nativa opt-in. O mod usa `$.process.run([python,entry,action],{stdin:JSON.stringify(args),timeoutMs:5000})`, sem Node.js ou shell. O instalador substitui os **literais com aspas** `'__PYTHON__'` e `'__ENTRY__'` por `json.dumps(caminho_absoluto)`; substituir só o texto interno gera JavaScript inválido para caminhos Windows.

`prompt.submit` chama `orchestration_native` com `event:'start'`, `prompt`, `client:'claude-code'`, `project`, `current_model`, `mode:'auto'`, `session_id` e `idempotency_key`. A resposta é `{run_id,decision,context}`. Usa a decisão e o contexto da mesma chamada, sem segunda consulta. Memórias são dados não confiáveis; entram em `e.context` como JSON de registros completos, com orçamento de 4000 caracteres, sem cortar JSON no meio.

Estado é separado por sessão, agente e turno. **No headless real `prompt.submit.turnId` veio ausente.** Nesse caso, uma fila por sessão/agente guarda o texto exato e `turn.start` vincula seu `text` ao `turnId`. Prompts intercalados são testados. Sem correspondência exata, o modelo fica preservado. Subagentes, `IA_HUB_WORKER` e `IA_HUB_ROUTING_MODE=manual|direct|direto` passam sem roteamento; o mod não altera env/permissões nem inicia executores.

Novos spawns recebem modelo econômico via orchestration_plan, sem alterar permissions/cwd/background. Workers e delegações aninhadas são recusados; modo manual e retomadas/workflows são preservados. Subagentes ficam no máximo em Sonnet (Opus só no orquestrador); forks são recusados porque herdam o modelo do pai; sem decisão da política o spawn cai em Sonnet. O limite de agentes ativos é opcional (`max_active_agents` em orchestration.json, 0 = sem limite); erro na verificação recusa o spawn. `tool.call` em `mcp__ccd_session__start_session` força Sonnet nas sessões paralelas e recusa `context: fork`. A reserva cobre o middleware até next() retornar; ainda não há prova runtime de atomicidade entre o retorno e a publicação do agente na lista. Investigação confirmou `agent.spawn`: permite trocar `model` ou devolver `{deny:reason}` antes de iniciar; `parentAgentId`, `permissionMode`, `provider` e identidade são fixos. Novos subagentes também aceitam prompt/description/subagentType/background/cwd (absoluto); retomadas e workflows ignoram essas reescritas e só permitem recusa. Retomar via SendMessage não dispara esse evento. `$.agent.list()` permite observar status, mas contar ativos antes de spawn não comprova reserva atômica de orçamento paralelo. Há quatro testes offline adicionais de spawn; não houve inferência extra de subagentes. Uso e qualidade dos filhos permanecem pendentes: as métricas do pai não representam todos os recursos.

`turn.step` encaminha cópia do evento com modelo/esforço escolhidos quando `decision.control` é `native_hooks`, `native_mod` ou `native`. **Aliases `haiku` e `sonnet` foram rejeitados pela API nesse ponto, embora funcionem no seletor do CLI. A política precisa retornar IDs canônicos.** A resposta e o stream são preservados. `result.usage.model` é o modelo observado; não se usa modelo solicitado como prova. Cada passo envia `event:'attempt'` com ID estável, uso normalizado e duração; `turn.complete` envia apenas `finish`, sem duplicar totais. Uso ausente não vira zero nem sucesso; qualidade permanece `not_run`/`not_measured`.

## Provas

- `claude plugin validate scripts/memory/claude-mod --strict`: passou, incluindo marketplace e hooks.
- `claude plugin validate scripts/memory/claude-mod/.claude-plugin/plugin.json --strict`: passou.
- `claude plugin test scripts/memory/claude-mod`: **12 passaram, 0 falharam**, sem rede/inferência. Verifica mutação efetiva do evento congelado, esforço, isolamento, correlação headless, limites de contexto, manual, worker, falha de RPC, ausência de correlação e telemetria sem dupla contagem.
- `claude -p /ia-hub-health --plugin-dir scripts/memory/claude-mod --output-format json`: comando carregado; `duration_api_ms=0`, `num_turns=0`, tokens=0.
- `python scripts/memory/claude-mod/proof/native_smoke.py`: duas inferências reais, RPC Python simulado em diretório temporário removido ao final. Login nativo existente, sem `--bare` ou opções que afrouxam permissões. MCPs/configurações são omitidos só para essa invocação isolada. O modelo inicial foi `opus`; os eventos registraram `current_model:'claude-opus-5-5'`.

| Prompt | Modelo realmente reportado | Resposta exata | Input | Output | Cache lido | Cache criado | Duração CLI | Estimativa CLI USD |
|---|---|---|---:|---:|---:|---:|---:|---:|
| `1+1` | `claude-haiku-5-5` | `2` | 2 | 3 | 535 | 2947 | 1512 ms | 0.00059645 |
| `2+3` | `claude-sonnet-5-5` | `5` | 2 | 3 | 535 | 2947 | 1573 ms | 0.0118755 |

Dados completos: `scripts/memory/claude-mod/proof/latest-results.json`, incluindo `modelUsage` do CLI e eventos `start/attempt/finish` do mod. Essa prova demonstra a mutação no caminho nativo com autenticação existente, **não** a persistência no daemon IA-Hub real nem disponibilidade no Desktop/WSL. O custo é estimativa de tabela emitida pelo CLI, não cobrança adicional comprovada da assinatura. São somente dois acertos aritméticos; não comprova economia de tokens ou qualidade em tarefas de desenvolvimento.

Tentativas anteriores também foram consideradas: duas aritméticas ainda com correlação antiga usaram Opus (respostas corretas, controle não comprovado); duas com aliases foram recusadas (sem modelo reportado/usage no mod, custo desconhecido). Nenhuma delas conta como economia ou sucesso de roteamento. A correção de correlação e o uso de IDs canônicos produziram a prova acima; não são necessárias novas inferências para os testes offline finais.

## Instalação persistente

Copiar o plugin para diretório permanente e substituir os dois caminhos antes de registrar. O marketplace fica em `.claude-plugin/marketplace.json` na própria raiz do plugin; seu `source:'./'` aponta para essa raiz. O caminho deve ser absoluto e continuar existindo. Preservar configurações/hooks de terceiros e fazer backup das alterações gerenciadas.

```powershell
claude plugin validate 'CAMINHO_PERMANENTE' --strict
claude plugin marketplace add 'CAMINHO_PERMANENTE'
claude plugin install ia-hub-router@ia-hub-local
claude plugin list --json
```

Executar `/reload-plugins` ou iniciar nova sessão para aplicar. Não reiniciar sessões automaticamente. Conferir `/ia-hub-health`, o status habilitado e um teste offline do plugin instalado. Um marketplace local relativo é lido diretamente; alterações passam a valer no reload/início seguinte. Não prometer que somente editar `enabledPlugins` tenha executado uma instalação. O instalador raiz deve provar add/install em configuração temporária primeiro e só então aplicar a autorização do usuário no ambiente real.

## Fontes primárias

- [API dos mods](https://code.claude.com/docs/en/plugins/mods/api): sandbox, env, processos e permissões.
- [Eventos](https://code.claude.com/docs/en/plugins/mods/events): imutabilidade, contexto e modelo observado em usage.
- [Test kit oficial](https://code.claude.com/docs/en/plugins/mods/test): testes sem inferência.
- [Marketplace local](https://code.claude.com/docs/en/plugin-marketplaces): source relativo, add/install e reload.
- [Modelos](https://code.claude.com/docs/en/model-config): IDs atuais; a rejeição dos aliases em `turn.step` é evidência runtime local, não afirmação inferida dessa página.
- Implementação da build instalada: `process.run` valida `init.stdin` string e envia ao pipe; o caminho interativo constrói `prompt.submit` com `turnId`, enquanto a prova headless acima exige correlação via `turn.start`.
