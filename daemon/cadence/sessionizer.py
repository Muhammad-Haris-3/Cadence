"""Segments -> sessions.

A segment ends whenever the foreground window changes, so a two-hour coding
block arrives as hundreds of rows: every tab switch, every file switch, every
glance at the terminal. Nobody experienced that as hundreds of things. A
*session* is the block as you actually lived it.

Three rules decide where one session ends and the next begins:

  1. A long idle gap ends it. Short ones do not -- thinking, reading a page,
     making tea are all part of the session, and IDLE_BREAK_SECONDS is the line.
  2. A sustained change of category ends it. A *brief* one does not: dipping
     into Slack for thirty seconds mid-session is recorded as an interruption
     inside the session, not as two sessions with a third wedged between.
  3. A day boundary ends it, so daily rollups stay honest.

Rebuilding is a pure function of the segments table -- it deletes the day's
sessions and recomputes from scratch, so it is idempotent and safe to rerun
after editing the rules or the category list.
"""

from collections import Counter
from datetime import datetime

from . import config

IDLE_APPS = {"__idle__", "__locked__"}
IDLE_CATEGORIES = {"idle", "away"}


def _is_gap(segment) -> bool:
    return segment["app"] in IDLE_APPS or (segment["category"] or "") in IDLE_CATEGORIES


class _Session:
    """Accumulator for one block of work."""

    def __init__(self, segment):
        self.started_at = segment["started_at"]
        self.ended_at = segment["started_at"]
        self.day = segment["day"]
        self.duration = 0.0
        self.active = 0.0
        self.input = 0.0
        self.switches = -1  # the opening segment isn't a switch
        self.interruptions = 0
        self.by_category = Counter()
        self.by_window = Counter()
        self.segment_ids = []

    def absorb(self, segment) -> None:
        self.duration += segment["duration_sec"]
        self.active += segment["active_sec"]
        self.input += segment["input_sec"]
        self.switches += 1
        self.segment_ids.append(segment["id"])
        self.ended_at = segment["ended_at"] or segment["started_at"]

        if not _is_gap(segment):
            self.by_category[segment["category"] or "other"] += segment["duration_sec"]
            self.by_window[(segment["app"], segment["title"] or "")] += segment["duration_sec"]

    @property
    def dominant(self) -> str:
        return self.by_category.most_common(1)[0][0] if self.by_category else "idle"

    def focus_score(self) -> float:
        """0-100. A heuristic, not a measurement -- three factors, each tunable.

        presence    how much of the block you were actually at the machine
        engagement  how much of that time you were touching the keyboard
        continuity  how little you bounced between windows

        Engagement is deliberately only half-weighted: reading documentation is
        real work with almost no input, and a score that called it slacking off
        would be wrong in the exact case you most want to measure honestly.

        Continuity is measured against SWITCH_TOLERANCE rather than against zero
        switching. Bouncing between an editor, a terminal and a doc page IS
        development; penalising every alt-tab equally scored real work in the
        single digits.
        """
        if self.duration <= 0:
            return 0.0

        presence = self.active / self.duration
        engagement = (self.input / self.active) if self.active > 0 else 0.0
        switches_per_min = max(self.switches, 0) / max(self.duration / 60.0, 1.0)
        continuity = 1.0 / (1.0 + switches_per_min / config.SWITCH_TOLERANCE)

        return round(100 * presence * (0.5 + 0.5 * engagement) * continuity, 1)

    def top_window(self) -> tuple:
        return self.by_window.most_common(1)[0][0] if self.by_window else ("", "")


def _run_length(segments, start: int, category: str) -> tuple[int, float]:
    """How far the off-category excursion beginning at `start` runs.

    Returns (segment count, seconds). Gaps are included so a Slack check that
    trails into a short idle still reads as one excursion.
    """
    count = 0
    seconds = 0.0
    for segment in segments[start:]:
        if not _is_gap(segment) and (segment["category"] or "other") == category:
            break
        count += 1
        seconds += segment["duration_sec"]
    return count, seconds


def build(segments) -> list:
    """Group ordered segments into sessions. Pure -- no database access."""
    sessions = []
    current = None
    index = 0

    def close():
        nonlocal current
        if current is not None and current.duration > 0:
            sessions.append(current)
        current = None

    while index < len(segments):
        segment = segments[index]

        # Rule 1 -- a long gap ends the session; a short one is absorbed.
        if _is_gap(segment):
            if segment["duration_sec"] >= config.IDLE_BREAK_SECONDS:
                close()
                index += 1
                continue
            if current is not None:
                current.absorb(segment)
            index += 1
            continue

        # Rule 3 -- never let a session straddle two days.
        if current is not None and segment["day"] != current.day:
            close()

        if current is None:
            current = _Session(segment)
            current.absorb(segment)
            index += 1
            continue

        # Rule 2 -- sustained category change ends it, a brief one interrupts it.
        category = segment["category"] or "other"
        if category != current.dominant:
            count, seconds = _run_length(segments, index, current.dominant)
            if seconds >= config.MIN_SWITCH_SECONDS:
                close()
                continue  # reprocess this segment as the opener of a new session

            current.interruptions += 1
            for excursion in segments[index:index + count]:
                current.absorb(excursion)
            index += count
            continue

        current.absorb(segment)
        index += 1

    close()
    return sessions


def rebuild(conn, day: str) -> int:
    """Recompute one day's sessions from its segments. Idempotent."""
    conn.execute("UPDATE segments SET session_id = NULL WHERE day = ?", (day,))
    conn.execute("DELETE FROM sessions WHERE day = ?", (day,))

    segments = conn.execute(
        "SELECT id, started_at, ended_at, day, app, title, category, "
        "duration_sec, active_sec, input_sec FROM segments "
        "WHERE day = ? ORDER BY started_at, id",
        (day,),
    ).fetchall()

    for session in build(segments):
        app, title = session.top_window()
        cursor = conn.execute(
            "INSERT INTO sessions (started_at, ended_at, day, duration_sec, active_sec, "
            "input_sec, category, top_app, top_title, switches, interruptions, focus_score) "
            "VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)",
            (
                session.started_at, session.ended_at, session.day,
                session.duration, session.active, session.input,
                session.dominant, app, title,
                max(session.switches, 0), session.interruptions, session.focus_score(),
            ),
        )
        session_id = cursor.lastrowid
        conn.executemany(
            "UPDATE segments SET session_id = ? WHERE id = ?",
            [(session_id, sid) for sid in session.segment_ids],
        )

    return conn.execute("SELECT COUNT(*) c FROM sessions WHERE day = ?", (day,)).fetchone()["c"]


def today() -> str:
    return datetime.now().strftime("%Y-%m-%d")
