#!/usr/bin/env bash
# Validação real do instalar.sh em HOME descartável (sem systemd => ramo servidor/headless):
# instala, inspeciona as integrações, reinstala (idempotência) e confirma o daemon sem a extração.
# Uso: bash tools/validate-linux.sh [pasta-de-logs]   (Linux ou WSL; baixa os CLIs oficiais para o HOME descartável)
REPO=$(cd "$(dirname "$0")/.." && pwd); LOGS=${1:-/tmp/ia-hub-validate-logs}; mkdir -p "$LOGS"
set -u
REAL_HOME=$HOME
F=${IA_HUB_TEST_HOME:-$REAL_HOME/.ia-hub-cleantest}; rm -rf $F /tmp/shim; mkdir -p $F /tmp/shim
printf '#!/bin/sh\nexit 1\n' > /tmp/shim/systemctl; chmod +x /tmp/shim/systemctl
export HOME=$F PATH=/tmp/shim:/usr/local/bin:/usr/bin:/bin
unset XDG_CONFIG_HOME XDG_DATA_HOME XDG_RUNTIME_DIR
cd "$REPO"
snap() { (cd $F; find . -type f -not -path './.local/share/ia-hub/*' -not -path './.local/share/uv/*' -not -path './.cache/*' -not -path './.local/bin/*' -not -path './.claude/plugins/*' -print0 | sort -z | xargs -0 sha256sum | sha256sum | cut -c1-16); }
bash instalar.sh --headless --cli > $LOGS/run1.log 2>&1; echo "RUN1 EXIT=$?"
S1=$(snap); R=$F/.local/share/ia-hub
echo "TEMP restante: $(ls /tmp | grep -c 'ia-hub-setup\.')"
echo "--- config files"; (cd $F; find .config .claude .codex .gemini -maxdepth 3 -type f -not -path '.config/uv/*' 2>/dev/null | head -30; ls -a .claude.json 2>/dev/null)
echo "--- opencode"; cat $F/.config/opencode/opencode.json* 2>/dev/null; ls $F/.config/opencode $F/.config/opencode/plugins 2>/dev/null
echo "--- opencode rules"; head -4 $F/.config/opencode/ia-hub.md 2>/dev/null
echo "--- claude mcp"; python3 -c "import json;print(list(json.load(open('$F/.claude.json')).get('mcpServers',{})))" 2>&1
echo "--- codex ia_hub blocks: $(grep -c 'mcp_servers.ia_hub\]' $F/.codex/config.toml 2>&1)"
echo "--- claude hooks"; python3 -c "import json;d=json.load(open('$F/.claude/settings.json'));print({k:len(v) for k,v in d['hooks'].items()}, d.get('enabledPlugins'))" 2>&1
echo "--- installation"; python3 -c "import json;d=json.load(open('$R/contexto/.memory/installation.json'));print({k:d.get(k) for k in ('startup','claude_mod','opencode_scope','opencode_legacy_removed')})" 2>&1
bash instalar.sh --headless --cli > $LOGS/run2.log 2>&1; echo "RUN2 EXIT=$?"
S2=$(snap); echo "snapshot config run1=$S1 run2=$S2 $([ "$S1" = "$S2" ] && echo IDEMPOTENTE || echo DIFERENTE)"
echo "codex blocks apos run2: $(grep -c 'mcp_servers.ia_hub\]' $F/.codex/config.toml)  profile blocks: $(grep -c 'BEGIN IA-HUB' $F/.profile 2>/dev/null)"
echo "TEMP restante: $(ls /tmp | grep -c 'ia-hub-setup\.')"
echo "--- daemon apos apagar extracao"; $R/.memory-runtime/bin/python $R/scripts/memory/entry.py health | head -c 300
echo "port file: $(cat $R/contexto/.memory/port 2>&1)"; ls $R/contexto/.memory/ | head -3 >/dev/null
