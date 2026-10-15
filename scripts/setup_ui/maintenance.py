import json
import os
import re
import shutil
import subprocess
import time
from datetime import datetime
from pathlib import Path
from .diagnostics import configs, entry_owned, json_file, rpc


def stop_legacy(root):
    entry = str(root / 'scripts/memory/entry.py')
    if os.name == 'nt':
        import base64
        escaped = entry.replace("'", "''")
        script = "$ErrorActionPreference='Stop'; $entry='" + escaped + "'; $pattern=[regex]::Escape($entry)+'\"?\\s+daemon(?:\\s|$)'; $found=0; Get-CimInstance Win32_Process | Where-Object { $_.Name -in @('python.exe','pythonw.exe') -and $_.CommandLine -match $pattern } | ForEach-Object { $owner=Invoke-CimMethod -InputObject $_ -MethodName GetOwner; if($owner.User -eq $env:USERNAME -and $owner.Domain -eq $env:USERDOMAIN) { $null=Invoke-CimMethod -InputObject $_ -MethodName Terminate; $found++ } }; if($found -eq 0) { throw 'Nenhum daemon legado verificado foi encontrado.' }"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Não foi possível identificar o daemon legado com segurança: ' + result.stderr[:180])
    else:
        import signal
        found = False
        for proc in Path('/proc').iterdir():
            if not proc.name.isdigit():
                continue
            try:
                args = (proc / 'cmdline').read_bytes().decode().split('\0')
                if entry in args and args[args.index(entry) + 1] == 'daemon' and proc.stat().st_uid == os.getuid():
                    os.kill(int(proc.name), signal.SIGTERM)
                    found = True
            except (OSError, UnicodeDecodeError, IndexError):
                continue
        if not found:
            raise RuntimeError('Nenhum daemon legado verificado foi encontrado; processos preservados.')


def stop_memory(root, log):
    try:
        rpc(root)
    except FileNotFoundError:
        return
    except ConnectionError:
        return
    except OSError as error:
        import urllib.error
        if isinstance(error, urllib.error.HTTPError):
            raise RuntimeError('Serviço existente não pertence a esta instalação; preservado.') from error
        return
    try:
        rpc(root, 'shutdown')
    except RuntimeError as error:
        if 'desconhecida' not in str(error).casefold() and 'unknown' not in str(error).casefold():
            raise
        log('info', 'Serviço legado: encerrando somente o daemon verificado desta pasta e deste usuário.')
        stop_legacy(root)
    for _ in range(50):
        try:
            rpc(root)
        except OSError:
            log('info', 'Serviço pausado com dados preservados.')
            return
        time.sleep(.1)
    raise RuntimeError('Serviço não encerrou; operação interrompida antes de alterar dados.')


def backup_runtime(root, log):
    stop_memory(root, log)
    runtime = root / '.memory-runtime'
    if runtime.is_symlink():
        raise RuntimeError('Runtime externo via symlink: reinstalação automática bloqueada.')
    if runtime.exists():
        backup = root / 'contexto/.memory/backups' / ('runtime-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
        backup.parent.mkdir(parents=True, exist_ok=True)
        runtime.rename(backup)
        log('info', 'Runtime anterior preservado em ' + str(backup))


def remove_configs(root, home, windows=None):
    windows = os.name == 'nt' if windows is None else windows
    backup = root / 'contexto/.memory/backups' / ('removal-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    changed = []
    def save(path, content=None):
        if not path.exists():
            return
        if content is not None and path.read_text(encoding='utf-8-sig') == content:
            return
        backup.mkdir(parents=True, exist_ok=True)
        shutil.copy2(path, backup / re.sub(r'[:\\/]', '_', str(path)))
        if content is None:
            path.unlink()
        else:
            path.write_text(content, encoding='utf-8')
        changed.append(str(path))
    def json_edit(path, edit):
        if path.exists():
            obj = json_file(path)
            before = json.dumps(obj, sort_keys=True)
            edit(obj)
            if before != json.dumps(obj, sort_keys=True):
                save(path, json.dumps(obj, ensure_ascii=False, indent=2) + '\n')
    owned_agy = False
    for key, path in configs(home).items():
        if key == 'codex':
            if path.exists():
                text = path.read_text(encoding='utf-8-sig')
                pattern = r'\n?# BEGIN IA-HUB MEMORY[\s\S]*?# END IA-HUB MEMORY\n?'
                text = re.sub(pattern, lambda m: '' if entry_owned(m[0], root) else m[0], text)
                save(path, text)
            continue
        field = 'mcp' if key.startswith('opencode') else 'mcpServers'
        if key == 'agy' and path.exists():
            owned_agy = entry_owned(json_file(path).get(field, {}).get('ia_hub', {}), root)
        def edit(obj):
            group = obj.get(field, {})
            if entry_owned(group.get('ia_hub', {}), root):
                group.pop('ia_hub', None)
                if key.startswith('opencode') and isinstance(obj.get('instructions'), list):
                    instruction = str(path.parent / 'ia-hub.md').replace('\\', '/')
                    obj['instructions'] = [v for v in obj['instructions'] if v.replace('\\', '/') != instruction]
        json_edit(path, edit)
    settings = home / '.claude/settings.json'
    known_marketplaces = home / '.claude/plugins/known_marketplaces.json'
    mod_source = json_file(known_marketplaces).get('ia-hub-local', {}).get('source', {}).get('path')
    owned_mod = bool(mod_source and Path(mod_source).resolve() == (root / 'contexto/.orchestration/claude-mod').resolve())
    def remove_hooks(obj):
        if owned_mod:
            obj.get('enabledPlugins', {}).pop('ia-hub-router@ia-hub-local', None)
            obj.get('extraKnownMarketplaces', {}).pop('ia-hub-local', None)
        for event, groups in obj.get('hooks', {}).items():
            remaining = []
            for group in groups:
                hooks = [h for h in group.get('hooks', []) if not entry_owned(h.get('command', ''), root)]
                if hooks:
                    remaining.append({**group, 'hooks': hooks})
            obj['hooks'][event] = remaining
    json_edit(settings, remove_hooks)
    if owned_mod:
        json_edit(known_marketplaces, lambda obj: obj.pop('ia-hub-local', None))
        json_edit(home / '.claude/plugins/installed_plugins.json', lambda obj: obj.get('plugins', {}).pop('ia-hub-router@ia-hub-local', None))
    def agy_hooks(obj):
        if entry_owned(obj.get('ia-hub-memory', {}), root):
            obj.pop('ia-hub-memory', None)
    json_edit(home / '.gemini/config/hooks.json', agy_hooks)
    if owned_agy:
        def permissions(obj):
            allowed = obj.get('permissions', {}).get('allow', [])
            if allowed:
                obj['permissions']['allow'] = [v for v in allowed if v not in ['mcp(ia_hub/' + tool + ')' for tool in ['memory_context', 'memory_get', 'memory_search', 'memory_store', 'memory_relate', 'memory_health']]]
        json_edit(home / '.gemini/antigravity-cli/settings.json', permissions)
    desktops = [home / 'AppData/Roaming/Claude/claude_desktop_config.json'] if windows else []
    if windows:
        desktops += list((home / 'AppData/Local/Packages').glob('Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json'))
    for path in desktops:
        def desktop(obj):
            servers = obj.get('mcpServers', {})
            if entry_owned(servers.get('ia_hub', {}), root):
                servers.pop('ia_hub', None)
        json_edit(path, desktop)
    xdg = Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config') if not windows else home / '.config'
    for path in [home / '.claude/CLAUDE.md', home / '.codex/AGENTS.md', home / '.gemini/GEMINI.md', xdg / 'opencode/ia-hub.md', home / '.profile', home / '.bash_profile', home / '.zprofile']:
        if not path.exists():
            continue
        text = path.read_text(encoding='utf-8-sig')
        for pattern in [r'<!-- BEGIN IA-HUB RULES -->[\s\S]*?<!-- END IA-HUB RULES -->', r'# BEGIN IA-HUB STARTUP[\s\S]*?# END IA-HUB STARTUP']:
            text = re.sub(pattern, lambda m: '' if entry_owned(m[0], root) else m[0], text)
        if text.startswith('<!-- GERADO por ') and str(root).replace('\\', '/') in text.splitlines()[0].replace('\\', '/'):
            text = re.sub(r'(?m)^## Memória entre IAs[^\n]*\n[\s\S]*?(?=^## |\Z)', '', text)
        save(path, text)
    for path in [xdg / 'opencode/plugins/ia-hub-memory.js', xdg / 'autostart/ia-hub-memory.desktop']:
        if path.exists() and entry_owned(path.read_text(encoding='utf-8'), root):
            save(path)
    # Binary packages and the memory directory are deliberately outside this removal.
    return {'backup': str(backup), 'changed': changed}


def remove_integration(root, log):
    home = Path.home()
    if os.name == 'nt':
        import base64
        escaped = str(root).replace("'", "''")
        script = "$ErrorActionPreference='Stop'; $root='" + escaped + "'; foreach($name in @('IA-Hub Memory','IA-Hub Sync')) { $task=Get-ScheduledTask -TaskName $name -ErrorAction SilentlyContinue; if($task -and ($task.Actions | Where-Object { $_.Arguments.IndexOf($root,[StringComparison]::OrdinalIgnoreCase) -ge 0 })) { Unregister-ScheduledTask -TaskName $name -Confirm:$false } }"
        result = subprocess.run(['powershell.exe', '-NoProfile', '-EncodedCommand', base64.b64encode(script.encode('utf-16-le')).decode()], capture_output=True, text=True)
        if result.returncode:
            raise RuntimeError('Falha removendo tarefa: ' + result.stderr[:250])
    else:
        unit = Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config') / 'systemd/user/ia-hub-memory.service'
        if unit.exists() and entry_owned(unit.read_text(encoding='utf-8'), root):
            result = subprocess.run(['systemctl', '--user', 'disable', '--now', unit.name], capture_output=True, text=True)
            if result.returncode:
                raise RuntimeError('Não foi possível desabilitar a unit; configurações preservadas: ' + result.stderr[:200])
            backup = root / 'contexto/.memory/backups' / ('unit-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(unit, backup / unit.name)
            unit.unlink()
    stop_memory(root, log)
    return remove_configs(root, home)
