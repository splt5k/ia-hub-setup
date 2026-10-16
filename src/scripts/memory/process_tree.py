"""Own and terminate an entire worker tree, including launcher descendants.

Windows: suspended creation, Job Object assignment, then resume its first thread.
https://learn.microsoft.com/en-us/windows/win32/procthread/job-objects
POSIX: a dedicated session/process group. Neither path uses a shell.
"""
import os
import signal
import subprocess
import sys
import threading
from pathlib import Path


class ProcessTree:
    def __init__(self, argv, cwd, env):
        self.lock = threading.RLock()
        self.job = None
        self.closed = False
        if os.name == 'nt':
            self._windows_job()
        try:
            if os.name != 'nt':
                argv = [sys.executable, str(Path(__file__).with_name('posix_worker.py')), str(os.getpid()), *argv]
            self.process = subprocess.Popen(argv, cwd=cwd, env=env, stdin=subprocess.DEVNULL,
                stdout=subprocess.PIPE, stderr=subprocess.PIPE, shell=False,
                start_new_session=os.name != 'nt',
                creationflags=(0x00000004 | subprocess.CREATE_NO_WINDOW) if os.name == 'nt' else 0)
            if self.job:
                self._assign_and_resume()
        except BaseException:
            if hasattr(self, 'process'):
                self.process.kill()
                self.process.wait(timeout=5)
            self.close()
            raise

    def _windows_job(self):
        import ctypes as c
        from ctypes import wintypes as w
        class Basic(c.Structure):
            _fields_ = [('process_time', c.c_longlong), ('job_time', c.c_longlong), ('flags', w.DWORD),
                ('minimum', c.c_size_t), ('maximum', c.c_size_t), ('active', w.DWORD),
                ('affinity', c.c_size_t), ('priority', w.DWORD), ('scheduling', w.DWORD)]
        class IO(c.Structure):
            _fields_ = [(name, c.c_ulonglong) for name in ('read_ops','write_ops','other_ops','read_bytes','write_bytes','other_bytes')]
        class Extended(c.Structure):
            _fields_ = [('basic',Basic), ('io',IO), ('process_memory',c.c_size_t), ('job_memory',c.c_size_t),
                ('peak_process',c.c_size_t), ('peak_job',c.c_size_t)]
        self.kernel = k = c.WinDLL('kernel32', use_last_error=True)
        k.CreateJobObjectW.argtypes = [c.c_void_p, w.LPCWSTR]; k.CreateJobObjectW.restype = w.HANDLE
        k.SetInformationJobObject.argtypes = [w.HANDLE,c.c_int,c.c_void_p,w.DWORD]; k.SetInformationJobObject.restype = w.BOOL
        k.AssignProcessToJobObject.argtypes = [w.HANDLE,w.HANDLE]; k.AssignProcessToJobObject.restype = w.BOOL
        k.TerminateJobObject.argtypes = [w.HANDLE,w.UINT]; k.TerminateJobObject.restype = w.BOOL
        k.CloseHandle.argtypes = [w.HANDLE]; k.CloseHandle.restype = w.BOOL
        self.job = k.CreateJobObjectW(None, None)
        if not self.job:
            raise c.WinError(c.get_last_error())
        info = Extended(); info.basic.flags = 0x2000  # KILL_ON_JOB_CLOSE; no breakaway.
        if not k.SetInformationJobObject(self.job, 9, c.byref(info), c.sizeof(info)):
            error = c.WinError(c.get_last_error()); self.close(); raise error

    def _assign_and_resume(self):
        import ctypes as c
        from ctypes import wintypes as w
        k = self.kernel
        if not k.AssignProcessToJobObject(self.job, int(self.process._handle)):
            raise c.WinError(c.get_last_error())
        class ThreadEntry(c.Structure):
            _fields_ = [('size',w.DWORD), ('usage',w.DWORD), ('id',w.DWORD), ('owner',w.DWORD),
                ('base',w.LONG), ('delta',w.LONG), ('flags',w.DWORD)]
        k.CreateToolhelp32Snapshot.argtypes = [w.DWORD,w.DWORD]; k.CreateToolhelp32Snapshot.restype = w.HANDLE
        k.Thread32First.argtypes = [w.HANDLE,c.POINTER(ThreadEntry)]; k.Thread32First.restype = w.BOOL
        k.Thread32Next.argtypes = [w.HANDLE,c.POINTER(ThreadEntry)]; k.Thread32Next.restype = w.BOOL
        k.OpenThread.argtypes = [w.DWORD,w.BOOL,w.DWORD]; k.OpenThread.restype = w.HANDLE
        k.ResumeThread.argtypes = [w.HANDLE]; k.ResumeThread.restype = w.DWORD
        snapshot = k.CreateToolhelp32Snapshot(4, 0)
        if snapshot == c.c_void_p(-1).value:
            raise c.WinError(c.get_last_error())
        try:
            entry = ThreadEntry(); entry.size = c.sizeof(entry)
            present = k.Thread32First(snapshot, c.byref(entry))
            while present:
                if entry.owner == self.process.pid:
                    thread = k.OpenThread(2, False, entry.id)
                    if not thread:
                        raise c.WinError(c.get_last_error())
                    try:
                        if k.ResumeThread(thread) == 0xFFFFFFFF:
                            raise c.WinError(c.get_last_error())
                        return
                    finally:
                        k.CloseHandle(thread)
                present = k.Thread32Next(snapshot, c.byref(entry))
            raise OSError('Suspended worker thread not found; worker will not run.')
        finally:
            k.CloseHandle(snapshot)

    def kill(self):
        with self.lock:
            if self.closed:
                return
            if self.job:
                self.kernel.TerminateJobObject(self.job, 1)
            elif hasattr(self, 'process'):
                try:
                    os.killpg(self.process.pid, signal.SIGKILL)
                except ProcessLookupError:
                    pass

    def close(self):
        with self.lock:
            if self.closed:
                return
            self.kill()
            if self.job:
                self.kernel.CloseHandle(self.job)
                self.job = None
            self.closed = True
