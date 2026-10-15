"""Installs the native Claude mod via its official plugin manager, with backups."""
import json
import os
import re
import shutil
import subprocess
from pathlib import Path
from .executor import Executor

TEMPLATE = Path(__file__).with_name('claude-mod')


def install_mod(root, home, python, entry, save, backups):
    binary = shutil.which('claude')
    if not binary:
        return {'installed': False, 'reason': 'Claude CLI indisponível; hooks de memória mantidos.'}
    try:
        command = Executor._native_argv(['claude'], binary)
        version = subprocess.run(command + ['--version'], capture_output=True, text=True, timeout=15)
        match = re.search(r'\b(2)\.(\d+)\.(\d+)\b', version.stdout)
        if version.returncode or not match or tuple(map(int, match.groups())) < (2, 1, 287):
            return {'installed': False, 'reason': 'Mods exigem Claude Code >=2.1.287; hooks mantidos.'}
        destination = root / 'contexto/.orchestration/claude-mod'
        for source in TEMPLATE.rglob('*'):
            if not source.is_file() or 'proof' in source.relative_to(TEMPLATE).parts:
                continue
            text = source.read_text(encoding='utf-8')
            text = text.replace("'__PYTHON__'", json.dumps(python)).replace("'__ENTRY__'", json.dumps(entry))
            save(destination / source.relative_to(TEMPLATE), text)
        config_home = Path(os.environ.get('CLAUDE_CONFIG_DIR', str(home / '.claude')))
        # Preserve plugin manager files before the official CLI mutates them.
        for relative in ['settings.json', 'plugins/known_marketplaces.json', 'plugins/installed_plugins.json']:
            path = config_home / relative
            if path.exists():
                target = backups / ('claude-' + relative.replace('/', '_'))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(path, target)
        known = config_home / 'plugins/known_marketplaces.json'
        if known.exists():
            existing = json.loads(known.read_text(encoding='utf-8')).get('ia-hub-local', {})
            declared = existing.get('source', {}).get('path')
            if existing and (not declared or Path(declared).resolve() != destination.resolve()):
                return {'installed': False, 'reason': 'Marketplace ia-hub-local de outra origem preservado; hooks mantidos.'}
        env = {**os.environ, 'CLAUDE_CONFIG_DIR': str(config_home)}
        steps = [(['plugin', 'validate', str(destination), '--strict']),
                 (['plugin', 'marketplace', 'add', str(destination), '--scope', 'user', '--json']),
                 (['plugin', 'install', 'ia-hub-router@ia-hub-local', '--scope', 'user', '--json']),
                 (['plugin', 'update', 'ia-hub-router@ia-hub-local', '--scope', 'user', '--json'])]
        for arguments in steps:
            result = subprocess.run(command + arguments, env=env, capture_output=True, text=True, timeout=45)
            if result.returncode:
                return {'installed': False, 'reason': 'Gerenciador de plugins recusou ' + arguments[1] + '; hooks mantidos. Consulte os backups/diagnóstico.'}
        return {'installed': True, 'path': str(destination), 'requires_reload': True,
                'scope': 'Claude Code; Desktop Code exige versão/sessão compatível, não Claude Chat convencional'}
    except (OSError, ValueError, subprocess.SubprocessError):
        return {'installed': False, 'reason': 'Instalação do mod pendente; hooks de memória mantidos.'}
