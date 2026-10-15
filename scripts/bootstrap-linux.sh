#!/usr/bin/env bash
# Functions only; no mutation when sourced by tests.
hub_is_wsl() { grep -qi microsoft /proc/sys/kernel/osrelease 2>/dev/null; }

hub_event() {
    if [[ ${IA_HUB_UI_WORKER:-} = 1 ]]; then printf 'IA_HUB_EVENT:{"phase":"%s","status":"%s"}\n' "$1" "$2"; fi
    return 0
}

hub_detect_mode() {
    if [[ -n ${SSH_CONNECTION:-}${SSH_TTY:-} ]] || hub_is_wsl; then
        printf 'headless\n'; return
    fi
    local socket=${WAYLAND_DISPLAY:-}
    [[ $socket = /* ]] || socket=${XDG_RUNTIME_DIR:-/nonexistent}/$socket
    if [[ -n ${WAYLAND_DISPLAY:-} && -S $socket ]]; then
        printf 'desktop\n'; return
    fi
    if [[ -n ${DISPLAY:-} ]] && command -v xdpyinfo >/dev/null && xdpyinfo -display "$DISPLAY" >/dev/null 2>&1; then
        printf 'desktop\n'; return
    fi
    if [[ ${DISPLAY:-} =~ ^:([0-9]+)(\.[0-9]+)?$ ]] && [[ -S /tmp/.X11-unix/X${BASH_REMATCH[1]} ]]; then
        printf 'desktop\n'; return
    fi
    printf 'headless\n'
}

hub_require_base() {
    local missing=0
    for name in curl tar unzip; do command -v "$name" >/dev/null || missing=1; done
    [[ $missing = 1 ]] || return 0
    local elevate=()
    if [[ $(id -u) != 0 ]]; then
        command -v sudo >/dev/null || { echo 'Faltam curl/tar/unzip; instale-os com o administrador.' >&2; return 1; }
        elevate=(sudo)
    fi
    if command -v apt-get >/dev/null; then
        "${elevate[@]}" apt-get update && "${elevate[@]}" apt-get install -y curl ca-certificates tar unzip
    elif command -v dnf >/dev/null; then "${elevate[@]}" dnf install -y curl ca-certificates tar unzip
    elif command -v yum >/dev/null; then "${elevate[@]}" yum install -y curl ca-certificates tar unzip
    elif command -v pacman >/dev/null; then "${elevate[@]}" pacman -S --needed --noconfirm curl ca-certificates tar unzip
    elif command -v zypper >/dev/null; then "${elevate[@]}" zypper --non-interactive install curl ca-certificates tar unzip
    else echo 'Gerenciador não reconhecido. Instale curl, certificados CA, tar e unzip e repita.' >&2; return 1
    fi
}

hub_native_command() {
    local path
    path=$(command -v "$1") || return 1
    # WSL may inherit Windows npm wrappers; those do not constitute Linux clients.
    if hub_is_wsl && [[ $path =~ ^/mnt/[a-zA-Z]/ || $path = *.exe ]]; then return 1; fi
    printf '%s\n' "$path"
}

hub_clean_wsl_path() {
    hub_is_wsl || return 0
    local item clean= parts
    IFS=: read -ra parts <<< "$PATH"
    for item in "${parts[@]}"; do
        if [[ $item =~ ^/mnt/[a-zA-Z]/ && $item != "$HUB/.tools/uv" ]]; then continue; fi
        clean+="${clean:+:}$item"
    done
    export PATH="$clean"
}

hub_install_script() {
    local name=$1 url=$2 file="${IA_HUB_WORK_DIR:-$HUB/.tools}/$1-install.sh"
    curl --fail --location --retry 2 "$url" -o "$file" || return 1
    case "$name" in
        opencode) bash "$file" --version 1.18.33 --no-modify-path ;;
        codex) CODEX_NON_INTERACTIVE=true CODEX_INSTALL_DIR="$HOME/.local/bin" sh "$file" ;;
        *) bash "$file" ;;
    esac
}

hub_cli() {
    if [[ ,${IA_HUB_FORCE_COMPONENTS:-}, != *,"$1",* ]] && hub_native_command "$1" >/dev/null; then return 0; fi
    hub_install_script "$1" "$2" || return 1
    hash -r
    hub_native_command "$1" >/dev/null
}

hub_record_cli() {
    local state=installed
    if [[ -n ${IA_HUB_COMPONENTS:-} && ,$IA_HUB_COMPONENTS, != *,"$1",* ]]; then
        printf '%s\tskipped\tFora dos componentes selecionados\n' "$1" >> "$HUB/contexto/bootstrap-linux.tsv"
        return 0
    fi
    hub_native_command "$1" >/dev/null && state=present
    if hub_cli "$1" "$2"; then
        printf '%s\t%s\t%s\n' "$1" "$state" 'Login ainda pode ser necessário' >> "$HUB/contexto/bootstrap-linux.tsv"
    else
        printf '%s\tfailed\tInstalador ou executável indisponível\n' "$1" >> "$HUB/contexto/bootstrap-linux.tsv"
    fi
}
