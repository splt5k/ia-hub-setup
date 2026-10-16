# Claude Code — específico

## Modelos
- Padrão: Sonnet. Opus só para planejamento/arquitetura difícil (use `opusplan` ou troque manualmente e volte).
- Subagentes (em `~/.claude/agents`):
  - `buscador` (Haiku): buscas amplas, ler muitos arquivos, resumir logs/docs. Retorna só a conclusão.
  - `executor` (Sonnet): implementar um plano já definido, mudanças mecânicas em vários arquivos.
- Delegar ao `buscador` sempre que a resposta exigir varrer vários arquivos; não fazer essa varredura no contexto principal.

## Contexto
- Sugerir `/clear` ao mudar de assunto e `/compact` em sessões longas.
- Não ativar conectores/MCP que a tarefa não usa.
