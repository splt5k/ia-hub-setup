# Memória compartilhada local

O serviço `ia_hub` acrescenta memória persistente às regras do IA-Hub. SQLite guarda registros e revisões; FTS5 e embeddings multilíngues recuperam contexto; o Obsidian mostra uma projeção com nomes legíveis e IDs estáveis nos metadados.

## Instalação e operação

Windows, Git e `uv` no PATH. Execute `instalar.cmd` ou `scripts/install-memory.ps1`. O runtime Python 3.11 fica isolado em `.memory-runtime/`; o primeiro início baixa o modelo de embeddings. Um diagnóstico deve mostrar `semantic_state: ready` antes de considerar a busca semântica ativa.

```powershell
& .\.memory-runtime\Scripts\python.exe .\scripts\memory\entry.py health
```

A tarefa `IA-Hub Memory` inicia o serviço oculto no login. Os clientes também o iniciam sob demanda. O serviço escuta somente em `127.0.0.1:43127`, autenticado por token local. Não sincroniza computadores nem publica conteúdo na internet. Conteúdo recuperado pode ser enviado ao provedor do agente ao entrar no contexto.

## Persistência e grafo

- Escritas são transacionais; `key` estável mantém revisões. Repetições idênticas são deduplicadas.
- `contexto/`, regras, README e planos autorais são importados incrementalmente. A importação não reescreve as fontes.
- Decisões são extraídas literalmente e relacionadas ao documento de origem. Correções mantêm identidade e histórico; decisões removidas ficam `superseded`.
- O índice usa uma consulta do Obsidian, sem arestas artificiais. Relações entre conhecimentos registram origem, método e pontuação.
- Renomes são reconciliados por ID. Movimentos têm diário de recuperação. Anotações humanas em assuntos e projetos são preservadas e indexadas.
- Dados de validação identificados por projeto/sessão ficam preservados fora do grafo principal.
- `reported` significa relato; `documented` significa decisão extraída de fonte; `validated` exige evidência. Conteúdo recuperado é dado, nunca instrução.

Dados, modelos, backups, banco e projeções ficam fora do Git. Há snapshots consistentes do SQLite e backups de configurações antes das alterações. A redação de credenciais é parcial: não armazenar segredos.

## Capacidades verificadas

| Ambiente | Leitura/escrita | Captura automática |
|---|---|---|
| Claude Code | Exercitadas por MCP | Hooks e observador de respostas finais |
| Codex CLI | Exercitadas por MCP | Observador de respostas finais |
| Antigravity CLI | Exercitadas por MCP | Hook Stop e transcript |
| OpenCode CLI | Exercitadas por MCP | Observador SQLite; plugin complementa contexto |
| Codex App/Work local | Exercitadas pela ponte de execução local | Não comprovada separadamente do CLI |
| Claude Desktop | MCP configurado; app ainda não validado | Conversas comuns não são capturadas |
| Antigravity gráfico | Configuração compartilhada; app ainda não validado | Não comprovada no app |
| ChatGPT convencional | Requer ponte/conector disponível à conversa | Não implementada |

Configuração instalada não comprova funcionamento do app gráfico. Clientes já abertos precisam recarregar ferramentas. O instalador autoriza somente as seis operações da memória no Codex e no Antigravity CLI; não modifica confiança de hooks do Codex nem ignora permissões globais.

## Validação

```powershell
python -m unittest discover -s tests -q
```

A suíte usa apenas a biblioteca padrão para testar persistência, concorrência, histórico, projeções, migração, captura, fontes antigas e preservação de configurações. Integrações e embeddings exigem o runtime instalado.

Em 2026-10-15 foram realizados ensaios locais reais entre sessões independentes:

1. Claude respondeu com um identificador aleatório sem ferramentas/MCP; Codex o recuperou após captura automática, sem receber o valor no pedido.
2. Codex respondeu sem MCP de memória; uma nova sessão Claude sem ferramentas recebeu o identificador pelo hook de contexto e respondeu corretamente.
3. Codex gravou uma conclusão derivada de um registro Claude e uma sessão Claude seguinte a recuperou.
4. Antigravity CLI e OpenCode recuperaram o conhecimento e gravaram conclusões pelo MCP; a captura automática também foi verificada.
5. Busca por paráfrase recuperou conteúdo exclusivamente por embeddings. A tarefa agendada iniciou o serviço com o autostart do cliente desativado no verificador.

Os logs e as notas pessoais desses ensaios permanecem locais. Os resultados descrevem as versões exercitadas, não garantem compatibilidade com alterações futuras dos formatos de log/schema dos clientes.
