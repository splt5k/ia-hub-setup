"""Linux integration: shared rules, XDG paths and per-user startup."""
import json
import os
import re
import shlex
import signal
import subprocess
import sys
import time
from pathlib import Path


def config_home(home):
    return Path(os.environ.get('XDG_CONFIG_HOME') or home / '.config')


def managed(text, start, end, block):
    pattern = re.escape(start) + r'[\s\S]*?' + re.escape(end)
    if start in text and end not in text:
        raise RuntimeError('Bloco gerenciado incompleto; preserve o arquivo e revise: ' + start)
    new = start + '\n' + block.rstrip() + '\n' + end
    return re.sub(pattern, lambda _: new, text).rstrip() + '\n' if start in text else text.rstrip() + '\n\n' + new + '\n'


def sync_rules(root, home, save):
    def render(name):
        text = (root / 'regras' / name).read_text(encoding='utf-8-sig')
        text = text.replace('{{HUB}}\\.memory-runtime\\Scripts\\python.exe {{HUB}}\\scripts\\memory\\entry.py', shlex.join([str(root / '.memory-runtime/bin/python'), str(root / 'scripts/memory/entry.py')]))
        return text.replace('\\.memory-runtime\\Scripts\\python.exe', '/.memory-runtime/bin/python').replace('\\', '/').replace('{{HUB}}', str(root)).replace('Windows (PowerShell)', 'Linux (Bash)')
    core = render('nucleo.md')
    targets = [(home / '.claude/CLAUDE.md', 'claude.md'), (home / '.codex/AGENTS.md', 'codex.md'),
               (home / '.gemini/GEMINI.md', 'antigravity.md'), (config_home(home) / 'opencode/ia-hub.md', 'opencode.md')]
    for path, extra in targets:
        text = path.read_text(encoding='utf-8-sig') if path.exists() else ''
        header = f'<!-- Gerado por {root}/scripts/memory/entry.py sync -->\n\n'
        if extra == 'opencode.md':  # OpenCode: somente memória, sem regras de roteamento/delegação.
            body = header + render(extra)
        else:
            body = header + core
            if extra:
                body += '\n' + render(extra)
        save(path, managed(text, '<!-- BEGIN IA-HUB RULES -->', '<!-- END IA-HUB RULES -->', body))
    for client, dest in [('claude', home / '.claude/agents')]:
        for source in (root / client / 'agents').glob('*.md'):
            path = dest / source.name
            if not path.exists():
                save(path, source.read_text(encoding='utf-8-sig').replace('{{HUB}}', str(root)))
    project_dir = root / 'contexto/projetos'
    project_dir.mkdir(parents=True, exist_ok=True)
    for model, target in [('perfil.md', root / 'contexto/perfil.md'), ('projeto.md', project_dir / '_modelo.md')]:
        if not target.exists() and (root / 'modelos' / model).exists():
            save(target, (root / 'modelos' / model).read_text(encoding='utf-8-sig'))


def unit_arg(value, exec_value=True):
    if '\n' in str(value) or '\r' in str(value):
        raise ValueError('Caminho com quebra de linha não suportado.')
    value = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('%', '%%')
    return '"' + (value.replace('$', '$$') if exec_value else value) + '"'


def running_memory():
    from .client import request
    try:
        return request('health', autostart=False)
    except OSError:
        return None


def handoff_to_systemd(root, entry):
    existing = running_memory()
    if not existing:
        return
    pid = existing.get('pid')
    if Path(existing.get('root', '')).resolve() != root.resolve() or not isinstance(pid, int):
        raise RuntimeError('Serviço existente não identificável; não será encerrado automaticamente.')
    result = subprocess.run(['systemctl', '--user', 'show', 'ia-hub-memory.service', '--property=MainPID', '--value'], capture_output=True, text=True, timeout=10)
    if result.returncode == 0 and result.stdout.strip() == str(pid):
        return
    proc = Path('/proc') / str(pid)
    args = (proc / 'cmdline').read_bytes().decode().split('\0')
    if proc.stat().st_uid != os.getuid() or str(entry) not in args or 'daemon' not in args:
        raise RuntimeError('Processo existente não corresponde ao daemon desta instalação; preservado.')
    os.kill(pid, signal.SIGTERM)
    for _ in range(50):
        if running_memory() is None:
            return
        time.sleep(.1)
    raise RuntimeError('Daemon anterior não encerrou; systemd não foi iniciado para evitar conflito.')


def setup_startup(root, home, python, entry, save):
    unit = config_home(home) / 'systemd/user/ia-hub-memory.service'
    contents = f'''[Unit]
Description=IA-Hub shared local memory

[Service]
Type=simple
ExecStartPre={unit_arg(python)} {unit_arg(entry)} sync
ExecStart={unit_arg(python)} {unit_arg(entry)} daemon
WorkingDirectory={unit_arg(root, False)}
Restart=on-failure
RestartSec=5
UMask=0077

[Install]
WantedBy=default.target
'''
    try:
        active = subprocess.run(['systemctl', '--user', 'show-environment'], capture_output=True, text=True, timeout=10)
    except (OSError, subprocess.TimeoutExpired):
        active = None
    if active and active.returncode == 0:
        handoff_to_systemd(root, entry)
        save(unit, contents)
        for args in [['daemon-reload'], ['enable', 'ia-hub-memory.service'], ['restart', 'ia-hub-memory.service']]:
            result = subprocess.run(['systemctl', '--user', *args], capture_output=True, text=True, timeout=30)
            if result.returncode:
                raise RuntimeError('Falha ao configurar systemd --user: ' + result.stderr[:250])
        return 'systemd-user'
    # Sem systemd: login de terminal e login gráfico; o daemon também inicia pelo MCP.
    command = shlex.join([python, entry, 'startup'])
    profile = home / '.profile'
    old = profile.read_text(encoding='utf-8') if profile.exists() else ''
    block = f'if [ -x {shlex.quote(python)} ]; then\n  ( {command} ) >> {shlex.quote(str(root / "contexto/.memory/startup.log"))} 2>&1 &\nfi'
    save(profile, managed(old, '# BEGIN IA-HUB STARTUP', '# END IA-HUB STARTUP', block))
    for alternative in ['.bash_profile', '.zprofile']:
        path = home / alternative
        if path.exists():
            save(path, managed(path.read_text(encoding='utf-8'), '# BEGIN IA-HUB STARTUP', '# END IA-HUB STARTUP', block))
    # Desktop Entry Exec is not a shell; quote reserved characters separately.
    def desktop_arg(value):
        value = str(value).replace('\\', '\\\\').replace('"', '\\"').replace('`', '\\`').replace('$', '\\$').replace('%', '%%')
        return '"' + value + '"'
    save(config_home(home) / 'autostart/ia-hub-memory.desktop', '[Desktop Entry]\nType=Application\nName=IA-Hub Memory\nTerminal=false\nExec=' + ' '.join(map(desktop_arg, [python, entry, 'startup'])) + '\n')
    return 'profile-and-xdg-autostart'


def sync():
    from .client import ROOT, STATE
    from datetime import datetime
    import shutil
    backup = STATE / 'backups' / ('sync-' + datetime.now().strftime('%Y%m%d-%H%M%S-%f'))
    def save(path, text):
        if path.exists():
            if path.read_text(encoding='utf-8-sig') == text:
                return
            backup.mkdir(parents=True, exist_ok=True)
            shutil.copy2(path, backup / re.sub(r'[:\\/]', '_', str(path)))
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_text(text, encoding='utf-8')
    sync_rules(ROOT, Path.home(), save)
