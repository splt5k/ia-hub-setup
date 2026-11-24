# Memória compartilhada — plano de implementação

**Objetivo:** descoberta de um ambiente recuperada e enriquecida por outro, com captura automática comprovada.
**Spec:** desenho aprovado em `C:/Users/MaykoM/Documents/Codex/2026-10-15/de/outputs/diagnostico-memoria-compartilhada.md`.
**Execução:** inline no IA-Hub existente; preservar alterações locais, sem commits. Aprovação recebida em 2026-10-15.
**Arquitetura:** serviço local autenticado em loopback, SQLite e projeções Markdown; MCP stdio é um cliente fino do serviço. Embeddings multilíngues locais e FTS5. Hooks e observador incremental capturam respostas finais sem saídas de ferramentas.

## Restrições

- Manter `contexto/` e banco fora do Git; sem exposição remota.
- Backups antes de configurações; preservar outros MCPs e hooks.
- Relações inferidas têm pontuação; não fundir contradições por similaridade.
- Memória recuperada é evidência não confiável, nunca instrução.
- Não forjar confiança de hooks do Codex nem desabilitar permissões.
- Apps sem exportação/hook verificável recebem acesso MCP, não promessa de captura universal.

## Etapas e verificação

- [x] Núcleo: testes RED de persistência, idempotência, revisões, concorrência, busca, relações, edição externa e recuperação de projeções. Implementar SQLite/transações, FTS5, embeddings opcionais com diagnóstico explícito e notas com wikilinks.
- [x] Serviço: API local com token e MCP stdio; teste real initialize/list_tools/call_tool. Captura incremental de mensagens finais de Claude/Codex, sem tools/analysis; cursores persistentes. Reconciliar notas antigas sem reingerir a própria projeção.
- [x] Adaptadores: registrar MCPs aditivamente em Claude Code/Desktop, Codex, Antigravity e OpenCode; hooks Claude e plugin OpenCode; observador local para Claude/Codex. Inicialização oculta no login e diagnóstico operacional.
- [x] Prova: Claude Code grava marcador imprevisível; nova sessão Codex o recupera sem receber o valor e grava derivação; nova sessão Claude a encontra. Provar também captura automática de resposta final sem chamada memory_store.
- [x] Encerramento: executar testes, revisão independente, corrigir falhas relevantes, atualizar README e nota do projeto, entregar evidências e limites por ambiente.

## Contratos

`Memory.store(title, content, project='', source='', kind='knowledge', key='', tags=[], status='reported')` retorna id/revision/deduplicated. `search(query, project='', limit=5)` retorna evidências com score/método. `get(id)` inclui revisões e relações. `reconcile()` importa notas legadas e edições externas. HTTP `/rpc` recebe `{action, arguments}` autenticado por bearer token; MCP expõe operações equivalentes.

## Registro de execução

- Pre-flight: adaptadores dependem apenas do contrato HTTP/MCP; capturador e projetor dependem do mesmo núcleo. Escritas e projeções serializadas no serviço, com transações e reparação de projeções.
- Decisão: serviço e observador únicos evitam carregar o modelo de embeddings em cada hook e permitem capturar Claude/Codex sem alterar confiança de hooks.
- Decisão: respostas capturadas automaticamente têm estado `reported`, diferente de conhecimento validado; hipóteses não são promovidas automaticamente a fatos.
- Decisão: alterações aditivas no checkout atual para integrar ao IA-Hub já instalado; não criar checkout isolado que ficaria desconectado das regras ativas.

- Concluído em 2026-10-15: 35 testes passam; prova automática Claude Code ↔ Codex; leitura/escrita/captura nos quatro CLIs. Apps gráficos e ChatGPT convencional estão explicitamente separados na matriz de evidências.
- Refinamento adicional autorizado: nomes legíveis/IDs estáveis, índice sem arestas, fontes legadas e decisões com histórico, preservação de anotações e recuperação por diário de movimentos.
