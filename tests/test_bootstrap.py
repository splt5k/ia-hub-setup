import os
import subprocess
import unittest
from pathlib import Path


@unittest.skipUnless(os.name == 'nt', 'Bootstrap Windows')
class BootstrapTests(unittest.TestCase):
    def ps(self, body):
        script = Path(__file__).resolve().parents[1] / 'scripts/bootstrap.ps1'
        result = subprocess.run(['powershell.exe', '-NoProfile', '-Command',
                                 ". '" + str(script).replace("'", "''") + "'; " + body],
                                capture_output=True, text=True)
        self.assertEqual(result.returncode, 0, result.stdout + result.stderr)

    def test_present_component_never_installs(self):
        self.ps("function Install-HubPackage { throw 'unexpected install' }; "
                "$r=Ensure-HubPackage 'Existing' 'some.id' { $true }; "
                "if ($r.state -ne 'present') { throw 'wrong state' }")

    def test_path_refresh_does_not_grow_with_repeated_calls(self):
        self.ps("Update-HubPath; $first=$env:PATH; Update-HubPath; "
                "if ($env:PATH -ne $first) { throw 'PATH duplicates' }")

    def test_missing_winget_is_bootstrapped_once(self):
        self.ps("$script:calls=0; $script:ready=$false; "
                "function Find-HubWinget { $script:ready }; "
                "function Invoke-HubWingetInstaller { $script:calls++; $script:ready=$true }; "
                "Ensure-HubWinget; Ensure-HubWinget; "
                "if ($script:calls -ne 1) { throw 'winget bootstrap failed' }")

    def test_install_failure_is_reported(self):
        self.ps("function Install-HubPackage { throw 'offline' }; "
                "$r=Ensure-HubPackage 'Missing' 'some.id' { $false }; "
                "if ($r.state -ne 'failed' -or $r.detail -notmatch 'offline') { throw 'lost failure' }")

    def test_success_requires_detectable_binary(self):
        self.ps("function Install-HubPackage {}; "
                "$r=Ensure-HubPackage 'Missing' 'some.id' { $false }; "
                "if ($r.state -ne 'failed') { throw 'false success' }")

    def test_uv_bootstrap_when_missing_and_idempotence(self):
        self.ps("$script:calls=0; $script:ready=$false; "
                "function Find-HubUv { if ($script:ready) { 'uv.exe' } }; "
                "function Invoke-HubUvInstaller { $script:calls++; $script:ready=$true }; "
                "$a=Ensure-HubUv; $b=Ensure-HubUv; "
                "if ($script:calls -ne 1 -or $a -ne 'uv.exe' -or $b -ne $a) { throw 'bootstrap failed' }")
