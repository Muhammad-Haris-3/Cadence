"""Proper application names, read from the executables themselves.

`WhatsApp.Root.exe` is not what anyone calls that program, and `Code.exe` is not
what anyone calls that one either. A hand-written lookup table would get the
famous dozen right and mislabel everything else, which is the same trap an icon
pack falls into.

Windows already stores the real name in the binary's version resource -- it is
what File Explorer shows in its Description column -- so this asks for that, and
falls back to tidying the filename only when the resource is missing. Reading it
touches the disk, so answers are cached in memory for the life of the process;
they cannot change while a binary is running.
"""

import threading
from typing import Optional

_lock = threading.Lock()
_cache = {}

# Wrappers and launchers whose version resource is unhelpful or absent. The
# tidied filename reads better than "WhatsApp Root Launcher" ever would.
_STRIP_SUFFIXES = (".root", ".app", ".launcher", ".host", ".exe")


def _from_resource(exe_path: str) -> Optional[str]:
    import win32api

    translations = win32api.GetFileVersionInfo(exe_path, r"\VarFileInfo\Translation")
    if not translations:
        return None

    lang, codepage = translations[0]
    key = r"\StringFileInfo\%04X%04X\FileDescription" % (lang, codepage)
    description = win32api.GetFileVersionInfo(exe_path, key)
    if not description:
        return None

    description = description.strip()
    # Some binaries put a whole sentence, a path, or the company name in here.
    if not description or len(description) > 40 or "\\" in description:
        return None
    # And some give the module name rather than the product ("WhatsApp.Root"),
    # which needs the same tidying as a bare filename.
    return _tidy(description) if "." in description else description


def _tidy(app: str) -> str:
    """Make a filename presentable when the binary will not say its own name."""
    name = app
    trimming = True
    while trimming:
        trimming = False
        lowered = name.lower()
        for suffix in _STRIP_SUFFIXES:
            if lowered.endswith(suffix) and len(name) > len(suffix):
                name = name[: -len(suffix)]
                trimming = True
                break
    name = name.replace("_", " ").replace(".", " ").strip()
    if not name:
        return app
    # Leave CamelCase and known casing alone; only rescue all-lowercase names.
    return name.title() if name.islower() else name


def display_name(conn, app: str) -> str:
    """The name a person would use for `app`."""
    if not app:
        return ""

    cached = _cache.get(app)
    if cached is not None:
        return cached

    with _lock:
        if app in _cache:
            return _cache[app]

        name = None
        row = conn.execute(
            "SELECT exe FROM segments WHERE app = ? AND exe IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (app,),
        ).fetchone()

        if row and row["exe"]:
            try:
                name = _from_resource(row["exe"])
            except Exception:
                # No version resource, or no permission to read it. Not worth
                # logging -- the fallback below is a perfectly good answer.
                name = None

        name = name or _tidy(app)
        _cache[app] = name
        return name
