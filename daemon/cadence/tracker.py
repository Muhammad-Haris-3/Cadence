"""The sampling loop.

Every POLL_SECONDS it asks Windows two questions -- what window is in front,
and has there been any input -- and folds the answers into the open segment.
Three time counters come out of that:

    duration_sec  wall clock the window was in front
    active_sec    that time minus stretches where input had gone quiet
    input_sec     seconds in which input actually happened

duration alone is what "screen was open" means. active and input are what tell
you whether anything was really going on -- a video playing to an empty chair
accumulates duration and nothing else.
"""

import signal
import time
from datetime import datetime

from . import config, db
from .win_probe import foreground_window, idle_millis, last_input_tick

IDLE_APP = "__idle__"
LOCKED_APP = "__locked__"


class Tracker:
    def __init__(self, conn, poll=None, idle_threshold=None, flush=None):
        self.conn = conn
        self.poll = poll or config.POLL_SECONDS
        self.idle_threshold_ms = (idle_threshold or config.IDLE_THRESHOLD_SECONDS) * 1000
        self.flush_every = flush or config.FLUSH_SECONDS

        self.seg_id = None
        self.seg_key = None
        self.duration = 0.0
        self.active = 0.0
        self.input_sec = 0.0

        self._prev_input_tick = last_input_tick()
        self._since_flush = 0.0
        self._stop = False

    # -- segment lifecycle -------------------------------------------------

    def _open(self, key, app, exe, title, is_idle):
        now = datetime.now()
        self.seg_id = db.open_segment(
            self.conn,
            started_at=now.isoformat(timespec="seconds"),
            day=now.strftime("%Y-%m-%d"),
            app=app,
            exe=exe,
            title=title,
            is_idle=is_idle,
        )
        self.seg_key = key
        self.duration = self.active = self.input_sec = 0.0

    def _flush(self, closing=False):
        if self.seg_id is None:
            return
        db.update_segment(
            self.conn,
            self.seg_id,
            self.duration,
            self.active,
            self.input_sec,
            ended_at=datetime.now().isoformat(timespec="seconds") if closing else None,
        )
        self._since_flush = 0.0

    # -- main loop ---------------------------------------------------------

    def stop(self, *_):
        self._stop = True

    def tick(self):
        idle_ms = idle_millis()
        is_idle = idle_ms > self.idle_threshold_ms

        tick_now = last_input_tick()
        had_input = tick_now != self._prev_input_tick
        self._prev_input_tick = tick_now

        window = foreground_window()
        if window is None:
            app, exe, title = LOCKED_APP, None, ""
        elif is_idle:
            # Attribute idle time to a single bucket rather than to whatever
            # window happened to be in front when you walked away.
            app, exe, title = IDLE_APP, None, window["app"]
        else:
            app, exe, title = window["app"], window["exe"], window["title"]

        key = (app, title, is_idle)
        if key != self.seg_key:
            self._flush(closing=True)
            self._open(key, app, exe, title, is_idle)

        self.duration += self.poll
        if not is_idle:
            self.active += self.poll
        if had_input:
            self.input_sec += self.poll

        self._since_flush += self.poll
        if self._since_flush >= self.flush_every:
            self._flush()

    def run(self):
        signal.signal(signal.SIGINT, self.stop)
        signal.signal(signal.SIGTERM, self.stop)

        closed = db.close_dangling(self.conn)
        if closed:
            print(f"[cadence] closed {closed} segment(s) left open by a previous run")
        print(f"[cadence] tracking -> {config.DB_PATH}  (ctrl-c to stop)")

        try:
            while not self._stop:
                started = time.monotonic()
                self.tick()
                # Sleep the remainder of the interval so drift doesn't accumulate.
                time.sleep(max(0.0, self.poll - (time.monotonic() - started)))
        finally:
            self._flush(closing=True)
            print("\n[cadence] stopped, current segment saved")
