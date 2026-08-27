"""Real application icons, pulled from the executables themselves.

An icon pack can only ever guess which logo goes with `Code.exe`. Windows already
knows, because the icon is a resource inside the binary -- so this extracts the
genuine one, for every app, including the obscure ones no pack would cover. No
network, no licensing, no cost.

Extraction is comparatively slow and involves GDI handles, so results are cached
on disk and misses are remembered too: a few system binaries (SearchHost.exe
among them) carry no extractable icon, and retrying them on every page load
would be pure waste.
"""

import threading
from pathlib import Path
from typing import Optional

from . import config

ICON_SIZE = 32
_lock = threading.Lock()
_misses = set()


def cache_dir() -> Path:
    path = config.DATA_DIR / "icons"
    path.mkdir(parents=True, exist_ok=True)
    return path


def _safe_name(app: str) -> str:
    return "".join(c for c in app if c.isalnum() or c in "._-").lower()


def _extract(exe_path: str, size: int = ICON_SIZE):
    """Render the executable's icon into a PIL image, releasing every handle."""
    import win32con
    import win32gui
    import win32ui
    from PIL import Image

    large, small = win32gui.ExtractIconEx(exe_path, 0)
    handles = list(large) + list(small)
    if not handles:
        return None

    hicon = handles[0]
    screen_dc = None
    memdc = None
    try:
        screen = win32gui.GetDC(0)
        screen_dc = win32ui.CreateDCFromHandle(screen)

        bitmap = win32ui.CreateBitmap()
        bitmap.CreateCompatibleBitmap(screen_dc, size, size)
        memdc = screen_dc.CreateCompatibleDC()
        memdc.SelectObject(bitmap)
        memdc.DrawIcon((0, 0), hicon)

        image = Image.frombuffer(
            "RGBA", (size, size), bitmap.GetBitmapBits(True), "raw", "BGRA", 0, 1
        )
        win32gui.DeleteObject(bitmap.GetHandle())
        return image
    finally:
        if memdc is not None:
            memdc.DeleteDC()
        if screen_dc is not None:
            screen_dc.DeleteDC()
            win32gui.ReleaseDC(0, screen)
        for handle in handles:
            try:
                win32gui.DestroyIcon(handle)
            except Exception:
                pass


def icon_path(conn, app: str) -> Optional[Path]:
    """Path to the cached PNG for `app`, extracting it once if needed."""
    if app in _misses or app.startswith("__"):
        return None

    target = cache_dir() / f"{_safe_name(app)}.png"
    if target.exists():
        return target

    with _lock:
        if target.exists():
            return target

        row = conn.execute(
            "SELECT exe FROM segments WHERE app = ? AND exe IS NOT NULL "
            "ORDER BY id DESC LIMIT 1",
            (app,),
        ).fetchone()
        if not row or not row["exe"] or not Path(row["exe"]).exists():
            _misses.add(app)
            return None

        try:
            image = _extract(row["exe"])
        except Exception:
            _misses.add(app)
            return None

        if image is None:
            _misses.add(app)
            return None

        # A fully transparent result is a miss wearing a disguise.
        if not image.getbbox():
            _misses.add(app)
            return None

        image.save(target, "PNG")
        return target
