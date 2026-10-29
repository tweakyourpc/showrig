"""Small host-OS boundaries shared by the browser server and render workers."""
from __future__ import annotations

import os
import signal
import subprocess


def acquire_lock(file) -> None:
    """Acquire a nonblocking file lock on POSIX or Windows."""
    if os.name == "nt":
        import msvcrt
        file.seek(0, 2)
        if file.tell() == 0:
            file.write("\0")
            file.flush()
        file.seek(0)
        try:
            msvcrt.locking(file.fileno(), msvcrt.LK_NBLCK, 1)
        except OSError as exc:
            raise BlockingIOError("This file is locked by another process.") from exc
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_EX | fcntl.LOCK_NB)


def release_lock(file) -> None:
    """Release a lock previously obtained by acquire_lock."""
    if os.name == "nt":
        import msvcrt
        file.seek(0)
        msvcrt.locking(file.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl
        fcntl.flock(file, fcntl.LOCK_UN)


def process_exists(pid: int) -> bool:
    """Check a process without Windows' destructive os.kill(pid, 0) behavior."""
    if os.name == "nt":
        import ctypes
        from ctypes import wintypes
        kernel = ctypes.WinDLL("kernel32", use_last_error=True)
        kernel.OpenProcess.restype = wintypes.HANDLE
        kernel.OpenProcess.argtypes = [wintypes.DWORD, wintypes.BOOL, wintypes.DWORD]
        kernel.GetExitCodeProcess.argtypes = [wintypes.HANDLE, ctypes.POINTER(wintypes.DWORD)]
        kernel.CloseHandle.argtypes = [wintypes.HANDLE]
        handle = kernel.OpenProcess(0x1000, False, pid)
        if not handle:
            return ctypes.get_last_error() == 5
        try:
            code = wintypes.DWORD()
            return bool(kernel.GetExitCodeProcess(handle, ctypes.byref(code))) and code.value == 259
        finally:
            kernel.CloseHandle(handle)
    try:
        os.kill(pid, 0)
        return True
    except ProcessLookupError:
        return False
    except PermissionError:
        return True


def process_options() -> dict:
    """Keep child media processes in an independently cancellable group."""
    return {"creationflags": subprocess.CREATE_NEW_PROCESS_GROUP} if os.name == "nt" else {"start_new_session": True}


def stop_process(process: subprocess.Popen, force: bool = False) -> None:
    """Stop the worker and its children using the host's process-group mechanism."""
    if process.poll() is not None:
        return
    try:
        if os.name == "nt":
            if force:
                subprocess.run(["taskkill", "/PID", str(process.pid), "/T", "/F"], capture_output=True, timeout=15)
            else:
                process.send_signal(signal.CTRL_BREAK_EVENT)
        else:
            os.killpg(process.pid, signal.SIGKILL if force else signal.SIGTERM)
    except ProcessLookupError:
        pass
