# IA-Hub

Configura de uma vez **Claude Code, Codex, Antigravity e OpenCode** para gastar menos tokens e trabalhar melhor no Windows. As regras são as mesmas para todas as IAs, e elas compartilham uma memória de cada projeto entre si.

## Instalar

1. Instale o [Git](https://git-scm.com/download/win), se ainda não tiver.
2. Clone em qualquer pasta:
   ```
   git clone https://github.com/splt5k/ia-hub.git
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

Cada projeto ganha uma nota curta em `contexto\projetos\<nome-da-pasta>.md`, com estado atual, decisões, próximos passos e última sessão.
- A IA que termina uma tarefa atualiza a nota.
- A próxima IA, qualquer que seja, lê a nota antes de começar.

A pasta `contexto\` fica **só no seu PC**: não vai para o git e não é compartilhada com ninguém. Se quiser, preencha `contexto\perfil.md` para as IAs te conhecerem.

## Personalizar

- Edite os arquivos em `regras/` e dê dois cliques em **`sincronizar.cmd`** para aplicar na hora.
- `regras/nucleo.md` vale para todas as IAs; `claude.md`, `codex.md` e `antigravity.md` são os ajustes de cada uma.
- O Obsidian (opcional) abre esta pasta como cofre para você ver as notas. Ele não precisa ficar aberto.

## Desfazer

Os arquivos originais estão em `_backup\<PC>-<data>\`; copie de volta para os caminhos de origem. Remova também a tarefa agendada:
```
schtasks /delete /tn "IA-Hub Sync" /f
```
