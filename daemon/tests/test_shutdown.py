"""What happens when Cadence stops.

A run that is killed leaves an open segment and nothing else: no log line, no
flush, no clue. That state was indistinguishable from a clean quit, so an
outage of several minutes looked exactly like a normal shutdown, and the log
that `autostart.py status` points at had nothing in it to read.

Three things are checked here. That a stop we *can* control is clean: the tray
waits for the sampler to write its open segment instead of returning and killing
it as a daemon thread. That a stop we cannot control is at least legible
afterwards -- the next start reconstructs when the previous run died, because
the wreckage is the only witness left. And that most of what looked like a stop
is not one at all: the icon's loop ending is explorer's problem, not the
tracker's, so it gets rebuilt and the day carries on.
"""

import os
import sys
import tempfile
import threading
import time
from datetime import datetime, timedelta
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-test-")

from cadence import db  # noqa: E402
from cadence.tracker import Tracker  # noqa: E402
from cadence.win_probe import Window  # noqa: E402


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {label}" + ("" if got == want else f"  (got {got!r}, want {want!r})"))
    return got == want


def check_true(label, got):
    return check(label, bool(got), True)


def open_segments(conn) -> int:
    return conn.execute("SELECT count(*) FROM segments WHERE ended_at IS NULL").fetchone()[0]


def main():
    results = []
    import cadence.tracker as tracker_mod
    tracker_mod.foreground_window = lambda: Window(
        app="Code.exe", exe="C:/Code.exe", title="main.py", pid=1
    )

    # -- a killed run is reconstructed by the next start ---------------------
    print("\nreconstructing a killed run")
    conn = db.connect()
    tracker = Tracker(conn, poll=1.0, idle_threshold=999, flush=999)
    tracker.tick()          # opens a segment
    tracker.duration = 30.0
    tracker._flush()        # durable, but still open -- the state a kill leaves
    started = conn.execute(
        "SELECT started_at FROM segments ORDER BY id DESC LIMIT 1"
    ).fetchone()["started_at"]

    closed, stopped_at = db.close_dangling(conn)
    results.append(check("the open segment was closed", closed, 1))
    results.append(check(
        "stop time is the start plus the last flushed duration",
        stopped_at,
        (datetime.fromisoformat(started) + timedelta(seconds=30)).isoformat(timespec="seconds"),
    ))
    results.append(check("written in the same format as every other timestamp",
                         stopped_at[10], "T"))
    results.append(check("nothing left open", open_segments(conn), 0))
    results.append(check("a clean database reports no stop", db.close_dangling(conn), (0, None)))

    # -- a stop we control waits for the segment to be written --------------
    print("\nshutdown waits for the sampler")
    from cadence.tray import TrayApp

    # A different window than the half above. Segments are keyed
    # UNIQUE (started_at, app, title) at second resolution, so reusing the title
    # collides whenever both halves land in the same wall-clock second.
    tracker_mod.foreground_window = lambda: Window(
        app="Code.exe", exe="C:/Code.exe", title="tray.py", pid=2
    )

    # The real sampler thread, so the connection is opened where it is used --
    # SQLite would refuse one handed across from here.
    app = TrayApp()
    app.sampler = threading.Thread(target=app._sample, daemon=True, name="cadence-sampler")
    app.sampler.start()
    app.ready.wait(timeout=15)

    for _ in range(100):    # let it open a segment
        if open_segments(conn):
            break
        time.sleep(0.05)
    results.append(check_true("the sampler has a segment open", open_segments(conn)))

    app.shutdown("test")
    results.append(check("the sampler thread has ended", app.sampler.is_alive(), False))
    results.append(check("its open segment was written on the way out",
                         open_segments(conn), 0))

    app.shutdown("test again")
    results.append(check("a second shutdown is harmless", app.stopping, True))

    # -- the icon dying is not the tracker dying ----------------------------
    print()
    print("the icon comes back")
    import cadence.tray as tray_mod

    class ScriptedTray(TrayApp):
        """A tray whose icon loop ends the instant it starts, `failures` times
        over, and quits on the one after -- explorer restarting, at speed."""

        def __init__(self, failures):
            super().__init__()
            self.failures = failures
            self.builds = 0

        def _build_icon(self):
            self.builds += 1
            tray = self

            class Icon:
                def run(self):
                    if tray.builds > tray.failures:
                        tray.shutdown("quit from the tray menu")

                def stop(self):
                    pass

            return Icon()

    # The retry sleeps are recorded rather than served; the backoff is the point
    # of the loop and waiting it out would put 45 seconds in a test suite.
    slept = []
    real_sleep, tray_mod.time.sleep = tray_mod.time.sleep, slept.append
    real_port, tray_mod.ingest.port_in_use = tray_mod.ingest.port_in_use, lambda: False
    real_serve = tray_mod.ingest.serve_in_background
    tray_mod.ingest.serve_in_background = lambda *a, **k: None
    try:
        tray = ScriptedTray(failures=4)
        code = tray.run()
    finally:
        tray_mod.time.sleep = real_sleep
        tray_mod.ingest.port_in_use = real_port
        tray_mod.ingest.serve_in_background = real_serve

    results.append(check("the icon was rebuilt after every non-quit end", tray.builds, 5))
    results.append(check("a quit still ends the loop", code, 0))
    results.append(check("retries back off instead of spinning", slept, [3, 6, 12, 24]))
    results.append(check("the sampler outlived all four rebuilds",
                         tray.tracker is not None, True))
    results.append(check("and stopped only once quit arrived", tray.sampler.is_alive(), False))

    print()
    print("the rebuilt icon tells the truth")
    honest = TrayApp()
    results.append(check("fresh", honest._icon_title(), "Cadence - tracking"))
    honest.tracker = Tracker(db.connect(), poll=1.0, idle_threshold=999, flush=999)
    honest.tracker.pause()
    results.append(check("paused", honest._icon_title(), "Cadence - paused"))
    honest.sampler_failed = True
    results.append(check("sampler dead", honest._icon_title(),
                         "Cadence - stopped (see cadence.log)"))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
