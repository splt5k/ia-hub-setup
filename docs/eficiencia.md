# Demonstração de eficiência (piloto) e matriz por ambiente

Piloto real em **2026-10-15**, `scripts/benchmark.py --live --paired-only`: duas tarefas triviais com resposta exata
(`17 + 28` e a lista JSON dos pares entre 1 e 6), executadas pelo dispatcher com as contas já logadas.
**Linha de base** = modelo fixo escolhido manualmente (`mode=manual`); **hub** = decisão determinística do IA-Hub.
Cada chamada usa banco e projeto novos; a ordem dos braços alterna. Critério externo de qualidade: validador de texto exato.
Amostra mínima (2 tarefas × 2 braços × 3 ambientes): **mostra o mecanismo, não prova economia geral**.

| Cliente | Tarefa | Braço | Status | Validação | Modelo pedido | Modelo reportado | Tent. | In | Out | Cache | Custo reportado (US$) | Latência (ms) |
|---|---|---|---|---|---|---|---|---|---|---|---|---|
| antigravity | 0 | baseline | succeeded | True | gemini-3.8-flash-medium | None | 1 | 16335 | 144 | 0 | None | 11187 |
| antigravity | 0 | hub | succeeded | True | gemini-3.8-flash-low | None | 1 | 16343 | 2 | 0 | None | 7125 |
| antigravity | 1 | baseline | succeeded | True | gemini-3.8-flash-medium | None | 1 | 16336 | 1511 | 0 | None | 21328 |
| antigravity | 1 | hub | succeeded | True | gemini-3.8-flash-low | None | 1 | 16345 | 5 | 0 | None | 7375 |
| claude-code | 0 | baseline | succeeded | True | sonnet | claude-sonnet-5-5 | 1 | 2 | 3 | 3109 | 0.0071809000000000005 | 5359 |
| claude-code | 0 | hub | succeeded | True | claude-haiku-5-5 | claude-haiku-5-5 | 1 | 2 | 3 | 4623 | 0.00024153000000000003 | 4578 |
| claude-code | 1 | baseline | succeeded | True | sonnet | claude-sonnet-5-5 | 1 | 2 | 9 | 3843 | 0.0044383 | 5609 |
| claude-code | 1 | hub | succeeded | True | claude-haiku-5-5 | claude-haiku-5-5 | 1 | 2 | 9 | 4623 | 0.00024873000000000007 | 6000 |
| codex | 0 | baseline | failed | False | gpt-6.1-sol | None | 1 | None | None | None | None | 2313 |
| codex | 0 | hub | failed | False | gpt-6.1-sol | None | 1 | None | None | None | None | 2297 |
| codex | 1 | baseline | failed | False | gpt-6.1-sol | None | 1 | None | None | None | None | 2297 |
| codex | 1 | hub | failed | False | gpt-6.1-sol | None | 1 | None | None | None | None | 2297 |

Custo "reportado" é o campo informado pelo cliente (Claude Code); não é fatura. O Antigravity não informa custo nem modelo
executado; tokens de entrada incluem o prompt de sistema do CLI (~16 mil), igual nos dois braços.

## Leitura

- **Claude Code:** mesma qualidade (2/2 validadas nos dois braços); o roteador escolheu `claude-haiku-5-5` no lugar de `sonnet`
  e o custo reportado caiu de ~US$ 0,0044–0,0072 para ~US$ 0,00025 por chamada. Modelo pedido = modelo reportado nas quatro chamadas.
- **Antigravity:** mesma qualidade (2/2); `flash-low` no lugar de `flash-medium` gerou 2–5 tokens de saída contra 144–1.511 e latência de 7,1–7,4 s contra 11,2–21,3 s.
  O modelo executado não é informado pelo CLI, então só o **modelo pedido** é comprovado, não o executado.
- **Codex:** as quatro chamadas falharam porque a conta atingiu o limite de uso do provedor. **Sem medida**; falha registrada, sem tentativa repetida paga.
  A política de roteamento do Codex (`gpt-6.1-sol` nas camadas baixa/média, `gpt-6-astra` na alta) continua **sem prova de economia**.
- Escalonamento: no primeiro piloto (antes da correção do parser do Antigravity) a saída vazia reprovou na validação e o executor escalou uma vez
  (`flash-low` → `flash-medium`) e parou ao atingir o limite de 2 tentativas, sem laço. Evidência em `docs/evidencias/orquestracao-piloto-2026-10-15.json`.
- Troca nativa no Claude Code (CLI): com `model: sonnet` configurado, o mod roteou um prompt trivial para `claude-haiku-5-5` e foi esse o modelo executado.

Dados brutos: `docs/evidencias/benchmark-2026-10-15.json`. Não há tarefas difíceis nem de várias etapas neste piloto: **o ganho em tarefas complexas, onde modelos menores podem falhar, não foi medido.**

## Matriz por ambiente

| Ambiente | Memória Obsidian | Orquestração | Status | Evidência / limite |
|---|---|---|---|---|
| Claude Code (CLI) | MCP + hooks; leitura e escrita | mod troca o modelo por prompt; dispatcher via MCP | **Comprovado em execução real** | Gravou/leu; haiku executado com `sonnet` configurado; tarefas validadas |
| Claude Desktop (GUI) | Registro MCP no `claude_desktop_config.json` | ferramentas MCP; sem troca de modelo da conversa | Configurado; **não validado em sessão gráfica** | Sem hook de prompt no app de conversa |
| Codex (CLI) | MCP + observador de respostas | dispatcher via MCP | Instalado e configurado; **leitura real impedida** | Limite de uso da conta durante os testes |
| ChatGPT Desktop / Codex App (GUI) | Depende do MCP/conector da sessão | idem | Configurado; **não validado** | Sem controle do modelo da janela aberta |
| Antigravity (CLI) | MCP + hooks de contexto e captura | dispatcher via MCP; modelo pedido registrado | Dispatcher **comprovado**; hooks configurados | CLI não informa o modelo executado |
| Antigravity (GUI) | Config MCP disponível | idem | **Não validado** | Sem interceptação comprovada |
| OpenCode (CLI) | plugin injeta contexto e captura a resposta final | **nenhuma, por desenho** | **Comprovado**: leu o que o Claude gravou e gravou o que o Claude leu | 0 execuções no ledger de orquestração |
| OpenCode (GUI) | mesmo plugin/MCP | nenhuma | Mesma configuração do CLI; **GUI não aberta** nos testes | — |
