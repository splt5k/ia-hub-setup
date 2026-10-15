# Instaladores portáteis

Para distribuir o IA-Hub, bastam os dois arquivos gerados: `instalar.cmd` no Windows e `instalar.sh` no Linux. Cada arquivo contém os scripts, configurações padrão e interface completos. Não precisa de git nem do restante do repositório para executar. A instalação ainda requer internet para baixar os runtimes, clientes e modelo; logins continuam pessoais.

Geração a partir do código-fonte:

```sh
python scripts/build-portable.py
```

Os arquivos ficam em `dist/`. Esse comando deve ser repetido ao publicar alterações; os arquivos da raiz do repositório continuam sendo as entradas de desenvolvimento. O pacote não inclui banco, histórico, credenciais, ambiente Python, modelos baixados nem notas pessoais. SHA256 verifica a integridade da extração; não é uma assinatura digital do distribuidor.

## Execução

Windows: abrir `instalar.cmd`. Linux: `chmod +x instalar.sh && ./instalar.sh`. Com sessão gráfica abre a interface; sem sessão gráfica, SSH ou WSL, usa o terminal. `--cli` força terminal, `--preview` abre somente leitura e `--self-test` verifica a extração sem instalar dependências. No Linux também aceita `--headless`, `--desktop` e `--memory-only`.

O instalador identifica a pasta de uma integração existente e a reutiliza. Sem instalação anterior, o destino é `%LOCALAPPDATA%\IA-Hub` no Windows e `${XDG_DATA_HOME:-~/.local/share}/ia-hub` no Linux. `IA_HUB_INSTALL_DIR` permite indicar outro destino definitivo; uma instalação ativa em outro lugar bloqueia mudanças conflitantes.

Somente Instalar, Reparar ou Reinstalar copiam o código ao destino. Verificar e a prévia não atualizam a instalação. Código substituído recebe backup; regras pessoais, notas, banco e histórico são preservados. Remover desconecta a integração e preserva os dados e aplicativos.

## O que fica no computador

- **Permanente:** código do serviço, memória, notas, histórico, configurações, backups de segurança, modelo semântico e Python necessário ao serviço, além dos clientes instalados. O Python base fica em `.tools/python`, fora da extração temporária.
- **Temporário:** extração do pacote, uv e Python da interface, instaladores baixados e cache usado pelo instalador. Cada execução possui uma pasta exclusiva; os temporários são removidos na saída normal, inclusive em falhas tratadas.

Use **Encerrar painel** quando terminar: fecha o servidor da interface e permite a limpeza. Fechar somente a aba mantém o painel disponível até o limite de inatividade de 30 minutos. A memória continua independente. Interrupção forçada do processo ou queda de energia podem deixar a pasta temporária daquela execução; falhas de limpeza são informadas. Caches mantidos pelos próprios aplicativos e pelo sistema não são apagados.

O pacote instala o sistema em outra máquina; não transfere automaticamente a memória privada da máquina anterior. Restaurar dados ou sincronizar computadores exige tratar essa base separadamente.
