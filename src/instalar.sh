#!/usr/bin/env bash
set -euo pipefail
umask 077
HUB=$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd -P)
source "$HUB/scripts/bootstrap-linux.sh"
mode=auto
clients=1
ui=1
preview=0
for arg in "$@"; do
    case "$arg" in
        --headless) mode=headless ;;
        --desktop) mode=desktop ;;
        --memory-only) clients=0 ;;
        --cli) ui=0 ;;
        --ui) mode=desktop; ui=1 ;;
        --preview) mode=desktop; preview=1 ;;
        --help|-h) echo 'Uso: ./instalar.sh [--headless|--desktop] [--cli|--ui] [--preview] [--memory-only]'; exit 0 ;;
        *) echo "Argumento desconhecido: $arg" >&2; exit 1 ;;
    esac
done
[[ $(uname -s) = Linux ]] || { echo 'Este instalador requer Linux.' >&2; exit 1; }
[[ $(id -u) != 0 ]] || { echo 'Execute como usuário normal, sem sudo. Dependências de sistema podem solicitar sudo separadamente.' >&2; exit 1; }
case $(uname -m) in x86_64|aarch64|arm64) ;; *) echo 'Arquitetura sem runtime semântico validado; requer x64 ou ARM64.' >&2; exit 1 ;; esac
libc=$(getconf GNU_LIBC_VERSION 2>/dev/null) || { echo 'A memória semântica requer Linux glibc. Alpine/musl ainda não é suportado.' >&2; exit 1; }
if [[ ! $libc =~ ([0-9]+)\.([0-9]+) ]] || (( BASH_REMATCH[1] < 2 || (BASH_REMATCH[1] == 2 && BASH_REMATCH[2] < 28) )); then
    echo 'Este runtime requer glibc 2.28 ou superior.' >&2; exit 1
fi
[[ $mode != auto ]] || mode=$(hub_detect_mode)
echo "IA-Hub: modo $mode, pasta $HUB"
hub_require_base
mkdir -p "$HUB/.tools/uv" "$HUB/contexto/.memory" "$HOME/.local/bin"
export PATH="$HOME/.local/bin:$HOME/.opencode/bin:$HUB/.tools/uv:$PATH"
hub_clean_wsl_path
if ! hub_native_command uv >/dev/null; then
    curl --fail --location --retry 2 https://astral.sh/uv/0.11.24/install.sh -o "$HUB/.tools/uv/install.sh"
    UV_INSTALL_DIR="$HUB/.tools/uv" UV_NO_MODIFY_PATH=1 sh "$HUB/.tools/uv/install.sh"
fi
uv=$(hub_native_command uv)
runtime="$HUB/.memory-runtime/bin/python"
environment="$HUB/.memory-runtime"
if [[ $mode = desktop && $ui = 1 && $clients = 1 ]]; then environment="$HUB/.setup-runtime"; fi
runtime="$environment/bin/python"
if [[ ! -x $runtime ]]; then "$uv" venv --python 3.11 "$environment"; fi
if [[ $environment = "$HUB/.setup-runtime" ]]; then
    export IA_HUB_INSTALL_MODE="$mode"
    options=()
    [[ $preview = 0 ]] || options+=(--preview)
    exec "$runtime" "$HUB/scripts/setup_ui/server.py" --root "$HUB" "${options[@]}"
fi
hub_event runtime running
"$uv" pip install --python "$runtime" -r "$HUB/scripts/memory/requirements.lock"
hub_event runtime done
entry="$HUB/scripts/memory/entry.py"
"$runtime" "$entry" preflight
: > "$HUB/contexto/bootstrap-linux.tsv"
if [[ $clients = 1 ]]; then
    hub_event clients running
    backup="$HUB/contexto/.memory/backups/bootstrap-$(date +%Y%m%d-%H%M%S)-$$"
    mkdir -p "$backup"
    for profile in .profile .bashrc .bash_profile .zshrc; do [[ ! -f $HOME/$profile ]] || cp -p -- "$HOME/$profile" "$backup/$profile"; done
    hub_record_cli claude https://claude.ai/install.sh
    hub_record_cli codex https://chatgpt.com/codex/install.sh
    hub_record_cli agy https://antigravity.google/cli/install.sh
    hub_record_cli opencode https://opencode.ai/install
else
    printf 'Clientes\tskipped\t--memory-only\n' >> "$HUB/contexto/bootstrap-linux.tsv"
fi
export IA_HUB_INSTALL_MODE="$mode"
if [[ $clients = 0 ]]; then export IA_HUB_INSTALL_MODE=headless; fi
if [[ -n ${IA_HUB_COMPONENTS:-} && ,$IA_HUB_COMPONENTS, != *,desktop,* ]]; then export IA_HUB_INSTALL_MODE=headless; fi
"$runtime" "$entry" linux-apps
hub_event clients done
hub_event config running
hub_event memory running
"$runtime" "$entry" install
hub_event config done
hub_event memory done
hub_event validate running
"$runtime" "$entry" doctor
hub_event validate done
"$runtime" "$entry" linux-summary
