import json
import os
import platform
import shutil
import shlex
import tomllib
import urllib.request
import urllib.error
from pathlib import Path
from memory.install import strip_json_comments


def json_file(path):
    return json.loads(strip_json_comments(path.read_text(encoding='utf-8-sig'))) if path.exists() else {}


def entry_owned(value, root):
    if isinstance(value, dict):
        return any(entry_owned(v, root) for v in value.values())
    if isinstance(value, list):
        return any(entry_owned(v, root) for v in value)
    if not isinstance(value, str):
        return False
    def normalize(text):
        text = text.replace('\\\\', '/').replace('\\', '/')
        return text.casefold() if os.name == 'nt' else text
    expected = normalize(str(root / 'scripts/memory/entry.py'))
    if expected in normalize(value):
        return True
    try:
        return any(normalize(arg) == expected for arg in shlex.split(value))
    except ValueError:
        return False


def rpc(root, action='health'):
    token = (root / 'contexto/.memory/token').read_text(encoding='utf-8').strip()
    req = urllib.request.Request('http://127.0.0.1:43127/rpc', json.dumps({'action': action}).encode(), {'Content-Type': 'application/json', 'Authorization': 'Bearer ' + token})
    try:
        with urllib.request.urlopen(req, timeout=5) as response:
            data = json.load(response)
    except urllib.error.HTTPError as error:
        if error.code == 400:
            detail = json.load(error)
            raise RuntimeError(detail.get('error', 'Falha no serviço local.')) from error
        raise
    if 'error' in data:
        raise RuntimeError(data['error'])
    result = data['result']
    if action == 'health' and Path(result.get('root', '')).resolve() != root.resolve():
        raise RuntimeError('O serviço pertence a outra pasta.')
    return result


def configs(home):
    xdg = Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config')
    return {'claude': home / '.claude.json', 'codex': home / '.codex/config.toml',
            'agy': home / '.gemini/config/mcp_config.json', 'opencode': xdg / 'opencode/opencode.json',
            'opencode_jsonc': xdg / 'opencode/opencode.jsonc'}


def configured_servers(home):
    result = {}
    for key, path in configs(home).items():
        try:
            obj = tomllib.loads(path.read_text(encoding='utf-8-sig')) if key == 'codex' and path.exists() else json_file(path)
            result[key] = obj.get('mcp_servers' if key == 'codex' else 'mcp' if key.startswith('opencode') else 'mcpServers', {}).get('ia_hub', {})
        except (ValueError, OSError):
            result[key] = {}
    if os.name == 'nt':
        desktops = [home / 'AppData/Roaming/Claude/claude_desktop_config.json']
        desktops += list((home / 'AppData/Local/Packages').glob('Claude_*/LocalCache/Roaming/Claude/claude_desktop_config.json'))
        for path in desktops:
            try:
                server = json_file(path).get('mcpServers', {}).get('ia_hub')
                if server:
                    result['claude-desktop'] = server
            except (OSError, ValueError):
                pass
    return result


def discover(code_root, home=None):
    home = home or Path.home()
    servers = configured_servers(home)
    candidates = [code_root]
    for server in servers.values():
        for arg in server.get('args', server.get('command', [])):
            if isinstance(arg, str) and arg.replace('\\', '/').endswith('/scripts/memory/entry.py'):
                candidate = Path(arg).parent.parent.parent
                if candidate not in candidates and candidate.is_dir():
                    candidates.append(candidate)
    root, health = code_root, {}
    for candidate in candidates:
        try:
            health = rpc(candidate)
            root = candidate
            break
        except (OSError, RuntimeError, ValueError):
            pass
    if not health and len(candidates) > 1 and not (code_root / 'contexto/.memory/installation.json').exists():
        root = candidates[1]
    windows = os.name == 'nt'
    local = home / 'AppData/Local'
    apps = []
    for key, name, binary, kind, dirs in [
        ('claude', 'Claude Code', 'claude', 'cli', []), ('codex', 'Codex', 'codex', 'cli', []),
        ('agy', 'Antigravity CLI', 'agy', 'cli', [local / 'agy/bin/agy.exe']),
        ('opencode', 'OpenCode', 'opencode', 'cli', [local / 'IA-Hub/bin/opencode.exe']),
        ('obsidian', 'Obsidian', 'obsidian', 'app', [local / 'Programs/Obsidian/Obsidian.exe']),
        ('claude-desktop', 'Claude Desktop', 'claude-desktop', 'app', [local / 'AnthropicClaude/claude.exe']),
        ('antigravity-app', 'Antigravity App', 'antigravity-app', 'app', [local / 'Programs/Antigravity/Antigravity.exe']),
        ('codex-app', 'Codex App', 'codex-app', 'app', [])]:
        present = bool(shutil.which(binary) or (windows and any(p.exists() for p in dirs)))
        if windows and key in ('codex-app', 'claude-desktop'):
            pattern = 'OpenAI.Codex_*' if key == 'codex-app' else 'Claude_*'
            present = present or any((local / 'Packages').glob(pattern))
        if key in ('claude', 'codex'):
            present = present or (home / '.local/bin' / (binary + ('.exe' if windows else ''))).exists()
        server = servers.get(key) or (servers.get('opencode_jsonc', {}) if key == 'opencode' else {})
        integrated = entry_owned(server, root)
        apps.append({'id': key, 'name': name, 'kind': kind, 'present': present, 'integrated': integrated})
    return {'root': str(root), 'code_root': str(code_root), 'foreign': root.resolve() != code_root.resolve(),
            'installed': bool(health or (root / 'contexto/.memory/installation.json').exists() or any(entry_owned(v, root) for v in servers.values())),
            'configured': any(entry_owned(v, root) for v in servers.values()),
            'health': health, 'apps': apps, 'system': {'os': 'Windows' if windows else 'Linux', 'arch': platform.machine()},
            'memory_preserved': (root / 'contexto/.memory/memory.sqlite3').exists()}
