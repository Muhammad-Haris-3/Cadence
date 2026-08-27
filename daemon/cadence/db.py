"""SQLite storage. One file, no server, no account.

A *segment* is a contiguous stretch of time on one window. It opens when the
foreground window (or the idle state) changes and closes when it changes again,
so a day is a few thousand rows rather than 86,400 samples.
"""

import sqlite3
from pathlib import Path
from typing import Optional

from . import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS segments (
    id           INTEGER PRIMARY KEY AUTOINCREMENT,
    started_at   TEXT    NOT NULL,          -- ISO8601, local time
    ended_at     TEXT,                      -- NULL while the segment is open
    day          TEXT    NOT NULL,          -- YYYY-MM-DD, for cheap daily rollups
    app          TEXT    NOT NULL,          -- process name, e.g. Code.exe
    exe          TEXT,
    title        TEXT    NOT NULL DEFAULT '',
    url          TEXT,                      -- filled by the browser extension
    is_idle      INTEGER NOT NULL DEFAULT 0,
    duration_sec REAL    NOT NULL DEFAULT 0,   -- wall clock on this window
    active_sec   REAL    NOT NULL DEFAULT 0,   -- wall clock minus idle
    input_sec    REAL    NOT NULL DEFAULT 0,   -- seconds in which input occurred
    category     TEXT,
    UNIQUE (started_at, app, title)
);

CREATE INDEX IF NOT EXISTS idx_segments_day  ON segments (day);
CREATE INDEX IF NOT EXISTS idx_segments_app  ON segments (day, app);
CREATE INDEX IF NOT EXISTS idx_segments_open ON segments (ended_at) WHERE ended_at IS NULL;
"""


def connect(path: Optional[Path] = None) -> sqlite3.Connection:
    config.ensure_data_dir()
    conn = sqlite3.connect(path or config.DB_PATH, isolation_level=None)
    conn.row_factory = sqlite3.Row
    # WAL lets the dashboard read while the tracker is mid-write.
    conn.execute("PRAGMA journal_mode=WAL")
    conn.execute("PRAGMA synchronous=NORMAL")
    conn.executescript(SCHEMA)
    migrate(conn)
    return conn


def open_segment(conn, started_at, day, app, exe, title, is_idle) -> int:
    cur = conn.execute(
        "INSERT INTO segments (started_at, day, app, exe, title, is_idle) "
        "VALUES (?, ?, ?, ?, ?, ?)",
        (started_at, day, app, exe, title, int(is_idle)),
    )
    return int(cur.lastrowid)


def update_segment(conn, seg_id, duration_sec, active_sec, input_sec, ended_at=None) -> None:
    conn.execute(
        "UPDATE segments SET duration_sec = ?, active_sec = ?, input_sec = ?, "
        "ended_at = COALESCE(?, ended_at) WHERE id = ?",
        (duration_sec, active_sec, input_sec, ended_at, seg_id),
    )


def close_dangling(conn) -> int:
    """Close segments left open by a crash or an unclean shutdown, so their
    time doesn't silently bleed into the next run."""
    cur = conn.execute(
        "UPDATE segments SET ended_at = datetime(started_at, '+' || duration_sec || ' seconds') "
        "WHERE ended_at IS NULL"
    )
    return cur.rowcount


def migrate(conn) -> None:
    """Additive migrations for databases created by an earlier version."""
    columns = {row["name"] for row in conn.execute("PRAGMA table_info(segments)")}
    if "host" not in columns:
        conn.execute("ALTER TABLE segments ADD COLUMN host TEXT")
        conn.execute("CREATE INDEX IF NOT EXISTS idx_segments_host ON segments (day, host)")


def set_segment_url(conn, seg_id, url, host) -> None:
    conn.execute("UPDATE segments SET url = ?, host = ? WHERE id = ?", (url, host, seg_id))
