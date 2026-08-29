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

Stopping gets the same treatment as starting, for the same reason. The sampler
is a daemon thread: returning from run() kills it wherever it happens to be,
which for a segment written every FLUSH_SECONDS means losing the one in hand and
leaving it open in the database. So there is exactly one way out of here --
shutdown() -- and it waits.

Nothing else is allowed to end the process. The icon's loop returning is not a
reason to stop tracking: explorer restarts, and the taskbar goes with it, while
the sampler and the web server carry on perfectly well without a picture in the
corner. So run() rebuilds the icon instead of falling through, and only a Quit
gets out.
"""

import threading
import time
import traceback
import webbrowser

import pystray
from PIL import Image, ImageDraw

from . import config, db, ingest, logs, web
from .tracker import Tracker

# Long enough for the sampler to notice the stop flag (one poll) and write the
# open segment; short enough that quitting never feels like a hang.
SHUTDOWN_GRACE_SECONDS = 5

# When the tray goes away it is usually explorer restarting, and it comes back
# within a few seconds. Wait that long, then back off, so a tray that is gone
# for good costs a log line a minute rather than a spinning main thread.
ICON_RETRY_SECONDS = 3
ICON_RETRY_MAX_SECONDS = 60

# An icon that lasted this long was working, whatever ended it. The next failure
# starts from the short delay again instead of inheriting an old backoff.
ICON_HEALTHY_SECONDS = 30

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
        self.sampler = None
        self.sampler_failed = False
        self.ready = threading.Event()
        self.icon = None
        self.stopping = False

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
            self.sampler_failed = True
            self.ready.set()  # don't make run() wait out the timeout
            if self.icon is not None:
                self.icon.icon = self._icon_image()
                self.icon.title = self._icon_title()

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

        icon.icon = self._icon_image()
        icon.title = self._icon_title()

    def quit(self, icon, *_):
        self.shutdown("quit from the tray menu")
        icon.stop()

    # -- shutdown ----------------------------------------------------------

    def shutdown(self, reason: str) -> None:
        """Stop the sampler, and wait for it to actually stop.

        Idempotent, because it is reached two ways: from the Quit item, and
        from run() once the icon loop has ended for any other reason.

        The waiting is the point. `tracker.stop()` only sets a flag; the sampler
        notices it at the top of its next tick, up to POLL_SECONDS later, and
        only then does its `finally` write the open segment. The sampler is a
        daemon thread, so returning from here before that happens kills it
        holding the segment it was about to save -- which is exactly the state
        every unclean run in the log left behind.
        """
        if self.stopping:
            return
        self.stopping = True

        log = logs.get("tray")
        log.info("stopping (%s)", reason)

        if self.tracker is not None:
            self.tracker.stop()
        if self.sampler is not None:
            self.sampler.join(timeout=SHUTDOWN_GRACE_SECONDS)
            if self.sampler.is_alive():
                log.warning(
                    "sampler did not stop within %ss; the open segment will be "
                    "closed by the next run instead", SHUTDOWN_GRACE_SECONDS
                )

    def _pause_label(self, _item) -> str:
        return "Resume tracking" if (self.tracker and self.tracker.paused) else "Pause tracking"

    # -- the icon ----------------------------------------------------------

    def _paused(self) -> bool:
        return self.sampler_failed or bool(self.tracker and self.tracker.paused)

    def _icon_image(self) -> Image.Image:
        return make_icon_image(self._paused())

    def _icon_title(self) -> str:
        if self.sampler_failed:
            return "Cadence - stopped (see cadence.log)"
        return "Cadence - paused" if self._paused() else "Cadence - tracking"

    def _build_icon(self) -> pystray.Icon:
        """A fresh icon, current with whatever the tracker is actually doing.

        Rebuilt rather than reused: a pystray Icon is spent once its loop has
        ended, and one that came back showing the cheerful default would be
        claiming to track through a pause or a dead sampler.
        """
        menu = pystray.Menu(
            pystray.MenuItem("Open dashboard", self.open_dashboard, default=True),
            pystray.MenuItem(self._pause_label, self.toggle_pause),
            pystray.Menu.SEPARATOR,
            pystray.MenuItem("Quit", self.quit),
        )
        return pystray.Icon("cadence", self._icon_image(), self._icon_title(), menu)

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

        self.sampler = threading.Thread(
            target=self._sample, daemon=True, name="cadence-sampler"
        )
        self.sampler.start()
        if not self.ready.wait(timeout=15):
            log.error("sampler did not come up within 15s")

        # Quit is not the only way the icon loop ends. Explorer restarting takes
        # the taskbar and its icons with it, and that return used to fall
        # straight through to process exit -- tracking stopped because a shell
        # process crashed, which has nothing to do with tracking. The sampler and
        # the web server are both still healthy at that moment, so the icon gets
        # rebuilt around them and the day carries on uninterrupted.
        delay = ICON_RETRY_SECONDS
        while True:
            self.icon = self._build_icon()
            started = time.monotonic()
            self.icon.run()
            lived = time.monotonic() - started

            if self.stopping:
                break

            if lived >= ICON_HEALTHY_SECONDS:
                delay = ICON_RETRY_SECONDS
            log.warning(
                "tray icon ended after %.0fs without a quit; rebuilding in %ss "
                "(tracking is unaffected)", lived, delay
            )
            time.sleep(delay)
            delay = min(delay * 2, ICON_RETRY_MAX_SECONDS)

        self.shutdown("tray icon loop ended")  # a no-op after quit; a guard otherwise
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
