import contextlib
import io
import json
import os
import shlex
import subprocess
import sys
import tempfile
import tarfile
import unittest
from pathlib import Path
from types import SimpleNamespace
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / 'scripts'))


class LinuxConfigTests(unittest.TestCase):
    def test_app_launcher_uses_xdg_data_and_escapes_uri_percent(self):
        from memory import linux_apps
        import shutil
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            home = root / 'home'
            data = root / 'data'
            source = root / 'source.tar.gz'
            with tarfile.open(source, 'w:gz') as bundle:
                info = tarfile.TarInfo('Obsidian/obsidian')
                content = b'#!/bin/sh\nexit 0\n'
                info.size = len(content)
                info.mode = 0o755
                bundle.addfile(info, io.BytesIO(content))
            def fetch(url, target, expected=''):
                self.assertTrue(target.is_relative_to(root / 'downloads'))
                target.parent.mkdir(parents=True, exist_ok=True)
                shutil.copy2(source, target)
            with patch.object(linux_apps, 'ROOT', root), patch.object(linux_apps.Path, 'home', return_value=home), patch.dict(os.environ, {'XDG_DATA_HOME': str(data), 'IA_HUB_WORK_DIR': str(root / 'downloads')}), patch.object(linux_apps, 'download', side_effect=fetch), patch.object(linux_apps.shutil, 'which', return_value=None):
                result = linux_apps.portable('obsidian', 'https://example.invalid', ['obsidian'])
            self.assertEqual(result['state'], 'installed')
            menu = (data / 'applications/ia-hub-obsidian.desktop').read_text(encoding='utf-8')
            self.assertIn('%%', menu)
            with patch.object(linux_apps.Path, 'home', return_value=home), patch.object(linux_apps.shutil, 'which', return_value=str(home / '.local/bin/obsidian')), patch.object(linux_apps, 'missing_libraries', return_value='libX missing'), patch.object(linux_apps, 'download', side_effect=AssertionError('unexpected download')):
                self.assertEqual(linux_apps.portable('obsidian', 'https://example.invalid', ['obsidian'])['state'], 'pending')

    def test_systemd_preserves_unknown_daemon_and_recognizes_its_own(self):
        from memory.linux import handoff_to_systemd
        with patch('memory.linux.running_memory', return_value={'root': '/other', 'pid': 42}), patch('memory.linux.os.kill') as kill, self.assertRaises(RuntimeError):
            handoff_to_systemd(Path('/this'), '/this/entry.py')
        kill.assert_not_called()
        with patch('memory.linux.running_memory', return_value={'root': '/this', 'pid': 42}), patch('memory.linux.subprocess.run', return_value=SimpleNamespace(returncode=0, stdout='42\n')), patch('memory.linux.os.kill') as kill:
            handoff_to_systemd(Path('/this'), '/this/entry.py')
        kill.assert_not_called()

    def test_headless_bootstrap_never_downloads_or_installs_graphical_apps(self):
        from memory import linux_apps
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'contexto').mkdir()
            with patch.object(linux_apps, 'ROOT', root), patch.object(linux_apps.platform, 'freedesktop_os_release', return_value={'ID': 'test'}), patch.dict(os.environ, {'IA_HUB_INSTALL_MODE': 'headless'}), patch.object(linux_apps, 'portable', side_effect=AssertionError('GUI invoked')), patch.object(linux_apps, 'package', side_effect=AssertionError('sudo invoked')):
                linux_apps.install_apps()
            report = json.loads((root / 'contexto/bootstrap.json').read_text(encoding='utf-8'))
            self.assertEqual(report['mode'], 'headless')
            self.assertEqual(report['components'][0]['state'], 'skipped')

    def test_graphical_unsupported_distro_reports_pending_official_packages(self):
        from memory import linux_apps
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / 'contexto').mkdir()
            with patch.object(linux_apps, 'ROOT', root), patch.object(linux_apps.platform, 'freedesktop_os_release', return_value={'ID': 'arch'}), patch.dict(os.environ, {'IA_HUB_INSTALL_MODE': 'desktop'}), patch.object(linux_apps, 'portable', side_effect=lambda name, *a: {'name': name, 'state': 'installed'}) as portable, patch.object(linux_apps, 'package', side_effect=AssertionError('unsupported package invoked')), contextlib.redirect_stdout(io.StringIO()):
                linux_apps.install_apps()
                self.assertIn('antigravity-app', [call.args[0] for call in portable.call_args_list])
            report = json.loads((root / 'contexto/bootstrap.json').read_text(encoding='utf-8'))
            self.assertEqual(sum(r['state'] == 'pending' for r in report['components']), 2)

    def test_linux_installer_uses_posix_paths_and_preserves_custom_config(self):
        from memory import install
        with tempfile.TemporaryDirectory(prefix="hub ' space-") as tmp:
            root = Path(tmp)
            home = root / 'home'
            hub = root / 'hub'
            state = hub / 'contexto/.memory'
            state.mkdir(parents=True)
            (hub / 'regras').mkdir()
            repo = Path(__file__).resolve().parents[1]
            import shutil
            shutil.copytree(repo / 'regras', hub / 'regras', dirs_exist_ok=True)
            shutil.copytree(repo / 'claude', hub / 'claude')
            shutil.copytree(repo / 'opencode', hub / 'opencode')
            cfg = home / '.config/opencode/opencode.json'
            cfg.parent.mkdir(parents=True)
            cfg.write_text('{"provider":{"custom":{}},"instructions":["existing.md"]}', encoding='utf-8')
            with patch.object(install, 'WINDOWS', False), patch.object(install.Path, 'home', return_value=home), patch.object(install, 'ROOT', hub), patch.object(install, 'STATE', state), patch.dict(os.environ, {}, clear=True), patch.object(install.subprocess, 'run', return_value=SimpleNamespace(returncode=1, stdout='', stderr='no user bus')) as runner, patch.object(install, 'request', return_value={'records': 0}), contextlib.redirect_stdout(io.StringIO()):
                install.main()
                install.main()
            self.assertFalse(any('powershell' in str(c) for c in runner.call_args_list))
            self.assertFalse((home / 'AppData').exists())
            self.assertIn('custom', json.loads(cfg.read_text(encoding='utf-8'))['provider'])
            self.assertEqual(json.loads(cfg.read_text(encoding='utf-8'))['mcp']['ia_hub']['command'][0], os.path.abspath(sys.executable))
            self.assertEqual(len(json.loads(cfg.read_text(encoding='utf-8'))['instructions']), 2)
            command = json.loads((home / '.claude/settings.json').read_text(encoding='utf-8'))['hooks']['Stop'][0]['hooks'][0]['command']
            self.assertEqual(shlex.split(command)[-2:], ['hook', 'claude'])
            self.assertEqual((home / '.profile').read_text(encoding='utf-8').count('# BEGIN IA-HUB STARTUP'), 1)
            generated = (home / '.codex/AGENTS.md').read_text(encoding='utf-8')
            self.assertIn('.memory-runtime/bin/python', generated)
            self.assertNotIn('Scripts\\python.exe', generated)
            self.assertIn('Linux (Bash)', generated)

    def test_systemd_startup_and_escaped_paths(self):
        from memory.linux import setup_startup
        written = {}
        def save(path, text):
            written[str(path)] = text
        with tempfile.TemporaryDirectory() as tmp, patch('memory.linux.running_memory', return_value=None), patch('memory.linux.subprocess.run', return_value=SimpleNamespace(returncode=0, stderr='')) as runner:
            root = Path(tmp)
            result = setup_startup(root, root, '/tmp/with space%/python', '/tmp/with space%/entry.py', save)
            self.assertEqual(result, 'systemd-user')
            unit = next(v for k, v in written.items() if k.endswith('.service'))
            self.assertIn('space%%', unit)
            self.assertIn('Restart=on-failure', unit)
            self.assertIn('enable', str(runner.call_args_list))


@unittest.skipIf(os.name == 'nt', 'Shell Linux; exercitado no WSL')
class LinuxShellTests(unittest.TestCase):
    def run_shell(self, text, env=None):
        script = Path(__file__).resolve().parents[1] / 'scripts/bootstrap-linux.sh'
        result = subprocess.run(['bash', '-c', 'source ' + shlex.quote(str(script)) + '\n' + text], env={**os.environ, **(env or {})}, capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)
        return result.stdout.strip()

    def test_headless_ssh_even_when_display_is_set(self):
        self.assertEqual(self.run_shell('hub_detect_mode', {'SSH_CONNECTION': 'server', 'DISPLAY': ':0'}), 'headless')

    def test_wsl_windows_paths_are_not_given_to_vendor_installers(self):
        self.run_shell('hub_is_wsl() { return 0; }; HUB=/repo; PATH=/mnt/c/Windows:/usr/bin:/repo/.tools/uv; hub_clean_wsl_path; [[ $PATH = /usr/bin:/repo/.tools/uv ]]')

    def test_stale_display_is_not_graphical(self):
        self.assertEqual(self.run_shell('hub_is_wsl() { return 1; }; xdpyinfo() { return 1; }; hub_detect_mode', {'SSH_CONNECTION': '', 'SSH_TTY': '', 'DISPLAY': ':99999', 'WAYLAND_DISPLAY': ''}), 'headless')

    def test_live_display_is_graphical(self):
        self.assertEqual(self.run_shell('hub_is_wsl() { return 1; }; xdpyinfo() { return 0; }; hub_detect_mode', {'SSH_CONNECTION': '', 'SSH_TTY': '', 'DISPLAY': ':0'}), 'desktop')

    def test_present_cli_is_not_reinstalled_and_failed_install_reports_failure(self):
        self.run_shell('hub_install_script() { return 99; }; hub_cli bash https://example.invalid/install; if hub_cli definitely_missing https://example.invalid/install; then exit 1; fi')
