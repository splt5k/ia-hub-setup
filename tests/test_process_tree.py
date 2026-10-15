import json
import os
import subprocess
import sys
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]/'scripts'))


class ProcessTreeTests(unittest.TestCase):
    @unittest.skipIf(os.name == 'nt','POSIX watchdog; Windows Job Object already owns descendants')
    def test_watchdog_kills_workers_when_daemon_disappears(self):
        with tempfile.TemporaryDirectory(prefix='hub-watchdog-') as temp:
            root=Path(temp); marker=root/'escaped'; started=root/'started'
            child=f'import time;from pathlib import Path;Path({str(started)!r}).write_text("ready");time.sleep(1);Path({str(marker)!r}).write_text("escaped")'
            source=str(Path(__file__).resolve().parents[1]/'scripts')
            daemon=f'import sys,time;sys.path.insert(0,{source!r});from memory.process_tree import ProcessTree;t=ProcessTree([sys.executable,"-c",{child!r}],{temp!r},dict(__import__("os").environ));time.sleep(10)'
            process=subprocess.Popen([sys.executable,'-c',daemon])
            try:
                for _ in range(100):
                    if started.exists():break
                    time.sleep(.02)
                self.assertTrue(started.exists())
                process.kill();process.wait(timeout=5)
                time.sleep(1.1)
                self.assertFalse(marker.exists(),'Worker outlived its daemon.')
            finally:
                if process.poll() is None:
                    process.kill();process.wait(timeout=5)

    def test_timeout_terminates_wrapper_child_and_grandchild(self):
        from memory.executor import Executor
        from memory.core import Memory
        with tempfile.TemporaryDirectory(prefix='hub-tree-') as temp:
            root = Path(temp); marker = root/'escaped'; started = root/'started'
            grandchild = f'import time;from pathlib import Path;time.sleep(1);Path({str(marker)!r}).write_text("escaped")'
            child = f'import subprocess,sys,time;from pathlib import Path;subprocess.Popen([sys.executable,"-c",{grandchild!r}]);Path({str(started)!r}).write_text("started");time.sleep(10)'
            wrapper = f'import subprocess,sys,time;subprocess.Popen([sys.executable,"-c",{child!r}]);time.sleep(10)'
            executor = Executor(Memory(root),root)
            try:
                with patch.object(executor,'_command',return_value=([sys.executable,'-c',wrapper],{})), patch('memory.executor.PROCESS_TIMEOUT',.5):
                    with self.assertRaises(TimeoutError):
                        executor._process({},'unused',temp)
                self.assertTrue(started.exists(), 'Fixture must really start a descendant before timeout.')
                time.sleep(1.1)
                self.assertFalse(marker.exists(), 'Grandchild survived timeout.')
            finally:
                executor.pool.shutdown(wait=True)
