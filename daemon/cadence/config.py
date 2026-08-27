"""Runtime configuration. Everything lives under the user's local app data."""

import os
from pathlib import Path

APP_NAME = "Cadence"

DATA_DIR = Path(os.environ.get("CADENCE_DATA_DIR") or (Path.home() / ".cadence"))
DB_PATH = DATA_DIR / "cadence.db"

# How often the sampler wakes up. 1s is cheap (a few win32 calls) and gives
# us second-resolution activity density without any input hook.
POLL_SECONDS = 1.0

# No keyboard/mouse input for this long => the segment counts as idle.
IDLE_THRESHOLD_SECONDS = 60

# How often the open segment is written back to disk, so a crash or a
# hard shutdown loses at most this much of the current segment.
FLUSH_SECONDS = 15


def ensure_data_dir() -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR


# --- browser tab ingest ------------------------------------------------------

# Loopback only. Nothing here is reachable from another machine.
INGEST_HOST = "127.0.0.1"
INGEST_PORT = 8765

TOKEN_PATH = DATA_DIR / "extension_token.txt"

# A tab report older than this is treated as unknown rather than assumed still
# current -- an MV3 service worker can be asleep, and stale data is worse than
# no data.
TAB_MAX_AGE_SECONDS = 150

# Foreground processes whose window we should enrich with a reported tab URL.
BROWSER_APPS = {
    "chrome.exe", "msedge.exe", "brave.exe", "vivaldi.exe",
    "opera.exe", "arc.exe", "firefox.exe",
}


def load_or_create_token() -> str:
    """Shared secret between the daemon and the extension. Generated once."""
    import secrets

    ensure_data_dir()
    if TOKEN_PATH.exists():
        token = TOKEN_PATH.read_text(encoding="utf-8").strip()
        if token:
            return token
    token = secrets.token_urlsafe(24)
    TOKEN_PATH.write_text(token, encoding="utf-8")
    return token


# --- sessionizing ------------------------------------------------------------

# Idle for at least this long ends a session. Below it, the gap is absorbed --
# thinking, reading, and making tea are part of the work, not breaks from it.
IDLE_BREAK_SECONDS = 300

# An off-category excursion shorter than this is an interruption inside the
# session rather than a boundary between two. A thirty-second Slack check should
# not turn one hour of work into two half-hours.
MIN_SWITCH_SECONDS = 120

# Sessions below this are noise in the report, though they stay in the database
# so the day still adds up.
MIN_SESSION_SECONDS = 120

# Window switches per minute at which continuity is judged to have halved.
# Alt-tabbing between an editor, a terminal and a doc page is what working looks
# like, so the tolerance is set well above zero; below ~2/min reads as deep
# focus, above ~12/min as genuinely scattered.
SWITCH_TOLERANCE = 6.0


# --- dashboard ---------------------------------------------------------------

# How often the sampler rebuilds today's sessions, so the dashboard shows a
# current view without the web thread ever needing to write.
SESSIONIZE_EVERY_SECONDS = 60

# How often the open dashboard refetches. Long enough to be quiet, short enough
# that the page is never visibly stale.
DASHBOARD_POLL_SECONDS = 20
