"""A log file, because the tray app has no console to fail in.

Launched at logon through `pythonw.exe` there is no stdout, no stderr and no
window. An exception on the way up ends the process in under a second and
leaves nothing behind to read -- the only symptom is a dashboard that says the
tracker isn't running, with no way to find out why. So everything Cadence would
have printed goes to a file instead, and it is the first thing set up.

`sys.stdout` and `sys.stderr` are pointed at that same file, because under
pythonw they are `None` and a library that assumes a console will die on them.
Uvicorn does exactly that: its log formatter calls `sys.stdout.isatty()`.
"""

import logging
import sys

from . import config

LOG_PATH = config.DATA_DIR / "cadence.log"

# Small enough to read in one sitting. On startup an oversized log is rolled to
# .1 and replaced, which is all the rotation a single-user tool needs -- no
# handler juggling, and no risk of two processes rotating the same file mid-run.
MAX_BYTES = 1_000_000

_configured = False


def _roll_if_large() -> None:
    try:
        if LOG_PATH.exists() and LOG_PATH.stat().st_size > MAX_BYTES:
            LOG_PATH.replace(LOG_PATH.with_suffix(".log.1"))
    except OSError:
        pass  # a locked or unreadable log must never stop tracking


def setup(console: bool = False) -> logging.Logger:
    """Send Cadence's logging to the file, and give pythonw usable std streams.

    Idempotent: main.py and the tray app both call it, and under the tray app
    the sampler thread may reach it first.
    """
    global _configured
    log = logging.getLogger("cadence")
    if _configured:
        return log

    config.ensure_data_dir()
    _roll_if_large()

    stream = open(LOG_PATH, "a", buffering=1, encoding="utf-8", errors="replace")

    # Under pythonw these are None. Everything the process writes to them --
    # ours and our dependencies' -- lands in the log instead of killing it.
    if sys.stdout is None:
        sys.stdout = stream
    if sys.stderr is None:
        sys.stderr = stream

    handler = logging.StreamHandler(stream)
    handler.setFormatter(logging.Formatter("%(asctime)s %(levelname)-7s %(message)s",
                                           datefmt="%Y-%m-%d %H:%M:%S"))
    log.addHandler(handler)

    if console and sys.__stdout__ is not None:
        log.addHandler(logging.StreamHandler(sys.__stdout__))

    log.setLevel(logging.INFO)
    log.propagate = False
    _configured = True
    return log


def get(name: str = "") -> logging.Logger:
    return logging.getLogger(f"cadence.{name}" if name else "cadence")
