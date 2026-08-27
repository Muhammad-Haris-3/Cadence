"""Compact a day into something worth reasoning about.

This is the shared input for both summary paths -- the free one, where Claude
Code reads it directly in a session, and the optional API one. It is plain text
rather than JSON because text costs fewer tokens and models read it just as well.

The trailing comparison is the part that matters. A summary built from one day's
numbers can only restate them; a summary that knows the day was 50% more coding
and half the usual distraction can say something you did not already know.
"""

from datetime import datetime

from . import config

TRAILING_DAYS = 7


def fmt(seconds) -> str:
    total = int(seconds or 0)
    if total < 60:
        return f"{total}s"
    minutes, secs = divmod(total, 60)
    if minutes < 60:
        return f"{minutes}m {secs:02d}s"
    hours, minutes = divmod(minutes, 60)
    return f"{hours}h {minutes:02d}m"


def _pct(part, whole) -> int:
    return round((part / whole) * 100) if whole else 0


def _delta(current, baseline) -> str:
    """Signed percentage against the baseline, or a plain note when there is none."""
    if not baseline:
        return "no baseline"
    change = round(((current - baseline) / baseline) * 100)
    return f"{change:+d}%"


def _trailing_days(conn, day: str) -> list:
    """The most recent tracked days before `day`. Skips gaps rather than
    averaging zeros into them -- a weekend off is not a productivity collapse."""
    return [
        row["day"]
        for row in conn.execute(
            "SELECT DISTINCT day FROM segments WHERE day < ? ORDER BY day DESC LIMIT ?",
            (day, TRAILING_DAYS),
        )
    ]


def _category_totals(conn, days: list) -> dict:
    if not days:
        return {}
    placeholders = ",".join("?" * len(days))
    rows = conn.execute(
        f"SELECT category, SUM(duration_sec) total FROM segments "
        f"WHERE day IN ({placeholders}) AND category NOT IN ('idle','away') "
        f"GROUP BY category",
        days,
    ).fetchall()
    return {r["category"]: r["total"] for r in rows}


def build(conn, day: str) -> str:
    """Render the day, and its context, as text."""
    lines = []

    try:
        weekday = datetime.strptime(day, "%Y-%m-%d").strftime("%A")
    except ValueError:
        weekday = ""

    totals = conn.execute(
        "SELECT SUM(duration_sec) d, SUM(active_sec) a, SUM(input_sec) i "
        "FROM segments WHERE day = ? AND category NOT IN ('idle','away')",
        (day,),
    ).fetchone()

    if not totals or not totals["d"]:
        return f"Day: {day} ({weekday})\nNothing was tracked on this day."

    lines.append(f"Day: {day} ({weekday})")
    lines.append(
        f"Tracked {fmt(totals['d'])} · at the machine {fmt(totals['a'])} · "
        f"engaged {fmt(totals['i'])} ({_pct(totals['i'], totals['d'])}% of tracked time)"
    )

    idle = conn.execute(
        "SELECT SUM(duration_sec) d FROM segments WHERE day = ? AND category IN ('idle','away')",
        (day,),
    ).fetchone()
    if idle and idle["d"]:
        lines.append(f"Away or idle: {fmt(idle['d'])}")

    # -- sessions ----------------------------------------------------------

    sessions = conn.execute(
        "SELECT * FROM sessions WHERE day = ? AND duration_sec >= ? ORDER BY started_at",
        (day, config.MIN_SESSION_SECONDS),
    ).fetchall()

    if sessions:
        lines.append(f"\nSessions ({len(sessions)}):")
        for s in sessions:
            start = (s["started_at"] or "")[11:16]
            end = (s["ended_at"] or "")[11:16]
            notes = []
            if s["interruptions"]:
                notes.append(f"{s['interruptions']} interruptions")
            if s["switches"]:
                notes.append(f"{s['switches']} window switches")
            suffix = f"  ({', '.join(notes)})" if notes else ""
            lines.append(
                f"  {start}-{end}  {fmt(s['duration_sec']):>9}  focus {s['focus_score']:>4.0f}  "
                f"{(s['category'] or ''):<12} {(s['top_title'] or s['top_app'] or '')[:44]}{suffix}"
            )

        longest = max(sessions, key=lambda s: s["duration_sec"])
        lines.append(
            f"Longest block: {fmt(longest['duration_sec'])} on {longest['category']} "
            f"(focus {longest['focus_score']:.0f})"
        )

    # -- categories --------------------------------------------------------

    categories = conn.execute(
        "SELECT category, SUM(duration_sec) d, SUM(input_sec) i FROM segments "
        "WHERE day = ? AND category NOT IN ('idle','away') "
        "GROUP BY category ORDER BY d DESC",
        (day,),
    ).fetchall()

    if categories:
        lines.append("\nCategories:")
        for c in categories:
            lines.append(
                f"  {(c['category'] or 'other'):<14}{fmt(c['d']):>9}  "
                f"engaged {fmt(c['i'])} ({_pct(c['i'], c['d'])}%)"
            )

    # -- detail ------------------------------------------------------------

    windows = conn.execute(
        "SELECT app, title, SUM(duration_sec) d, SUM(input_sec) i FROM segments "
        "WHERE day = ? AND category NOT IN ('idle','away') "
        "GROUP BY app, title ORDER BY d DESC LIMIT 10",
        (day,),
    ).fetchall()
    if windows:
        lines.append("\nTop windows:")
        for w in windows:
            lines.append(
                f"  {fmt(w['d']):>9}  {_pct(w['i'], w['d']):>3}%  "
                f"{w['app']:<20} {(w['title'] or '')[:50]}"
            )

    sites = conn.execute(
        "SELECT host, SUM(duration_sec) d, SUM(input_sec) i FROM segments "
        "WHERE day = ? AND host IS NOT NULL GROUP BY host ORDER BY d DESC LIMIT 8",
        (day,),
    ).fetchall()
    if sites:
        lines.append("\nTop sites:")
        for s in sites:
            lines.append(f"  {fmt(s['d']):>9}  {_pct(s['i'], s['d']):>3}%  {s['host']}")

    # -- baseline ----------------------------------------------------------

    trailing = _trailing_days(conn, day)
    if trailing:
        placeholders = ",".join("?" * len(trailing))
        past = conn.execute(
            f"SELECT SUM(duration_sec) d FROM segments "
            f"WHERE day IN ({placeholders}) AND category NOT IN ('idle','away')",
            trailing,
        ).fetchone()

        avg_tracked = (past["d"] or 0) / len(trailing)
        lines.append(
            f"\nAgainst the previous {len(trailing)} tracked day(s), as daily averages:"
        )
        lines.append(
            f"  tracked       {fmt(totals['d']):>9} vs {fmt(avg_tracked):>9}  "
            f"{_delta(totals['d'], avg_tracked)}"
        )

        today_by_cat = {c["category"]: c["d"] for c in categories}
        past_by_cat = _category_totals(conn, trailing)
        for category in sorted(
            set(today_by_cat) | set(past_by_cat),
            key=lambda c: today_by_cat.get(c, 0),
            reverse=True,
        )[:6]:
            current = today_by_cat.get(category, 0)
            baseline = past_by_cat.get(category, 0) / len(trailing)
            lines.append(
                f"  {category:<14}{fmt(current):>9} vs {fmt(baseline):>9}  "
                f"{_delta(current, baseline)}"
            )
    else:
        lines.append("\nNo earlier tracked days yet, so there is no baseline to compare against.")

    return "\n".join(lines)
