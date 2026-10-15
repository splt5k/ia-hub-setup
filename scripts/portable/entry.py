"""Entry point inside the temporary, public installer payload."""
import os
import subprocess
import sys
from pathlib import Path

source = Path(__file__).resolve().parents[2]
sys.path.insert(0, str(source / 'scripts'))
from setup_ui.diagnostics import discover
from setup_ui.portable import deploy, worker_environment, payload_files


def main():
    args = sys.argv[1:]
    allowed = {'--cli', '--preview', '--ui', '--headless', '--desktop', '--memory-only'} if os.name != 'nt' else {'--cli', '--preview'}
    if any(arg not in allowed for arg in args):
        raise ValueError('Argumento inválido; consulte --help. Nenhum arquivo foi instalado.')
    payload_files(source)
    default = Path(os.environ.get('LOCALAPPDATA', Path.home() / 'AppData/Local')) / 'IA-Hub' if os.name == 'nt' else Path(os.environ.get('XDG_DATA_HOME') or Path.home() / '.local/share') / 'ia-hub'
    override = os.environ.get('IA_HUB_INSTALL_DIR')
    root = Path(override).expanduser().resolve() if override else Path(discover(default)['root'])
    graphical = os.name == 'nt' or os.environ.get('IA_HUB_INSTALL_MODE') == 'desktop'
    if '--preview' in args or '--ui' in args or graphical and '--cli' not in args and '--headless' not in args:
        from setup_ui.server import main as server_main
        options = ['--root', str(root), '--payload', str(source)]
        if '--preview' in args:
            options.append('--preview')
        if os.environ.get('IA_HUB_NO_BROWSER') == '1':
            options.append('--no-browser')
        if os.environ.get('IA_HUB_SESSION_FILE'):
            options += ['--session-file', os.environ['IA_HUB_SESSION_FILE']]
        return server_main(options)
    if discover(root).get('foreign'):
        raise RuntimeError('Outra instalação foi identificada; use a pasta ativa. Nenhuma configuração foi alterada.')
    deploy(source, root, lambda level, message: print(message, flush=True))
    with worker_environment(root) as env:
        if os.name == 'nt':
            if any(arg != '--cli' for arg in args):
                raise ValueError('Modo Windows: use --cli ou --preview.')
            command = ['powershell.exe', '-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', str(root / 'install.ps1')]
        else:
            command = ['bash', str(root / 'instalar.sh'), '--cli', *[a for a in args if a != '--cli']]
        return subprocess.call(command, cwd=root, env=env)


if __name__ == '__main__':
    raise SystemExit(main())
