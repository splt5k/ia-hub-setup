# Validação — evidências e limites

Data das provas: **2026-10-15/16**, PC Windows 11 x86_64 do mantenedor + Ubuntu 24.04 no WSL2.
Tudo abaixo foi executado de verdade, salvo onde está escrito **simulação** ou **não comprovado**.
Os pilotos com CLIs consomem cota das contas reais; os resultados são amostras pequenas, não prova geral de economia.

## 1. Testes automatizados (`python -m unittest discover -s tests -v`)

14 testes, todos passando em Windows. Cobrem, com daemon e SQLite reais em pasta temporária:

- instaladores sincronizados com `src/` (`tools/build.py --check`);
- OpenCode somente memória: roteador rejeita o cliente, política e configuração sem chaves de roteamento, plugin sem chamadas de orquestração e com JavaScript válido (`node --check`), MCP sem ferramentas `orchestration_*` para o OpenCode, daemon recusando `orchestration_*` vindo dele;
- limpeza do legado do OpenCode (por hash e por assinatura do conjunto completo; agente isolado do usuário é preservado);
- porta ocupada por serviço alheio: outra porta é escolhida e o serviço alheio não é tocado;
- memória: escrita por um cliente, leitura por outro, deduplicação por chave estável, nota Markdown no cofre, README/regras do produto não viram memória;
- parsing das saídas JSON dos CLIs (Antigravity 1.3).

## 2. Instalador distribuído

| Prova | Windows (`instalar.cmd`) | Linux (`instalar.sh`, Ubuntu 24.04/WSL, `tools/validate-linux.sh`) |
|---|---|---|
| `--self-test` (extração íntegra por SHA256, limpeza do temporário) | passou | passou |
| Instalação completa em ambiente sem o hub | passou (pasta nova `C:\Users\MaykoM\IA-Hub`) | passou, HOME descartável, ~52 s, busca semântica `ready` |
| Temporários removidos ao final | passou (0 pastas `ia-hub-setup.*`) | passou |
| Daemon continua funcionando após apagar a extração | passou | passou |
| Reexecução sem duplicar MCP/hooks/blocos | passou (blocos únicos conferidos) | passou: só mudam recibo do uv e lock temporário do Codex |
| Substituição do hub antigo | MCPs, hooks, marketplace do mod e tarefas agendadas apontam para a nova pasta; pasta antiga não alterada | n/a |

Defeitos reais encontrados e corrigidos nesta etapa: porta 43127 fixa bloqueava a instalação quando outro serviço a ocupava; o daemon herdava a pasta temporária do instalador e impedia a limpeza no Windows (exit 1); o importador tratava README/regras do produto como conhecimento; o parser não lia a saída do Antigravity 1.3; agentes antigos do OpenCode (de geração anterior) não eram removidos.

## 3. Memória entre CLIs (pilotos reais, contas autenticadas)

| Caminho | Resultado |
|---|---|
| Claude Code (CLI) grava via MCP → `reported`, origem `claude-code`, nota Markdown criada no cofre | **comprovado** |
| Claude Code → OpenCode (CLI), sessão nova, **sem chamar ferramenta** (plugin injeta contexto) | **comprovado**: o OpenCode respondeu o código gravado |
| OpenCode (CLI) → memória (plugin captura a resposta final; origem `opencode:session:…`) | **comprovado** |
| OpenCode → Claude Code (CLI), sessão nova | **recuperado automaticamente** (o Claude citou o código), mas **recusou afirmá-lo** por estar `reported`; é o comportamento de proveniência desenhado |
| Claude Code → Codex (CLI), sessão nova | **impedido**: a conta do Codex atingiu o limite de uso (erro do provedor, não contornado). Reexecutar após o reset |

## 4. Orquestração (3 ambientes) — piloto real, tarefa trivial `17 + 28`

Ver [eficiencia.md](eficiencia.md) para a comparação linha de base × IA-Hub e a matriz por ambiente.

## 5. Limitações comprovadas

- **Codex:** limite de uso da conta durante os testes; falha tratada sem repetição (uma tentativa, `failed`, erro do provedor registrado).
- **GUI:** Claude Desktop, ChatGPT Desktop/Codex App e Antigravity App recebem MCP (e, onde existe, o mecanismo oficial), mas **não há** interceptação de prompt nem troca de modelo da janela principal. Não foi aberta nenhuma sessão gráfica autenticada nesta validação.
- **Windows dentro do Claude Desktop:** processos filhos do app têm `AppData` virtualizado (MSIX). Instale numa pasta fora de `AppData` (`IA_HUB_INSTALL_DIR`) quando executar o instalador a partir dele; o registro do cofre no `obsidian.json` por esse caminho não chega ao Obsidian real.
- **Obsidian:** o hub é adicionado à lista de cofres só com o app fechado; com o app aberto, abra a pasta pelo atalho `obsidian://open?path=…` ou reabra depois.
- Máquina nova **real** comprovada uma vez, em Windows de órgão público com política que nega tarefas agendadas (ver seção 8). Ainda não testadas: Windows recém-formatado, Linux com GUI, outras distros, ARM, systemd real.
- O SHA256 embutido verifica integridade, não é assinatura digital.

## 6. Antigravity (2026-10-16)

Testes feitos pelo mantenedor no Windows, com a conta Google autenticada, instalação em `C:\Users\MaykoM\IA-Hub` e Antigravity CLI 1.3.6.

| Teste | Resultado | Evidência |
|---|---|---|
| CLI `agy --print` com chamada explícita ao MCP | **Comprovado** (duas vezes) | `response: DESK-1234`, uma rodada |
| CLI interativo: pergunta sem pedir ferramenta, respondida com memória do projeto | **Comprovado** | Código `CTX-5520` na transcrição (`transcript_full.jsonl`) com duas mensagens efêmeras injetadas pelo hook de contexto e nenhuma etapa de ferramenta |
| CLI: captura da resposta pelo hook de fim de turno | **Comprovado** | Registro com origem `antigravity:transcript:<conversa>` criado na mesma conversa |
| GUI: chamada ao MCP (`memory_context`) | **Comprovado** | Etapa "Search memory … · ia_hub" na conversa, resposta `DESK-1234` |
| GUI: injeção automática de memória (conversa nova) | **Comprovado** | Transcrição da conversa da GUI (`~/.gemini/antigravity/brain/<conversa>/…`): mensagens efêmeras injetadas pelo hook de contexto, resposta `CTX-5520` sem etapa de ferramenta, e captura posterior com origem `antigravity:transcript:…` |

Limites do hook de contexto do CLI, comprovados no código e nos testes:

- O hook recebe só `conversationId`, `invocationNum`, `modelName`, `transcriptPath` e `workspacePaths`. **Não recebe o texto da pergunta.**
- A recuperação usa o nome da pasta do projeto como consulta. Registros que não se ligam ao nome da pasta não são injetados.
- A injeção ocorre só na primeira rodada da conversa (`invocationNum` 1). Vale para o CLI e para a GUI, pois ambos usam os mesmos hooks em `~/.gemini/config/hooks.json`.
- Com a verbosidade padrão ("medium"), chamadas de ferramenta podem ficar recolhidas na tela; a transcrição é a evidência confiável.

Defeitos encontrados e corrigidos nesta etapa:

- Os hooks do Claude Code no Windows rodavam pelo bash, que apagava as barras invertidas (`command not found`). Correção: barras normais entre aspas (`d0a3667`).
- A correção anterior aplicou esse mesmo formato aos hooks do Antigravity, que rodam pelo PowerShell, onde ele é erro de sintaxe. Os hooks pararam de disparar. Correção: formato sem aspas, com `&` quando há espaço (`73320e7`). Teste valida o comando no parser do PowerShell.

Não validado: captura de conversas gráficas do Antigravity App (sem hook) e comportamento em outras versões do CLI.

## 7. Fechamento (2026-10-16)

Matriz final, confirmada pelo mantenedor:

| Ambiente | Memória (MCP `ia_hub`) | Injeção automática | Orquestração | Status |
|---|---|---|---|---|
| Claude Code (CLI) | Comprovado | Hooks de início e fim | Troca de modelo pelo mod (`sonnet` → `haiku`) | Comprovado |
| Claude Desktop (chat) | Comprovado (gravação e leitura) | Não existe (sem hook de prompt) | Não aplicável | Comprovado |
| Antigravity (CLI) | Comprovado | Comprovado (transcrição: `CTX-5520` sem busca) | Despacho validado | Comprovado |
| Antigravity (GUI) | Comprovado | Comprovado (mesmos hooks do CLI) | Não aplicável | Comprovado |
| Codex (CLI) | Comprovado (`ia_hub/memory_search`) | Não existe | Dispatcher `gpt-6.1-sol`, resposta validada | Comprovado |
| Codex App (GUI) | Comprovado (`Memory search`) | Não existe | Não aplicável | Comprovado |
| ChatGPT Desktop | Comprovado (mesmo MCP do Codex) | Não existe | Não aplicável | Comprovado |
| OpenCode (CLI) | Comprovado (leitura e escrita) | Plugin de contexto | Nenhuma, por desenho | Comprovado |
| Instalação em máquina nova (Windows, política sem tarefas agendadas) | Comprovado: memória ok, busca semântica pronta, integridade ok | — | — | Comprovado (seção 8) |
| Controle negativo (conta sem IA-Hub) | Ferramenta `ia_hub` ausente no outro PC | — | — | Comprovado |

Limites que permanecem: injeção só na primeira rodada e com consulta pelo nome da pasta; ChatGPT web não tem acesso à memória local; a memória não sincroniza entre máquinas.

## 8. Máquina nova: Windows de órgão público (2026-10-16)

Teste conduzido pelo mantenedor numa máquina de terceiros, com usuário comum, conta Google do Antigravity logada e sem o IA-Hub instalado antes.

- **Primeira execução (`instalar.cmd` v2026.10.16):** falhou na etapa de memória. A política negou a tarefa agendada "IA-Hub Memory" ("Acesso negado") e o instalador encerrou com código 1. Apps, Python e configurações já tinham sido instalados.
- **Correção (commit `ca3d7e5`, release v2026.10.17):** tarefa negada passa a gerar atalho na pasta Iniciar do usuário, sem administrador; se também for negado, a instalação segue no modo "manual".
- **Reparação com v2026.10.17:** concluída (exit 0). Memória compartilhada pronta, busca semântica `ready`, integridade `ok`, início no login pelo atalho ("startup-folder"). Clientes Claude Code, Codex CLI, Antigravity CLI e OpenCode presentes e integrados; Claude Desktop integrado.
- **Controle negativo e pergunta de contexto no Antigravity da máquina:** confirmados pelo mantenedor.

Não foi testado nesta máquina: a instalação do zero após formatação, nem Linux.
