"""Tray application.

The point of the tray app is that tracking stops being something you remember to
do. It owns three things at once:

    main thread    the tray icon and its Windows message loop
    worker thread  the sampler
    daemon thread  the web server (dashboard + tab ingest)

The sampler runs on a worker rather than the main thread because pystray needs
the main one to pump messages. That is why it opens its own database connection
-- SQLite connections have thread affinity and cannot be handed across.

Nothing here may assume a console. This is what the logon task launches, under
pythonw.exe, where an uncaught exception is invisible: the process is simply
gone and the dashboard says the tracker isn't running. So logging is set up
before anything else, and every thread that can die on its own says so first.
"""

import threading
import traceback
import webbrowser

import pystray
from PIL import Image, ImageDraw

from . import config, db, ingest, logs, web
from .tracker import Tracker

ACTIVE_INK = (28, 25, 23, 255)      # --text-primary
PAUSED_INK = (168, 162, 158, 255)   # muted, so the state reads at a glance


def make_icon_image(paused: bool = False) -> Image.Image:
    """Three bars, for the three clocks. Drawn large and downscaled by the tray."""
    size = 64
    image = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    ink = PAUSED_INK if paused else ACTIVE_INK

    for x, top in ((8, 34), (26, 20), (44, 6)):
        draw.rectangle([x, top, x + 12, 58], fill=ink)

    return image


def _show_message(message: str) -> None:
    """There is no console to print to when launched at logon."""
    try:
        import ctypes

        ctypes.windll.user32.MessageBoxW(0, message, "Cadence", 0x40)
    except Exception:
        print(message)


class TrayApp:
    def __init__(self):
        self.tracker = None
        self.ready = threading.Event()
        self.icon = None

    # -- threads -----------------------------------------------------------

    def _sample(self):
        log = logs.get("tray")
        try:
            conn = db.connect()  # this thread's own connection
            self.tracker = Tracker(conn)
            self.ready.set()
            self.tracker.run()
        except Exception:
            # A dead sampler under a live tray icon is the worst failure mode
            # available: it looks like it is tracking and records nothing.
            log.error("sampler thread died:\n%s", traceback.format_exc())
            self.ready.set()  # don't make run() wait out the timeout
            if self.icon is not None:
                self.icon.icon = make_icon_image(paused=True)
                self.icon.title = "Cadence - stopped (see cadence.log)"

    # -- menu actions ------------------------------------------------------

    def open_dashboard(self, *_):
        webbrowser.open(f"http://{config.INGEST_HOST}:{config.INGEST_PORT}/")

    def toggle_pause(self, icon, *_):
        if self.tracker is None:
            return

        if self.tracker.paused:
            self.tracker.resume()
        else:
            self.tracker.pause()

        icon.icon = make_icon_image(self.tracker.paused)
        icon.title = "Cadence - paused" if self.tracker.paused else "Cadence - tracking"

    def quit(self, icon, *_):
        if self.tracker is not None:
            self.tracker.stop()  # flushes the open segment on its way out
        icon.stop()

    def _pause_label(self, _item) -> str:
        return "Resume tracking" if (self.tracker and self.tracker.paused) else "Pause tracking"

    # -- entry point -------------------------------------------------------

    def run(self) -> int:
        log = logs.setup()
        log.info("tray starting (data dir %s)", config.DATA_DIR)

        if ingest.port_in_use():
            log.warning("port %s already in use; not starting a second instance",
                        config.INGEST_PORT)
            self._warn_already_running()
            return 1

        token = config.load_or_create_token()
        ingest.serve_in_background(token, web.build_app(token))
        log.info("dashboard on http://%s:%s/", config.INGEST_HOST, config.INGEST_PORT)

        threading.Thread(target=self._sample, daemon=True, name="cadence-sampler").start()
        if not self.ready.wait(timeout=15):
            log.error("sampler did not come up within 15s")

        menu = pystray.Menu(
            pystray.MenuItem("Open dashboard", self.open_dashboard, default=True),
            pystray.MenuItem(self._pause_label, self.toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit),
        )

        self.icon = pystray.Icon("cadence", make_icon_image(), "Cadence - tracking", menu)
        self.icon.run()
        return 0

    @staticmethod
    def _warn_already_running() -> None:
        _show_message(
            f"Cadence is already running (port {config.INGEST_PORT} is in use).\n\n"
            "Only one instance may run, or every second would be counted twice."
        )


def run() -> int:
    """Top-level guard. Under pythonw a traceback goes nowhere, so write it
    down and then say so on screen -- a message box is the only channel the
    logon task has to a person."""
    try:
        return TrayApp().run()
    except Exception:
        detail = traceback.format_exc()
        try:
            logs.setup().error("Cadence failed to start:\n%s", detail)
        except Exception:
            pass
        _show_message(
            "Cadence could not start.\n\n"
            f"{detail.strip().splitlines()[-1]}\n\n"
            f"Full details: {logs.LOG_PATH}"
        )
        return 1
