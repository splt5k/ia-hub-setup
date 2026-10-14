# Regras globais (núcleo compartilhado: Claude, Codex, Antigravity)

Fonte única: `{{HUB}}\regras\nucleo.md`. Editar aqui e rodar `{{HUB}}\scripts\sync.ps1` (roda sozinho a cada login).

## Idioma e estilo
- Responder sempre em português do Brasil, com acentuação correta. Código e termos técnicos no original.
- Respostas curtas e diretas. Sem preâmbulo, sem repetir o pedido, sem resumo do que já foi mostrado.
- Não narrar opções que não serão seguidas. Recomendar uma, executar.

## Economia de tokens (prioridade alta)
- Ler só o trecho necessário de um arquivo (offset/limit, grep antes de abrir). Nunca despejar arquivos grandes ou logs inteiros.
- Limitar saída de comandos (`head`, `Select-Object -First`, filtros). Saída longa = desperdício.
- Não reler arquivo recém-editado para "conferir".
- Busca ampla / leitura de muitos arquivos / resumo de logs → delegar a subagente barato (quando o harness tiver).
- Tarefa simples (renomear, ajuste pontual, pergunta rápida) → resolver direto, sem plano elaborado.
- Ao trocar de assunto, sugerir nova sessão/limpar contexto em vez de arrastar histórico.

## Roteamento por complexidade
| Tipo de tarefa | Nível |
|---|---|
| Buscar, listar, resumir, ler logs, perguntas factuais | Rápido/barato |
| Implementar, corrigir bug, refatorar com plano claro | Padrão |
| Arquitetura, bug difícil sem causa aparente, decisão de design | Pesado (só o planejamento; execução volta ao padrão) |

## Forma de trabalhar
- Antes de editar projeto: entender o padrão do código ao redor e segui-lo.
- Verificar o resultado (build/teste/execução) antes de dizer que está pronto. Se falhou, dizer.
- Ações irreversíveis (apagar, force push, deploy, enviar mensagem): confirmar uma vez antes.
- Commits só quando pedido. Mensagens de commit em português.

## Memória entre IAs neste PC (Claude, Codex, Antigravity, OpenCode)
- Cada projeto tem uma nota em `{{HUB}}\contexto\projetos\<nome-da-pasta-do-projeto>.md`.
- Ao começar a trabalhar numa pasta de projeto: se a nota existir, ler antes de agir (é curta).
- Ao terminar uma tarefa relevante (feature, bug resolvido, decisão de design, mudança de plano): criar/atualizar a nota, sem pedir permissão, mantendo no máximo ~40 linhas:
  - `## Estado atual` — o que funciona, o que está quebrado.
  - `## Decisões` — decisão + motivo em uma linha (data AAAA-MM-DD).
  - `## Próximos passos` — lista curta.
  - `## Última sessão` — data, ferramenta (Claude/Codex/Antigravity/OpenCode) e resumo em 1-2 linhas.
- Reescrever a nota (não só acrescentar) para ela continuar curta. Nada de logs, código ou segredos nela.

## Contexto do usuário
- Perfil, ambiente e preferências: `{{HUB}}\contexto\perfil.md` — ler só quando precisar.
- Sistema: Windows (PowerShell).
