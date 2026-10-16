# IA-Hub no Linux

```bash
git clone https://github.com/splt5k/ia-hub-setup.git
cd ia-hub-setup
./instalar.sh
```

Execute como usuário normal, na pasta definitiva. Bash, internet, x64/ARM64 e glibc 2.28+ são necessários; os pacotes Python também precisam ter wheels compatíveis com a plataforma. Alpine/musl e outras arquiteturas ainda não são suportados pelo runtime semântico. Não é uma promessa de compatibilidade com toda distribuição Linux.

O bootstrap tenta instalar curl, certificados, tar e unzip pelo gerenciador encontrado (apt, dnf, yum, pacman ou zypper) somente se faltarem ferramentas. Essa etapa e os pacotes gráficos de sistema podem solicitar sudo. Não execute o instalador inteiro com sudo. O serviço, dados, configurações e runtime pertencem ao usuário; Python global e Node não são necessários para os instaladores nativos.

## Detecção e resultados

| Ambiente | Resultado automático |
|---|---|
| Sessão Wayland com socket ou X11 acessível | Quatro CLIs, memória e tentativa dos apps Linux compatíveis |
| Servidor sem display, SSH ou WSL | Quatro CLIs e memória; nenhum pacote gráfico |
| `--headless` | Força somente CLIs e memória |
| `--desktop` | Solicita apps mesmo se a sessão não for detectada; não abre janelas |
| `--memory-only` | Prepara memória e configurações; não instala clientes nem apps |

WSLg pode exportar DISPLAY mesmo em um terminal usado como servidor. Por isso WSL e SSH usam headless por padrão. Para instalar os apps Linux deliberadamente, use `./instalar.sh --desktop`. O instalador remove do PATH do processo os wrappers Windows herdados pelo WSL, para que o instalador oficial de um CLI não confunda os dois sistemas.

Os scripts oficiais instalam Claude Code, Codex CLI, Antigravity CLI e OpenCode. Clientes nativos existentes são preservados. OpenCode novo usa 1.18.33; uv novo usa 0.11.24 e fica em `.tools/uv/`. O Python 3.11 e as dependências fixadas ficam em `.memory-runtime/`.

Com interface gráfica:

| App | Instalação |
|---|---|
| Obsidian | Tarball oficial 1.14.4 com SHA256, launcher do usuário abre o cofre do clone |
| Antigravity App | Tarball oficial 2.23.1, launcher `antigravity-app` do usuário; preserva o comando `antigravity` do IDE |
| Claude Desktop | Pacote oficial em Ubuntu 22.04+/Debian 12+; requer sudo e dependências da distro |
| ChatGPT/Codex App | DEB em Ubuntu 24.04/26.04 e Debian 13; RPM em Fedora 43/44; requer sudo |

Em outras distribuições, os CLIs continuam disponíveis quando o runtime for compatível. Apps sem método automatizado ficam pendentes no relatório; não são substituídos por wrappers não oficiais. O método Arch do ChatGPT App não está automatizado nesta versão. Tarballs evitam FUSE, mas precisam de bibliotecas gráficas e sandbox funcional. O instalador não acrescenta `--no-sandbox`, não configura KVM/grupos e não abre os apps automaticamente.

## Memória e inicialização

O MCP, banco, histórico, busca semântica, captura suportada e notas `Memoria/` usam o mesmo núcleo do Windows. Não é preciso instalar Obsidian num servidor para manter o banco e as projeções funcionando. Não há sincronização automática de bancos entre computadores; dados privados não vêm pelo Git.

MCPs, hooks e plugin são registrados nos CLIs. As instruções globais recebem um bloco gerenciado com caminhos Linux, preservando texto externo e cópias de segurança. OpenCode respeita XDG_CONFIG_HOME/XDG_DATA_HOME. O caminho do Python do venv é preservado: resolver seu symlink faria os MCPs perderem as dependências.

Quando `systemctl --user` funciona, a unit `ia-hub-memory.service` inicia a memória e sincroniza regras no login do usuário. A ativação confere a propriedade do processo; um daemon avulso só é encerrado na transição se PID, usuário, pasta e comando corresponderem a esta instalação. Não habilita linger nem promete serviço antes do login. Sem systemd, há inicialização em `.profile` (também em `.bash_profile`/`.zprofile` existentes), autostart XDG e início sob demanda pelo cliente MCP.

Uma porta 43127 ocupada por outra instalação bloqueia a configuração. Não use o mesmo runtime entre Windows e WSL: mantenha clones e diretórios de dados separados, sem ativar dois escritores sobre o mesmo banco.

## Diagnóstico e limites

```bash
./.memory-runtime/bin/python scripts/memory/entry.py doctor
# Quando usa systemd:
systemctl --user status ia-hub-memory.service
journalctl --user -u ia-hub-memory.service
```

O instalador só conclui com memória pronta após testar gravação, leitura, recuperação por paráfrase e integridade das projeções. O registro sintético não aparece no grafo principal. Relatórios privados: `contexto/bootstrap.json`, `contexto/.memory/installation.json` e `contexto/.memory/doctor.json`. Saída 2 significa componentes pendentes/falhos, mesmo que a memória esteja funcional; saída 1 indica erro que interrompeu o processo. Reexecute após corrigir a causa.

Autenticação, assinaturas, consentimentos e confiança de workspace continuam sob controle do usuário. Os testes do serviço e MCP não autenticam agentes. Na aba Code, Claude Desktop compartilha configurações do Claude Code; o caminho MCP do Chat Desktop Linux não foi confirmado pela documentação, portanto não é inventado pelo instalador. Instalar o ChatGPT/Codex App não comprova acesso do Chat convencional à memória. Captura nos apps gráficos não é considerada validada.

Validação desta implementação: instalação headless real no Ubuntu WSL, com HOME e XDG isolados, quatro CLIs nativos e modelo semântico; troca MCP Claude → Codex → Claude usando as configurações geradas. Sem login de provedores nesse perfil. Abertura dos apps, instalação privilegiada dos DEB/RPM, ARM64 e outras distros não foram exercitados. Os testes automatizados cobrem a seleção desktop/headless, preservação, paths XDG, venv e ciclo de inicialização.

Fontes oficiais: [Claude Code](https://code.claude.com/docs/en/setup), [Codex CLI](https://github.com/openai/codex), [Antigravity CLI](https://antigravity.google/docs/cli/install/), [OpenCode](https://opencode.ai/docs/), [Obsidian](https://obsidian.md/download), [Antigravity App](https://antigravity.google/download), [Claude Desktop Linux](https://code.claude.com/docs/en/desktop-linux), [ChatGPT/Codex App Linux](https://learn.chatgpt.com/docs/linux/linux-app).
