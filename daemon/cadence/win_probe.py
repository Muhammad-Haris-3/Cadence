"""Thin wrappers over the Win32 APIs the sampler needs.

Deliberately narrow: we read *window metadata* (process name, window title) and
*whether* input happened -- never what was typed. There is no keyboard hook here
and there should never be one.
"""

import ctypes
from ctypes import wintypes
from typing import Optional, TypedDict

import psutil
import win32gui
import win32process

_user32 = ctypes.windll.user32
_kernel32 = ctypes.windll.kernel32
_kernel32.GetTickCount.restype = wintypes.DWORD


class _LastInputInfo(ctypes.Structure):
    _fields_ = [("cbSize", wintypes.UINT), ("dwTime", wintypes.DWORD)]


class Window(TypedDict):
    app: str
    exe: Optional[str]
    title: str
    pid: int


def last_input_tick() -> int:
    """Tick count of the most recent keyboard or mouse input, system-wide."""
    info = _LastInputInfo()
    info.cbSize = ctypes.sizeof(_LastInputInfo)
    _user32.GetLastInputInfo(ctypes.byref(info))
    return int(info.dwTime)


def idle_millis() -> int:
    """Milliseconds since the last input. 32-bit arithmetic so the ~49-day
    GetTickCount rollover subtracts correctly instead of going negative."""
    return (_kernel32.GetTickCount() - last_input_tick()) & 0xFFFFFFFF


def foreground_window() -> Optional[Window]:
    """The window the user is actually looking at, or None if there isn't one
    (lock screen, secure desktop, UAC prompt)."""
    hwnd = _user32.GetForegroundWindow()
    if not hwnd:
        return None

    try:
        title = win32gui.GetWindowText(hwnd)
    except Exception:
        title = ""

    try:
        _, pid = win32process.GetWindowThreadProcessId(hwnd)
    except Exception:
        return None

    app, exe = "unknown", None
    if pid:
        try:
            proc = psutil.Process(pid)
            app = proc.name()
            exe = proc.exe()
        except (psutil.NoSuchProcess, psutil.AccessDenied, OSError):
            pass

    return Window(app=app, exe=exe, title=title, pid=int(pid or 0))


def session_locked() -> bool:
    """True when the workstation is locked -- there is no foreground window to
    attribute time to, and we should not guess."""
    return _user32.GetForegroundWindow() == 0
