# Orquestração distribuída v1 — evidências e limites

2026-10-15. Reutiliza serviço, MCP, SQLite e runtime existentes. O usuário permanece no seu ambiente. Não há gateway de credenciais nem um novo chat obrigatório.

## O que mudou

| Objetivo | Capacidade entregue | Evidência / limite |
|---|---|---|
| Seleção de modelos | Política determinística, modelos/esforço por complexidade, preservação de provedor e modo manual | Claude instalado: Opus solicitado → Haiku 5.5 observado. OpenCode: contrato da versão 1.18.33 e execução do plugin em teste isolado; sem nova chamada real ao provedor |
| Delegação e paralelismo | Modelo de novos subagentes Claude controlado pelo mod; executor assíncrono com dois workers e subtarefas explicitamente independentes | Testes de execução, orçamento, recursão e falhas. Não demonstra ganho econômico de paralelizar qualquer tarefa; orçamento nativo Claude ainda não tem prova de atomicidade do runtime |
| Economia de contexto | Contexto por projeto, fallback global explícito e orçamento de caracteres mantendo JSON/proveniência | Testes e recuperação real; caracteres não são contagem exata de tokens. Contexto fixo do próprio harness continua existindo |
| Reutilização | Escrita automática de resultados e recuperação antes da próxima execução, memória histórica preservada | Claude → Codex e Codex → Claude passaram em novas sessões CLI; valor secreto de teste fornecido somente ao escritor, leitor respondeu com o código recuperado |
| Escalonamento | Uma escalada, até duas tentativas; validação exata/trecho/JSON | Regressões reproduzíveis. Auth/permissão/política bloqueiam tentativa adicional; JSON válido não comprova correção técnica |
| Cooperação multimodelo | Adaptadores com autenticação nativa, MCP comum e resultados com origem | Claude/Codex exercitados com modelos reais; AGY/OpenCode tiveram contratos/parsers/configurações testados, sem nova prova completa de inferência nesta evolução |
| Mensuração | Ledger aditivo de runs, tentativas, eventos, uso, custo reportado, duração e validação | Filhos/retries do dispatcher incluídos. Telemetria nativa declara cobertura incompleta dos filhos; custo desconhecido fica nulo |
| Ecossistema | Dez ferramentas MCP nos quatro CLIs configurados; instaladores Windows/Linux atualizados | GUI, ChatGPT convencional e todos os modelos locais continuam dependendo de capacidades e testes próprios |

## Testes reproduzíveis

Nas fontes, Python 3.11+:

```sh
python -m unittest discover -s tests
claude plugin test scripts/memory/claude-mod
claude plugin validate scripts/memory/claude-mod --strict
python scripts/build-portable.py
```

Windows: 134 testes Python, 128 passaram e 6 ignorados. Ubuntu/WSL: 134, 126 passaram e 8 ignorados. Mod Claude: 12 passaram. Testes incluem HTTP real isolado, JS real do plugin OpenCode, perfis carregados pelo Codex, migração, histórico, paginação com 1.000 empates, interrupção, idempotência, cache e subprocessos com filho/neto. O watchdog POSIX também foi testado com morte abrupta do daemon. Não controla a fatura remota após cancelamento local.

Provas que consomem cota/custo exigem opção explícita:

```sh
python scripts/benchmark.py --live --memory-only --output memoria.json
python scripts/benchmark.py --live --paired-only --output comparativo.json
```

O piloto final tem duas tarefas simples, dois braços por cliente e oito chamadas. Foram oito respostas exatas. Claude reportou estimativas de USD 0,0100152 no baseline Sonnet e USD 0,00041106 no braço Haiku; ambas são estimativas do harness, com cache distinto, não custo faturado nem uma taxa de economia generalizável. Codex reportou 34.806 contra 34.810 tokens de entrada e 16 de saída em cada braço, custo desconhecido: **não houve economia de tokens demonstrada nesse cliente**. Modelos solicitados e observados permanecem separados; o stream Codex não informou modelo observado.

Não há aleatorização ampla, intervalo de confiança, prova de qualidade em código complexo ou ganho global de paralelismo. O piloto alterna a ordem dos braços, registra fingerprints da implementação e usa bases vazias por chamada, mas caminhos temporários e cache do provedor variam. O próximo benchmark deve congelar essas variáveis e ampliar o conjunto com critérios externos de qualidade.

## Instalação ativa

Backup completo antes da atualização; tabelas aditivas, nenhum registro removido. Conferência comprovou todos os IDs e pares históricos (ID, revisão) anteriores preservados e demais MCPs Codex intactos. Vinte e nove capturas Codex receberam seu projeto de origem sem alterar IDs/revisões/confiança. Reparo equivalente passa a ocorrer automaticamente no observador. Replay legado OpenCode é paginado/deduplicado e pode ampliar legitimamente a base histórica. Quatro notas geradas por fixtures foram classificadas como teste, sem apagar conteúdo/histórico.

Serviço terminou com integridade `ok`, embeddings `ready`, projeções sem conflito e dez ferramentas em cada registro MCP CLI. Mod Claude persistente foi instalado pelo gerenciador oficial e comprovado contra o serviço real: Opus inicial → Haiku 5.5 observado, resposta exata 29, tentativa e tokens no ledger. Recarregar os clientes/sessões antigos é necessário.

O worker Claude leu uma fixture cujo conteúdo não estava no prompt. O worker Codex teve essa leitura bloqueada pela política nativa; o resultado foi falha e a regressão agora impede escalada nesse caso. A atualização preservou essa política. Não afirmar leitura irrestrita ou automação universal nos apps.
