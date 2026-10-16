#!/usr/bin/env bash
set -euo pipefail
umask 077
for arg in "$@"; do
    case "$arg" in
        --help|-h) echo 'Uso: ./instalar.sh [--cli|--ui] [--preview] [--headless|--desktop] [--memory-only] [--self-test]'; exit 0 ;;
        --cli|--ui|--preview|--headless|--desktop|--memory-only|--self-test) ;;
        *) echo "Argumento desconhecido: $arg" >&2; exit 1 ;;
    esac
done
[[ $(uname -s) = Linux ]] || { echo 'Este instalador requer Linux.' >&2; exit 1; }
[[ $(id -u) != 0 || ${1:-} = --self-test ]] || { echo 'Execute como usuário normal, sem sudo.' >&2; exit 1; }
case $(uname -m) in x86_64|aarch64|arm64) ;; *) echo 'Arquitetura não suportada.' >&2; exit 1 ;; esac
for tool in mktemp base64 sha256sum tar awk; do
    command -v "$tool" >/dev/null || { echo "Falta a ferramenta básica: $tool" >&2; exit 1; }
done
work=$(mktemp -d "${TMPDIR:-/tmp}/ia-hub-setup.XXXXXXXX")
work=$(cd -- "$work" && pwd -P)
cleanup() {
    # Only this run's mktemp directory, never the installed brain or a user cache.
    if [[ -n $work && ${work##*/} = ia-hub-setup.* && -d $work && ! -L $work ]]; then
        rm -rf -- "$work"
    fi
}
trap cleanup EXIT
trap 'exit 130' INT
trap 'exit 143' TERM HUP
awk 'found {print} /^__IA_HUB_PAYLOAD__$/ {found=1}' "$0" | base64 --decode > "$work/payload.tar.gz"
printf '%s  %s\n' '{{SHA256}}' "$work/payload.tar.gz" | sha256sum --check --status || { echo 'Pacote corrompido (SHA256).' >&2; exit 1; }
mkdir "$work/app"
tar -xzf "$work/payload.tar.gz" -C "$work/app"
[[ -f $work/app/scripts/setup_ui/web/index.html && -f $work/app/scripts/memory/entry.py && -f $work/app/payload-manifest.json ]]
if [[ ${1:-} = --self-test ]]; then echo 'Pacote íntegro. Extração e limpeza temporárias verificadas.'; exit 0; fi
mkdir "$work/tmp"
export TMPDIR="$work/tmp"
HUB="$work/app"
source "$HUB/scripts/bootstrap-linux.sh"
hub_require_base
hub_clean_wsl_path
export IA_HUB_INSTALL_MODE
IA_HUB_INSTALL_MODE=$(hub_detect_mode)
for arg in "$@"; do
    case "$arg" in --desktop|--ui|--preview) IA_HUB_INSTALL_MODE=desktop ;; --headless) IA_HUB_INSTALL_MODE=headless ;; esac
done
export UV_INSTALL_DIR="$work/uv" UV_NO_MODIFY_PATH=1
export UV_PYTHON_INSTALL_DIR="$work/python" UV_CACHE_DIR="$work/cache" UV_PYTHON_PREFERENCE=only-managed
echo 'Preparando o instalador temporário do IA-Hub...'
curl --fail --location --retry 2 https://astral.sh/uv/0.11.24/install.sh -o "$work/uv-install.sh"
sh "$work/uv-install.sh"
export PATH="$work/uv:$PATH"
"$work/uv/uv" run --no-project --python 3.11 -- python "$HUB/scripts/portable/entry.py" "$@"
exit $?
