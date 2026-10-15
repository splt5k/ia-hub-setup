# IA-Hub

Configura de uma vez **Claude Code, Codex, Antigravity e OpenCode** para gastar menos tokens e trabalhar melhor no Windows. As regras são as mesmas para todas as IAs, e elas compartilham uma memória de cada projeto entre si.

## Instalar

1. Instale o [Git](https://git-scm.com/download/win), se ainda não tiver.
2. Clone em qualquer pasta:
   ```
   git clone https://github.com/splt5k/ia-hub-setup.git
   ```
3. Dois cliques em **`instalar.cmd`**.

O instalador:
- detecta quais IAs existem no PC e configura só essas;
- faz backup do que já existia, em `_backup\`;
- agenda uma tarefa que reaplica as regras a cada login;
- pode ser rodado de novo quando quiser.

Depois, **feche e abra de novo** as IAs que estavam abertas.

**ChatGPT (app/web):** ele não lê arquivos do PC. Cole o texto de [`chatgpt/instrucoes-personalizadas.md`](chatgpt/instrucoes-personalizadas.md) em Configurações → Personalização.

## O que muda

| IA | Padrão depois de instalar | Para tarefa difícil |
|---|---|---|
| Claude Code | Sonnet, resumo automático de conversa ligado, subagentes `buscador` (Haiku) e `executor` (Sonnet) | `/model opus` e depois `/model sonnet` |
| Codex | GPT-6.1 Sol, raciocínio médio, perfis `rapido` e `pesado` | `codex --profile pesado` |
| Antigravity | regras curtas (o arquivo de instruções antigo vai para o backup) | trocar para Pro no seletor |
| OpenCode | orquestrador + 8 subagentes, cada um no modelo certo | escolhe sozinho |

Regras que todas seguem (`regras/nucleo.md`):
- respostas em português, curtas e diretas;
- leem só o trecho necessário dos arquivos e limitam a saída de comandos;
- usam o modelo barato para buscas, o médio para implementar e o forte só para planejar;
- confirmam antes de ações irreversíveis.

## Memória entre IAs

O serviço local `ia_hub` mantém histórico em SQLite, busca FTS5 e embeddings multilíngues locais. Os agentes acessam a mesma memória pelo MCP; o Obsidian mostra notas em `Memoria/` com links de projeto, assunto e similaridade. As notas antigas em `contexto/` são importadas incrementalmente.

Os arquivos têm nomes legíveis; IDs estáveis permanecem no frontmatter e no banco. O índice é uma consulta e não cria arestas. As fontes de `contexto/`, `regras/`, README e planos autorais são indexadas sem editar os originais. Decisões são extraídas literalmente e vinculadas à fonte; correções preservam a identidade e o histórico, e decisões removidas ficam `superseded`, fora da busca corrente.

Renomes dentro de `Memoria/` são reconciliados pelo ID. Assuntos e projetos aceitam anotações humanas, preservadas e indexadas como conhecimento. Movimentos têm diário de recuperação para reconciliar arquivos após uma interrupção. Testes sintéticos identificados por projeto/sessão permanecem preservados fora do grafo principal; documentos reais que apenas descrevem os testes continuam visíveis.

- Claude Code: contexto por hooks, gravação por MCP e captura de respostas finais.
- Codex App/CLI local: MCP e observador das respostas finais. Sessões existentes precisam recarregar ferramentas; a configuração não altera confiança de hooks.
- OpenCode: MCP, plugin de contexto e observador de respostas finais do banco local, somente leitura.
- Antigravity CLI: MCP, contexto por hooks e captura do transcript indicado pelo hook Stop. Formato validado na versão 1.3.5; app gráfico precisa recarregar e ser validado separadamente.
- Claude Desktop: MCP configurado; reiniciar o app para carregar. Não há captura universal comprovada das conversas comuns.
- ChatGPT convencional: precisa de ponte/conector disponível à conversa. Instruções personalizadas e configuração do Codex não concedem esse acesso.

As observações automáticas são `reported`, não fatos confirmados. Os agentes devem registrar decisões relevantes por `memory_store` e só usar `validated` quando houver evidência. Correções com `key` estável preservam revisões; relações semânticas são afinidade, não causalidade.

### Instalar e diagnosticar

Requer [uv](https://docs.astral.sh/uv/) no PATH; Python 3.11 e dependências são isolados em `.memory-runtime/`. O primeiro início baixa um modelo local de aproximadamente 220 MB. O instalador principal também executa:

```powershell
& .\scripts\install-memory.ps1
& .\.memory-runtime\Scripts\python.exe .\scripts\memory\entry.py health
```

A tarefa `IA-Hub Memory` inicia o serviço oculto no login. O cliente também o inicia sob demanda. Ele escuta somente `127.0.0.1:43127`, com token local; não há exposição pública. `semantic_state: ready` comprova modelo carregado; `last_error`, `projection_conflicts` e `pending_projections` expõem falhas. Logs e backups de configurações ficam em `contexto/.memory/`.

O observador processa mensagens finais novas, sem raciocínio interno nem saídas de ferramentas. Não importa conversas antigas em massa. Claude/Codex dependem do formato de log da versão instalada; OpenCode depende de seu schema SQLite; alterações desses formatos precisam de nova validação. A redação automática de credenciais é uma proteção parcial: não colocar segredos nas notas ou respostas finais.

Notas gerenciadas preservam o marcador `<!-- ia-hub:relations -->`. Edições no corpo entram como revisões. Alteração estrutural que impeça leitura aparece como conflito e não é sobrescrita. Projeções ausentes são reconstruídas. Há snapshot diário consistente do banco, sem copiar arquivos WAL manualmente.

Os testes reais de 2026-10-15 comprovaram Claude Code → Codex → Claude Code e captura automática de Claude, Codex, Antigravity CLI e OpenCode. A busca por paráfrase também foi exercitada com o modelo ativo.

Foi comprovada recuperação automática nos dois sentidos em novas sessões, com identificadores aleatórios ausentes dos pedidos dos leitores: Codex acionou a memória pelas regras globais; Claude recebeu contexto por hook mesmo com MCP e ferramentas desabilitados naquela sessão de teste. OpenCode e Antigravity CLI também leram e gravaram pelo MCP. Nenhum desses testes CLI deve ser apresentado como validação dos apps gráficos. No Antigravity CLI, o instalador concede somente as seis operações de `ia_hub`, preservando as demais políticas de permissão.

`contexto/`, `Memoria/`, modelos e runtime ficam fora do Git. Todos os ambientes locais acessam a mesma base; isso não sincroniza computadores diferentes. O conteúdo recuperado é enviado ao provedor do agente quando usado como contexto, conforme as permissões desse ambiente.

## Personalizar

- Edite os arquivos em `regras/` e dê dois cliques em **`sincronizar.cmd`** para aplicar na hora.
- `regras/nucleo.md` vale para todas as IAs; `claude.md`, `codex.md` e `antigravity.md` são os ajustes de cada uma.
- O Obsidian (opcional) abre esta pasta como cofre para você ver as notas. Ele não precisa ficar aberto.

## Desfazer

Os arquivos originais estão em `_backup\<PC>-<data>\`; copie de volta para os caminhos de origem. Remova também a tarefa agendada:
```
schtasks /delete /tn "IA-Hub Sync" /f
```
