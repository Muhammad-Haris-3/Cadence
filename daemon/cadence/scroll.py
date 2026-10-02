"""Distraction time for one day, shaped for Small Steps (the habit app).

Deliberately narrow: seconds per hour and the top few sinks, never a window
title or a full URL. It is the one thing Cadence lets another origin read, so it
carries only what that app needs to say "your scrolling peaks around 4 pm" --
nothing a leaked response could turn into a diary.
"""

from datetime import datetime, timedelta

from . import appnames

CATEGORY = "distraction"
TOP_SINKS = 5


def _sink_name(conn, app: str, host) -> str:
    """The site when the extension knew it, the application otherwise."""
    if host:
        return host.removeprefix("www.")
    return appnames.display_name(conn, app)


def scroll_day(conn, day: str, start_hour: int = 0) -> dict:
    """One day of distraction. With `start_hour`, the day runs from that hour to the
    same hour the next morning -- Small Steps' day ends at 8 am, so a video at 1 am
    belongs to the evening before, not to tomorrow. `by_hour` stays clock hours."""
    start = datetime.strptime(day, "%Y-%m-%d").replace(hour=start_hour)
    end = start + timedelta(days=1)
    calendar_days = sorted({start.strftime("%Y-%m-%d"), (end - timedelta(seconds=1)).strftime("%Y-%m-%d")})
    by_hour = [0.0] * 24
    sinks = {}
    rows = conn.execute(
        f"SELECT app, host, started_at, duration_sec FROM segments "
        f"WHERE day IN ({','.join('?' * len(calendar_days))}) AND category = ?",
        (*calendar_days, CATEGORY),
    ).fetchall()

    for row in rows:
        try:
            moment = datetime.fromisoformat(row["started_at"])
        except (ValueError, TypeError):
            continue
        seconds = row["duration_sec"] or 0
        name = _sink_name(conn, row["app"], row["host"])

        # A 90-minute YouTube segment starting at 3:40 belongs mostly to 4 pm,
        # so it is split at hour boundaries rather than filed under its start --
        # and only the part inside the day counts, for the hours and the sites alike.
        left = seconds
        while left > 0:
            boundary = moment.replace(minute=0, second=0, microsecond=0) + timedelta(hours=1)
            chunk = min(left, (boundary - moment).total_seconds())
            if start <= moment < end:
                by_hour[moment.hour] += chunk
                sinks[name] = sinks.get(name, 0.0) + chunk
            moment, left = boundary, left - chunk

    top = sorted(sinks.items(), key=lambda kv: kv[1], reverse=True)[:TOP_SINKS]
    # A day Cadence never ran reads as zero scrolling -- a perfect day that
    # never happened. Saying so lets the reader leave it out of any average.
    tracked = conn.execute("SELECT 1 FROM segments WHERE day = ? LIMIT 1", (day,)).fetchone() is not None
    return {
        "day": day,
        "tracked": tracked,
        "distraction_sec": round(sum(by_hour)),
        "by_hour": [round(s) for s in by_hour],
        "top": [{"name": name, "sec": round(sec)} for name, sec in top],
    }
