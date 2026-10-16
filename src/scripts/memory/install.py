"""Integração aditiva, com backups e permissões limitadas às operações da memória."""
import json
import os
import shlex
import re
import shutil
import subprocess
import sys
import time
from datetime import datetime
from pathlib import Path
from .client import ROOT, STATE, request

WINDOWS = sys.platform == 'win32'


def strip_json_comments(text):
    # URLs e comentários dentro de strings permanecem intactos.
    text = re.sub(r'("(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/)', lambda m: m[0] if m[0].startswith('"') else '', text)
    return re.sub(r'("(?:\\.|[^"\\])*"|,\s*(?=[}\]]))', lambda m: m[0] if m[0].startswith('"') else '', text)


def main():
    home = Path.home()
    STATE.mkdir(parents=True, exist_ok=True)
    stamp = datetime.now().strftime('%Y%m%d-%H%M%S-%f')
    backups = STATE / 'backups' / stamp
    # Linux venv executables are symlinks: resolving them loses site-packages.
    python = os.path.abspath(sys.executable)
    entry = str(Path(__file__).with_name('entry.py').resolve())
    changed = []

    def save(path, text):
        path = Path(path)
        if path.exists() and path.read_text(encoding='utf-8-sig') == text:
            return
        if path.exists():
            target = backups / re.sub(r'[:\\/]', '_', str(path))
            target.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, target)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
        changed.append(str(path))

    def update_json(path, apply):
        path = Path(path)
        obj = json.loads(strip_json_comments(path.read_text(encoding='utf-8-sig'))) if path.exists() else {}
        apply(obj)
        save(path, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')

    def server(client):
        return {'command': python, 'args': [entry, 'mcp', client]}

    if not WINDOWS:
        from .linux import sync_rules, config_home
        sync_rules(ROOT, home, save)
    shell_command = subprocess.list2cmdline if WINDOWS else shlex.join

    update_json(home / '.claude.json', lambda obj: obj.setdefault('mcpServers', {}).update(ia_hub=server('claude-code')))
    from .mods import install_mod
    native_mod = install_mod(ROOT, home, python, entry, save, backups)

    def hooks(obj):
        groups = obj.setdefault('hooks', {})
        for event in ['SessionStart', 'UserPromptSubmit', 'Stop']:
            command = shell_command([python, entry, 'hook', 'claude'])
            group = {'hooks': [{'type': 'command', 'command': command, 'timeout': 30}]}
            existing = groups.setdefault(event, [])
            retained = []
            for current in existing:
                handlers = [h for h in current.get('hooks', []) if 'memory/entry.py' not in h.get('command', '').replace('\\', '/')]
                if handlers:
                    retained.append({**current, 'hooks': handlers})
            existing[:] = retained
            if event == 'UserPromptSubmit' and native_mod['installed']:
                continue  # O mod já recupera por prompt; evita contexto duplicado.
            existing.append(group)
    update_json(home / '.claude' / 'settings.json', hooks)

    codex = home / '.codex' / 'config.toml'
    text = codex.read_text(encoding='utf-8-sig') if codex.exists() else ''
    marker = '# BEGIN IA-HUB MEMORY'
    text = re.sub(r'\n?# BEGIN IA-HUB MEMORY[\s\S]*?# END IA-HUB MEMORY\n?', '', text)
    if re.search(r'^\[mcp_servers\.ia_hub\]', text, re.M):
        raise RuntimeError('MCP ia_hub existente fora do bloco gerenciado; preservar e revisar antes de alterar.')
    block = f'\n{marker}\n[mcp_servers.ia_hub]\ncommand = {json.dumps(python)}\nargs = {json.dumps([entry, "mcp", "codex"])}\nstartup_timeout_sec = 30\ntool_timeout_sec = 90\n# END IA-HUB MEMORY\n'
    # Autorização restrita às seis operações locais solicitadas pelo usuário;
    # não modifica approval_policy, shell, outros MCPs ou confiança de hooks.
    permissions = ''.join(f'\n[mcp_servers.ia_hub.tools.{tool}]\napproval_mode = "approve"\n' for tool in ['memory_store', 'memory_search', 'memory_get', 'memory_context', 'memory_relate', 'memory_health'])
    block = block.replace('# END IA-HUB MEMORY', permissions + '# END IA-HUB MEMORY')
    save(codex, text.rstrip() + '\n' + block)
    from .profiles import configure_profiles
    profiles = configure_profiles(home, save)

    agy = home / '.gemini' / 'config' / 'mcp_config.json'
    update_json(agy, lambda obj: obj.setdefault('mcpServers', {}).update(ia_hub=server('antigravity')))
    agy_hooks = agy.with_name('hooks.json')
    def configure_agy_hooks(obj):
        obj['ia-hub-memory'] = {
            event: [{'type': 'command', 'command': shell_command([python, entry, 'hook', f'antigravity-{mode}']), 'timeout': 15}]
            for event, mode in [('SessionStart', 'context'), ('PreInvocation', 'context'), ('Stop', 'capture')]
        }
    update_json(agy_hooks, configure_agy_hooks)
    agy_settings = home / '.gemini' / 'antigravity-cli' / 'settings.json'
    def scoped_memory_permissions(obj):
        allowed = obj.setdefault('permissions', {}).setdefault('allow', [])
        for tool in ['memory_context', 'memory_search', 'memory_get', 'memory_store', 'memory_relate', 'memory_health']:
            grant = 'mcp(ia_hub/' + tool + ')'
            if grant not in allowed:
                allowed.append(grant)
    update_json(agy_settings, scoped_memory_permissions)
    if WINDOWS:
        desktops = [home / 'AppData' / 'Roaming' / 'Claude' / 'claude_desktop_config.json']
        desktops += [p / 'LocalCache/Roaming/Claude/claude_desktop_config.json' for p in (home / 'AppData' / 'Local' / 'Packages').glob('Claude_*')]
        # Antes do primeiro lançamento, o MSIX pode ainda não ter criado LocalCache.
        packages = subprocess.run(['powershell.exe', '-NoProfile', '-Command', 'Get-AppxPackage -Name Claude -ErrorAction Stop | Select-Object -ExpandProperty PackageFamilyName'], capture_output=True, text=True)
        if packages.returncode == 0:
            desktops += [home / 'AppData/Local/Packages' / name / 'LocalCache/Roaming/Claude/claude_desktop_config.json'
                         for name in getattr(packages, 'stdout', '').splitlines() if re.fullmatch(r'Claude_[A-Za-z0-9]+', name)]
        for desktop in dict.fromkeys(desktops):
            update_json(desktop, lambda obj: obj.setdefault('mcpServers', {}).update(ia_hub=server('claude-desktop')))

    opencode_dir = (home / '.config' if WINDOWS else config_home(home)) / 'opencode'
    if not WINDOWS and not any((opencode_dir / f).exists() for f in ['opencode.json', 'opencode.jsonc']):
        template = (ROOT / 'opencode/opencode.jsonc').read_text(encoding='utf-8-sig')
        obj = json.loads(strip_json_comments(template))
        obj['instructions'] = [str(opencode_dir / 'ia-hub.md')]
        save(opencode_dir / 'opencode.jsonc', json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    opencode_configs = [p for p in [opencode_dir / 'opencode.json', opencode_dir / 'opencode.jsonc'] if p.exists()]
    if not opencode_configs and opencode_dir.exists():
        opencode_configs = [opencode_dir / 'opencode.json']
    from .opencode_cleanup import clean_config, clean_files
    legacy_removed = []

    def backup_file(path):
        target = backups / re.sub(r'[:\\/]', '_', str(path))
        target.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, target)
    if opencode_dir.exists():
        legacy_removed.extend(clean_files(opencode_dir, backup_file))
    for opencode in opencode_configs:
        def configure_opencode(obj):
            obj.setdefault('mcp', {}).update(ia_hub={'type': 'local', 'command': [python, entry, 'mcp', 'opencode'], 'enabled': True, 'timeout': 30000})
            legacy_removed.extend(clean_config(obj))
            instructions = obj.setdefault('instructions', [])
            hub_instruction = str(opencode_dir / 'ia-hub.md').replace('\\', '/')
            if hub_instruction not in instructions:
                instructions.append(hub_instruction)
        update_json(opencode, configure_opencode)
    if opencode_configs:
        plugin = Path(__file__).with_name('opencode-plugin.js').read_text(encoding='utf-8').replace('__PYTHON__', json.dumps(python)).replace('__ENTRY__', json.dumps(entry))
        save(opencode_dir / 'plugins' / 'ia-hub-memory.js', plugin)

    if WINDOWS:
        # Tarefa por usuário, sem elevação, sem modificar confiança de hooks.
        pythonw = str(Path(python).with_name('pythonw.exe'))
        script = ROOT / 'scripts' / 'memory-start.ps1'
        save(script, f"$ErrorActionPreference = 'Stop'\nStart-Process -FilePath '{pythonw.replace(chr(39), chr(39)*2)}' -ArgumentList @('\"{entry}\"', 'health') -WindowStyle Hidden\n")
        # health autoinicia o serviço; a tarefa não precisa manter um terminal aberto.
        task_arguments = ('-NoProfile -WindowStyle Hidden -ExecutionPolicy Bypass -File "' + str(script) + '"').replace("'", "''")
        ps = "$a=New-ScheduledTaskAction -Execute 'powershell.exe' -Argument '" + task_arguments + "'; $t=New-ScheduledTaskTrigger -AtLogOn; $s=New-ScheduledTaskSettingsSet -AllowStartIfOnBatteries -DontStopIfGoingOnBatteries -StartWhenAvailable; Register-ScheduledTask -TaskName 'IA-Hub Memory' -Action $a -Trigger $t -Settings $s -Description 'Memória local compartilhada IA-Hub' -Force | Out-Null"
        registered = subprocess.run(['powershell.exe', '-NoProfile', '-Command', ps], capture_output=True, text=True)
        if registered.returncode:
            raise RuntimeError('Falha ao registrar tarefa IA-Hub Memory: ' + registered.stderr[:200])
        startup = 'windows-task'
    else:
        from .linux import setup_startup
        startup = setup_startup(ROOT, home, python, entry, save)
    if not WINDOWS and startup == 'systemd-user':
        for attempt in range(50):
            try:
                health = request('health', autostart=False)
                owner = subprocess.run(['systemctl', '--user', 'show', 'ia-hub-memory.service', '--property=MainPID', '--value'], capture_output=True, text=True, timeout=10)
                if owner.returncode or owner.stdout.strip() != str(health.get('pid')):
                    raise RuntimeError('Daemon não está sob controle da unit systemd esperada.')
                break
            except OSError:
                if attempt == 49:
                    raise RuntimeError('Serviço systemd não iniciou. Consulte journalctl --user -u ia-hub-memory.')
                time.sleep(.2)
    else:
        health = request('health')
    report = {'startup': startup, 'codex_profiles': profiles, 'claude_mod': native_mod, 'platform': 'windows' if WINDOWS else 'linux', 'changed': changed, 'opencode_legacy_removed': legacy_removed, 'opencode_scope': 'memory-only', 'backup': str(backups), 'health': health, 'requires_restart': ['claude-desktop', 'antigravity-app', 'codex-app-existing-sessions', 'opencode-existing-sessions'], 'chatgpt_conventional': 'Sem ponte disponível confirmada; configuração local do Codex não configura o ChatGPT convencional.'}
    (STATE / 'installation.json').write_text(json.dumps(report, ensure_ascii=False, indent=2), encoding='utf-8')
    print(json.dumps(report, ensure_ascii=False, indent=2))
