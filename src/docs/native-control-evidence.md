# Controle nativo por prompt: evidências e contratos

2026-10-15. Escopo: inspeção sem inferência, instalação ou alteração de produção. Versões locais: Claude Code 2.1.299, Codex 0.162.0-alpha.17.2, agy 1.3.5, OpenCode 1.18.33. Este arquivo é o único artefato alterado pela investigação. Autenticação existente registrada na auditoria: Claude via claude.ai; Codex via ChatGPT. Isso não comprova disponibilidade de qualquer modelo.

## OpenCode: mutação efetiva antes da inferência

Tipos locais em `C:/Users/MaykoM/.config/opencode/node_modules/@opencode-ai/plugin/dist/index.d.ts:187`: `chat.message(input, output)` recebe `output.message: UserMessage` e `output.parts`. `UserMessage.model` contém `providerID` e `modelID`. O pacote de tipos local é 1.18.13; por isso conferi também o código da tag exata do CLI.

Em [prompt.ts v1.18.33](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/session/prompt.ts#L952), `chat.message` recebe a referência `info` como `output.message`; depois `sessions.updateMessage(info)` persiste essa referência. O loop usa `getModel(lastUser.model.providerID,lastUser.model.modelID)` em L1083. Portanto, o ponto correto é:

```js
'chat.message': async (input, output) => {
  const decision = await classify(output.parts, input.sessionID);
  output.message.model.providerID = decision.providerID;
  output.message.model.modelID = decision.modelID;
}
```

Mutar os campos ou `output.message.model`; NÃO substituir `output.message` inteiro: o chamador retém `info` e ignora o retorno do trigger. Alterar `input.model` não é o contrato de saída e pode não alterar a mensagem. Em [plugin/index.ts L263](https://github.com/anomalyco/opencode/blob/v1.18.33/packages/opencode/src/plugin/index.ts#L263), os plugins recebem os mesmos objetos sequencialmente; um plugin posterior pode sobrescrever a decisão.

`chat.params` permite temperatura, topP/topK, maxOutputTokens e options; não expõe modelo no output. `experimental.chat.system.transform` altera `system: string[]`: útil para instruções/contexto, sem contrato de roteamento. Os tipos são evidência estática; ainda é necessária prova com provedor simulado e teste da ordem de plugins.

O [servidor nativo](https://opencode.ai/docs/server/) permite enviar modelo/agente por mensagem a uma sessão, e o SDK local declara `POST /session/{id}/message` com `model`, `agent`, `parts`, `noReply`. Isso serve para despacho controlado sem gateway de inferência próprio. O plugin no servidor alcança seus clientes conectados; não foi validada aqui a instalação específica da GUI.

## Claude: hook tradicional versus mod executável

[UserPromptSubmit](https://code.claude.com/docs/en/hooks#userpromptsubmit) permite bloquear e acrescentar contexto, sem substituir modelo/prompt. PreModelSwitch aprova/nega uma troca já solicitada; também não fornece modelo substituto. Porém existe outro contrato nativo: **mods**.

Um mod intercepta [turn.step](https://code.claude.com/docs/en/plugins/mods/reference#turns), antes de cada requisição, e encaminha evento com modelo/esforço alterados:

```js
export function register(on) {
  on('turn.step', async function* ($, e, next) {
    return yield* next({ ...e, model: 'sonnet', effort: 'low' });
  });
}
```

Esse exemplo fixa valores; a política deve decidir antes do `next`. Os eventos são congelados: criar cópia, nunca atribuir em `e`. Para classificar por prompt, `prompt.submit` lê `e.text`; correlacionar com a requisição exige conferir os tipos gerados da versão, incluindo subagentes, em vez de presumir um estado global único.

Contrato mínimo do [loader](https://code.claude.com/docs/en/plugins/mods/create):

```text
<plugin>/.claude-plugin/plugin.json  {"name":"ia-hub-router","version":"0.1.0"}
<plugin>/hooks/hooks.json          {"modules":["./register.js"]}
<plugin>/hooks/register.js         export function register(on) {...}
```

`claude --plugin-dir PATH` carrega para aquela sessão. Instalação persistente usa marketplace/plugin convencional; depois `/reload-plugins` ou nova sessão. Manifesto não requer campo especial. Ao carregar interativamente, o Claude gera `.claude-plugin/types/claude-code/index.d.ts`, contrato exato da build. `claude plugin validate PATH` inspeciona sem executar; `claude plugin test PATH` executa testes offline.

O [ambiente do mod](https://code.claude.com/docs/en/plugins/mods/api#reach-files-processes-and-the-network) não fornece Node.js/require/spawn globais. Usar `$.process.run([executavel,...args])`, sem shell; ou `$.http.fetch`, `$.mcp.call`, `$.fs`. Imports somente internos e `claude-code`. As chamadas da API precisam estar explícitas para validação estática. Isso permite consultar o runtime Python IA-Hub já existente sem iniciar outra inferência.

[Disponibilidade](https://code.claude.com/docs/en/plugins/mods#where-mods-run): terminal >=2.1.287, Desktop Code >=2.1.286; funciona em `-p`/SDK sem UI. Desktop em sessão WSL não carrega plugins. A versão interna do Desktop precisa de `/status`: a versão do CLI não a comprova. O CLI local reconheceu `plugin test`; `plugin list --json` retornou `[]`. Logo: capacidade disponível, nenhum mod instalado/ativo demonstrado.

Prova sem inferência para implementação posterior: criar comando próprio `/ia-hub-health`, responder no `command.run` sem chamar modelo, executar `claude -p "/ia-hub-health" --plugin-dir PATH`. Para provar mutação, o [test kit](https://code.claude.com/docs/en/plugins/mods/test) permite disparar `$.turn.step({turnId:'t',index:0,model:'claude-test',messageCount:1})`, drenar o async iterator e interceptar o evento final com stub async generator que verifica `e.model`. O resultado do stub contém `turnId,index,answer,toolUses,stopReason,usage`; nenhuma API é chamada. Não executei essa prova porque exigiria criar arquivos além deste documento.

## Codex e Antigravity

Nos [hooks atuais Codex](https://developers.openai.com/codex/hooks), `model` é entrada informativa. UserPromptSubmit produz contexto/bloqueio; não tem output para modelo. Não implementar autoseleção nativa por retorno inventado. O [app-server](https://developers.openai.com/codex/app-server#turns) aceita `turn/start` com `model` e `effort`, e publica `thread/tokenUsage/updated` e `model/rerouted`. Isso dá controle ao cliente que envia a requisição, não interceptação automática da GUI já aberta. `codex exec --model ... --json` controla uma invocação própria com autenticação nativa.

`agy --help` local comprova `--model`, `--effort`, `--agent`, `--print`, entrada/saída stream-json e retomada por conversa. Não comprova troca por mensagem da GUI nem schema de uso. `agy models` terminou com código 0, sem inferência, listando: `gemini-3.8-flash-high`, `gemini-3.8-flash-medium`, `gemini-3.8-flash-low`, `claude-sonnet-4-6`, `claude-opus-4-6-thinking`, `gpt-oss-120b-medium`. `models --help` não oferece JSON. Elegibilidade listada não prova chamada bem-sucedida/preço. [Entrada oficial CLI](https://antigravity.google/docs/getting-started?tab=cli).

## Telemetria, autenticação e ambientes

OpenCode SDK: `message.updated.properties.info` inclui assistant `providerID,modelID,parentID,time,cost,tokens{input,output,reasoning,cache{read,write}}`; `step-finish` também contém tokens/custo. Deduplicar por mensagem/passo e escolher uma granularidade, evitando somar ambos. Capturar todas as sessões filhas, não só última resposta em `session.idle`. Zero inicial não prova uso gratuito.

Claude mod [turn.step/turn.complete](https://code.claude.com/docs/en/plugins/mods/events#follow-a-turn): resultado por requisição tem modelo e tokens input/output/cache; turn.complete informa totais, duração e agentId. Guardar por requisição OU total do turno, sem duplicar. O [JSON headless](https://code.claude.com/docs/en/headless) informa estimativas de custo; continuar sessão pode repetir totais anteriores.

Help local confirma que Claude `--bare` desliga hooks/mods e ignora OAuth/keychain: exige chave/API helper ou credenciais do provedor. Não usar para preservar assinatura. Codex `--ignore-user-config` preserva autenticação em CODEX_HOME, mas remove integração configurada. Invocações normais usam login do harness; não exportar/copiar tokens.

Windows: subprocesso por lista, executável absoluto; .cmd/.ps1 requerem adaptador explícito. Linux/WSL: resolver binário, caminhos e Python próprios, sem transplantar caminhos Windows. Não supor instalação/autenticação compartilhada entre hosts. Houve inspeção Windows apenas; execução Linux e interceptação GUI ainda pendentes. Sucesso da instalação futura exige smoke offline por ambiente, permissões mantidas e prova explícita do modelo observado.
