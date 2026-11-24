# Antigravity — específico

## Modelos
- Padrão: Gemini 3.8 Flash (`gemini-3.8-flash-medium`) para agilidade máxima, cota livre e baixo consumo no fluxo diário.
- Subagentes: delegar varreduras, buscas e leituras volumosas para `flash` ou `flash_lite` via `invoke_subagent`.
- Decisões difíceis / Arquitetura: alternar via `/model` para `gemini-4-hydrogen-medium` ou `claude-sonnet-4-6` apenas durante o planejamento/diagnóstico crítico, voltando ao Flash para a execução.
- Preferir ferramentas nativas de busca (`find_by_name`, `grep_search`) a comandos de shell para procurar arquivos.
