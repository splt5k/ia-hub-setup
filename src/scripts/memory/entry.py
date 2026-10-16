"""Entrypoint absoluto, independente do diretório e do PYTHONPATH do cliente."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
for stream in [sys.stdin, sys.stdout, sys.stderr]:
    if stream is not None and hasattr(stream, 'reconfigure'):
        stream.reconfigure(encoding='utf-8')


def main():
    command = sys.argv[1] if len(sys.argv) > 1 else 'health'
    if command == 'daemon':
        from memory.daemon import main as run
        run()
    elif command == 'mcp':
        from memory.server import main as run
        run(sys.argv[2] if len(sys.argv) > 2 else 'unknown')
    elif command == 'hook':
        from memory.hooks import main as run
        run(sys.argv[2])
    elif command == 'preflight':
        from memory.client import preflight
        preflight()
    elif command in ('linux-apps', 'linux-summary'):
        from memory.linux_apps import install_apps, summary
        install_apps() if command == 'linux-apps' else summary()
    elif command in ('sync', 'startup'):
        from memory.linux import sync
        sync()
        if command == 'startup':
            from memory.client import request
            request('health')
    elif command == 'doctor':
        from memory.doctor import check
        check()
    elif command == 'install':
        from memory.install import main as run
        run()
    else:
        from memory.client import request
        args = json.loads(sys.stdin.read()) if command not in ('health', 'reconcile') else {}
        print(json.dumps(request(command, args), ensure_ascii=False))


if __name__ == '__main__':
    main()
