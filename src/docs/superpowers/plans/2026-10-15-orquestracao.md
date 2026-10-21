# Orquestração por ambiente — plano executável

> Execução: superpowers:subagent-driven-development e TDD. Desenho e plano já revisados pelo usuário em outputs/auditoria-ia-hub/ARQUITETURA.md e PLANO.md; usuário autorizou implementação nesta mensagem. Não reabrir decisões técnicas rotineiras.

Goal: política comum aplicada em pontos de controle nativos, memória corrigida, execução local verificável, delegação limitada e telemetria, sem novo chat obrigatório.
Architecture: reutilizar daemon/MCP/SQLite/runtime. Política determinística configurável, ledger aditivo, adaptadores CLI com permissões nativas, plugins nativos onde há controle por prompt. Interfaces sem controle ficam explicitamente limitadas.

## Restrições
- Preservar produção D:/Pessoal/IA-Hub, dados e IDs/revisões; testar isolado antes de aplicar.
- Sem novo provedor pago, gateway de credenciais, relaxamento de sandbox ou dependência de LLM para classificar toda solicitação.
- Contadores ausentes/desconhecidos não são zero; preço estimado não é fatura da assinatura.
- Distribuição final mantém instalar.cmd/sh autocontidos + README/imagem/metadados; fontes/testes versionados separadamente.
- Não alegar automação universal GUI nem eficiência sem teste pareado de qualidade/uso.

## Unidades e gates
- [ ] T1 memória: contexto por projeto/fallback marcado, confiança por revisão, cursor composto e metadata/baselineCodex. Red/green das quatro regressões; repetir suite.
- [ ] T2 compatibilidade: perfis Codex legados migrados por versão, preservando demais configurações; contratos nativos documentados.
- [ ] T3 telemetria: Ledger(memory), tabelas aditivas runs/attempts/events e parsers Claude/Codex/agy/OpenCode; dedup/cumulativos/valores desconhecidos.
- [ ] T4 política/executor: plan(prompt,client,project), classificação determinística/tier/modelos elegíveis, validação e limite de tentativas, jobs e subtrabalhos readonly independentes com no máximo2paralelos. Testes com runners determinísticos + subprocessos reais.
- [ ] T5 integração: MCP APIs novas mantendo seis atuais; entryCLI; contexto/decisão por hooks, escolha efetiva no OpenCode via chat.message e controles nativos comprovados dos demais; docs explicam limites.
- [ ] T6 provas: rodar modelos reais em pelo menos dois ambientes suportados, recuperação cruzada, telemetria e comparação pareada sem atribuir redução só por usar modelo diferente. Aplicar produção combackup/restart/health apenas depois.
- [ ] T7 revisão, fonte versionada, novos pacotes equivalentes, README/capacidades/provas e atualização do ia-hub-setup.

## Foco de revisão
- Recursão de hooks/subprocessos e tarefas duplicadas por modelo; processo filho não inicia outro job automaticamente.
- Escolha explícita/manual de modelo e controles nativos não podem ser silenciosamente sobrepostos sem política opt-in.
- Permissão negada não causa escalonamento para contorná-la; nenhuma execução arbitrária de shell vinda do modelo.
- Falhas de dependência/auth/modelo/timeout/schema não podem produzir succeeded ou economia fictícia.
- Operações longas fora do lock da memória, reprocessamento idempotente e recuperação após crash.

## Rulings
- A auditoria técnica é base de falhas; capacidades nativas novas serão verificadas na versão instalada antes de afirmar controle automático.
- O motor pode ser compartilhado; o ponto de entrada e execução continuam no harness escolhido. MCP também expõe execução controlada para delegação local.
- Heurísticas e tiers são política inicial, não prova de menor preço global; a medição decide ajustes futuros.
