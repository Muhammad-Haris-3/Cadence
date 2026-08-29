"""The local dashboard: JSON API plus the single page that renders it.

Served by the same FastAPI app as the tab ingest, on the same loopback port, so
the tracker is one process. Opening http://127.0.0.1:8765/ while the daemon runs
is the whole install story -- there is no build step and no second server.

Every handler here is read-only in the normal case. The one exception is asking
for a historical day whose sessions were never built; that rebuild is guarded by
the busy timeout in db.connect.
"""

from datetime import date, datetime, timedelta
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles

from . import (appnames, categories, config, db, dayreport, icons, ingest,
               sessionizer, summary, weekreport)

STATIC_DIR = Path(__file__).parent / "static"


def _seconds_since_midnight(stamp: str) -> float:
    """Position within the day, for the timeline band."""
    try:
        moment = datetime.fromisoformat(stamp)
    except (ValueError, TypeError):
        return 0.0
    return moment.hour * 3600 + moment.minute * 60 + moment.second


def _ensure_built(conn, day: str) -> None:
    """Build a day's sessions if nobody has yet.

    Today is rebuilt continuously by the sampler, so this only fires for a
    historical day being opened for the first time.
    """
    has_sessions = conn.execute(
        "SELECT 1 FROM sessions WHERE day = ? LIMIT 1", (day,)
    ).fetchone()
    if has_sessions:
        return

    has_segments = conn.execute(
        "SELECT 1 FROM segments WHERE day = ? LIMIT 1", (day,)
    ).fetchone()
    if has_segments:
        categories.backfill(conn)
        sessionizer.rebuild(conn, day)


def _app_rollup(conn, day: str) -> list:
    """One entry per application, each carrying the story of how it was used.

    A day spent in WhatsApp is not twelve unrelated rows, which is what grouping
    by window title produces -- it is one application picked up and put down
    several times. So segments are grouped by app and then merged into visits,
    and a visit that ends only because you glanced at Explorer for three seconds
    is not a visit that ended. MIN_SWITCH_SECONDS is the same threshold the
    sessionizer uses to decide that a switch was real, reused here so the two
    views of a day cannot disagree about what counts as an interruption.
    """
    rows = conn.execute(
        "SELECT app, title, started_at, ended_at, duration_sec, input_sec, category "
        "FROM segments WHERE day = ? AND category NOT IN ('idle','away') "
        "ORDER BY started_at, id",
        (day,),
    ).fetchall()

    def moment(stamp):
        try:
            return datetime.fromisoformat(stamp)
        except (ValueError, TypeError):
            return None

    grouped = {}
    for row in rows:
        grouped.setdefault(row["app"], []).append(row)

    apps = []
    for app, segments in grouped.items():
        visits = []
        for row in segments:
            started, ended = moment(row["started_at"]), moment(row["ended_at"])
            gap = None
            if visits and started and visits[-1]["_end"]:
                gap = (started - visits[-1]["_end"]).total_seconds()

            if visits and gap is not None and gap < config.MIN_SWITCH_SECONDS:
                visit = visits[-1]
                visit["duration_sec"] += row["duration_sec"] or 0
                visit["input_sec"] += row["input_sec"] or 0
                visit["away_sec"] += max(gap, 0)
                if ended:
                    visit["_end"] = ended
                    visit["end"] = row["ended_at"]
                continue

            visits.append({
                "start": row["started_at"],
                "end": row["ended_at"],
                "offset_sec": _seconds_since_midnight(row["started_at"]),
                "duration_sec": row["duration_sec"] or 0,
                "input_sec": row["input_sec"] or 0,
                "away_sec": 0.0,
                "break_sec": gap if gap is not None else None,
                "title": row["title"] or "",
                "_end": ended,
            })

        for visit in visits:
            visit.pop("_end", None)

        # The open segment carries no duration yet, so an app currently in focus
        # for the first time today would otherwise rank as zero and vanish.
        total = sum(v["duration_sec"] for v in visits)
        titles = {}
        for row in segments:
            if row["title"]:
                titles[row["title"]] = titles.get(row["title"], 0) + (row["duration_sec"] or 0)

        apps.append({
            "app": app,
            "name": appnames.display_name(conn, app),
            "category": segments[-1]["category"] or "other",
            "duration_sec": total,
            "input_sec": sum(v["input_sec"] for v in visits),
            "first_seen": visits[0]["start"] if visits else None,
            "last_seen": visits[-1]["end"] if visits else None,
            "top_title": max(titles, key=titles.get) if titles else "",
            "visits": visits,
        })

    apps.sort(key=lambda a: a["duration_sec"], reverse=True)
    return apps


def day_payload(conn, day: str) -> dict:
    _ensure_built(conn, day)

    sessions = [
        {
            "start": row["started_at"],
            "end": row["ended_at"],
            "offset_sec": _seconds_since_midnight(row["started_at"]),
            "duration_sec": row["duration_sec"],
            "active_sec": row["active_sec"],
            "input_sec": row["input_sec"],
            "category": row["category"] or "other",
            "top_app": row["top_app"] or "",
            "top_title": row["top_title"] or "",
            "switches": row["switches"],
            "interruptions": row["interruptions"],
            "focus_score": row["focus_score"] or 0,
        }
        for row in conn.execute(
            "SELECT * FROM sessions WHERE day = ? ORDER BY started_at", (day,)
        )
    ]

    listed = [s for s in sessions if s["duration_sec"] >= config.MIN_SESSION_SECONDS]
    worked = [s for s in listed if s["category"] not in ("idle", "away")]

    def rows(sql):
        return [dict(r) for r in conn.execute(sql, (day,))]

    written = summary.get(conn, day)

    return {
        "day": day,
        "written": written["text"] if written else None,
        "written_source": written["source"] if written else None,
        "summary": {
            "sessions": len(listed),
            "blocks_sec": sum(s["duration_sec"] for s in worked),
            "longest_sec": max((s["duration_sec"] for s in listed), default=0),
            "tracked_sec": sum(s["duration_sec"] for s in sessions),
            "active_sec": sum(s["active_sec"] for s in sessions),
            "input_sec": sum(s["input_sec"] for s in sessions),
        },
        "sessions": listed,
        "categories": rows(
            # COALESCE, because a segment that is still open has no category
            # yet and would otherwise come back as a second, nameless 'other'.
            "SELECT COALESCE(category, 'other') category, "
            "SUM(duration_sec) duration_sec, SUM(active_sec) active_sec, "
            "SUM(input_sec) input_sec FROM segments WHERE day = ? "
            "GROUP BY 1 ORDER BY duration_sec DESC"
        ),
        "apps": _app_rollup(conn, day),
        "sites": rows(
            "SELECT host, SUM(duration_sec) duration_sec, SUM(input_sec) input_sec "
            "FROM segments WHERE day = ? AND host IS NOT NULL "
            "GROUP BY host ORDER BY duration_sec DESC LIMIT 10"
        ),
    }


def week_bounds(day: str):
    """The Monday and Sunday of the week containing `day`.

    Calendar weeks rather than a trailing seven days, because the report is made
    to be handed to someone: "24 to 30 August" is a span two people can agree on
    without having to know which day it was exported.
    """
    anchor = datetime.strptime(day, "%Y-%m-%d").date()
    start = anchor - timedelta(days=anchor.weekday())
    return start, start + timedelta(days=6)


def _accumulate(days: list, section: str, key_of, keep) -> list:
    """Sum one of the day rollups across the week, largest first."""
    totals = {}
    for day in days:
        for row in day[section]:
            key = key_of(row)
            running = totals.get(key)
            if running is None:
                totals[key] = running = keep(row)
                running["duration_sec"] = 0.0
                running["input_sec"] = 0.0
            running["duration_sec"] += row.get("duration_sec") or 0
            running["input_sec"] += row.get("input_sec") or 0
    return sorted(totals.values(), key=lambda row: row["duration_sec"], reverse=True)


def _top_category(day: dict):
    """What a day was mostly, ignoring the time it was not being used."""
    real = [
        row for row in day["categories"]
        if row["category"] not in ("idle", "away") and row["duration_sec"]
    ]
    return max(real, key=lambda row: row["duration_sec"])["category"] if real else None


def week_payload(conn, day: str) -> dict:
    """A week as the report needs it: each day whole, plus the week's own totals.

    Built by asking for each day exactly as the dashboard would, so a week can
    never disagree with the days inside it. A week still running stops at today
    rather than padding out to Sunday -- empty bars for days that have not
    happened read as absence rather than as the future.
    """
    start, end = week_bounds(day)
    today = date.today()
    through = end if end < today else max(today, start)

    days = []
    cursor = start
    while cursor <= through:
        stamp = cursor.strftime("%Y-%m-%d")
        payload = day_payload(conn, stamp)
        payload["top_category"] = _top_category(payload)
        days.append(payload)
        cursor += timedelta(days=1)

    tracked = [d for d in days if d["summary"]["tracked_sec"]]
    busiest = max(tracked, key=lambda d: d["summary"]["tracked_sec"], default=None)

    def total(field):
        return sum(d["summary"][field] for d in days)

    return {
        "start": start.strftime("%Y-%m-%d"),
        "end": end.strftime("%Y-%m-%d"),
        "through": through.strftime("%Y-%m-%d"),
        "partial": through < end,
        "days": days,
        "busiest": {
            "day": busiest["day"] if busiest else None,
            "name": datetime.strptime(busiest["day"], "%Y-%m-%d").strftime("%A")
                    if busiest else "",
            "tracked_sec": busiest["summary"]["tracked_sec"] if busiest else 0,
        },
        "summary": {
            "tracked_days": len(tracked),
            "sessions": total("sessions"),
            "blocks_sec": total("blocks_sec"),
            "tracked_sec": total("tracked_sec"),
            "active_sec": total("active_sec"),
            "input_sec": total("input_sec"),
            "longest_sec": max((d["summary"]["longest_sec"] for d in days), default=0),
        },
        "categories": _accumulate(
            days, "categories", lambda row: row["category"],
            lambda row: {"category": row["category"]},
        ),
        "apps": _accumulate(
            days, "apps", lambda row: row["app"],
            lambda row: {"app": row["app"], "name": row.get("name"),
                         "category": row.get("category")},
        ),
        "sites": _accumulate(
            days, "sites", lambda row: row["host"],
            lambda row: {"host": row["host"]},
        ),
    }


def build_app(token: str):
    """The ingest app, extended with the dashboard."""
    app = ingest.build_app(token)

    @app.get("/api/days")
    def list_days():
        conn = db.read_connection()
        try:
            days = [r["day"] for r in conn.execute(
                "SELECT DISTINCT day FROM segments ORDER BY day DESC LIMIT 90"
            )]
        finally:
            conn.close()
        return {"days": days, "today": date.today().strftime("%Y-%m-%d")}

    @app.get("/api/day/{day}")
    def get_day(day: str):
        try:
            parsed = datetime.strptime(day, "%Y-%m-%d").date()
        except ValueError:
            raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

        conn = db.read_connection()
        try:
            payload = day_payload(conn, day)
        finally:
            conn.close()

        payload["prev"] = (parsed - timedelta(days=1)).strftime("%Y-%m-%d")
        payload["next"] = (parsed + timedelta(days=1)).strftime("%Y-%m-%d")
        payload["is_today"] = parsed == date.today()
        return payload

    @app.get("/api/day/{day}/pdf")
    def day_pdf(day: str):
        """The same day the dashboard shows, as something you can send someone.

        Rendered on demand rather than cached: a day report is cheap to build
        and today's changes every minute, so a stale file on disk would be one
        more thing that can be wrong.
        """
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

        conn = db.read_connection()
        try:
            payload = day_payload(conn, day)
        finally:
            conn.close()

        content = dayreport.render(
            payload, created=datetime.now().strftime("%Y%m%d%H%M%S")
        )
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="cadence-{day}.pdf"',
                "Content-Length": str(len(content)),
            },
        )

    @app.get("/api/week/{day}/pdf")
    def week_pdf(day: str):
        """The calendar week containing `day`, as one file.

        Seven days is seven day_payload calls, each of which may have to build a
        historical day's sessions the first time it is asked for. That is still
        well under a second on a real database, and doing it here keeps a week
        and the days inside it from ever disagreeing.
        """
        try:
            datetime.strptime(day, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(status_code=400, detail="day must be YYYY-MM-DD")

        conn = db.read_connection()
        try:
            payload = week_payload(conn, day)
        finally:
            conn.close()

        content = weekreport.render(
            payload, created=datetime.now().strftime("%Y%m%d%H%M%S")
        )
        name = f"cadence-week-{payload['start']}.pdf"
        return Response(
            content=content,
            media_type="application/pdf",
            headers={
                "Content-Disposition": f'attachment; filename="{name}"',
                "Content-Length": str(len(content)),
            },
        )

    @app.get("/api/icon")
    def app_icon(app: str):
        """The real icon for an application, extracted from its executable."""
        conn = db.read_connection()
        try:
            path = icons.icon_path(conn, app)
        finally:
            conn.close()

        if path is None:
            # Not an error worth logging -- some binaries simply have no icon,
            # and the page falls back to a category dot.
            return Response(status_code=204)

        return FileResponse(path, media_type="image/png", headers={"Cache-Control": "max-age=86400"})

    @app.get("/")
    def dashboard():
        return FileResponse(STATIC_DIR / "index.html")

    # The manifest and the worker must be served from the root, not from
    # /static, or the service worker's scope will not cover the dashboard.
    @app.get("/manifest.webmanifest")
    def manifest():
        return FileResponse(
            STATIC_DIR / "manifest.webmanifest", media_type="application/manifest+json"
        )

    @app.get("/sw.js")
    def service_worker():
        return FileResponse(
            STATIC_DIR / "sw.js",
            media_type="application/javascript",
            headers={"Cache-Control": "no-cache"},
        )

    @app.get("/favicon.ico")
    def favicon():
        return FileResponse(STATIC_DIR / "icons/icon.ico", media_type="image/x-icon")

    app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
    return app
