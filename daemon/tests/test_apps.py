"""Rule-by-rule check of segment -> per-application visit rollup."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-apps-")

from cadence import config, db, web  # noqa: E402

DAY = "2026-08-27"


def add(conn, app, start, seconds, *, title="", category="comms", inp=None):
    """Insert one closed segment, given a HH:MM:SS start."""
    h, m, s = (int(p) for p in start.split(":"))
    end_total = h * 3600 + m * 60 + s + seconds
    ended = f"{end_total // 3600:02d}:{(end_total % 3600) // 60:02d}:{end_total % 60:02d}"
    conn.execute(
        "INSERT INTO segments (started_at, ended_at, day, app, exe, title, is_idle, "
        "duration_sec, active_sec, input_sec, category) "
        "VALUES (?, ?, ?, ?, NULL, ?, 0, ?, ?, ?, ?)",
        (f"{DAY}T{start}", f"{DAY}T{ended}", DAY, app, title,
         seconds, seconds, seconds if inp is None else inp, category),
    )


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    return ok


def main():
    conn = db.connect(Path(os.environ["CADENCE_DATA_DIR"]) / "t.db")
    results = []

    # A brief excursion is not a break: the sessionizer's own threshold decides.
    short = max(config.MIN_SWITCH_SECONDS - 30, 5)
    long = config.MIN_SWITCH_SECONDS + 60

    add(conn, "WhatsApp.Root.exe", "09:00:00", 300)
    add(conn, "explorer.exe", "09:05:00", short, category="other")
    add(conn, "WhatsApp.Root.exe", f"09:0{5 + short // 60}:{short % 60:02d}", 120)
    conn.commit()

    apps = web._app_rollup(conn, DAY)
    whatsapp = next(a for a in apps if a["app"] == "WhatsApp.Root.exe")

    print("\nmerging")
    results.append(check("a short excursion does not split a visit", len(whatsapp["visits"]), 1))
    results.append(check("merged visit sums only time in the app", whatsapp["duration_sec"], 420))
    results.append(check("time spent elsewhere is kept, not hidden",
                         whatsapp["visits"][0]["away_sec"] >= short, True))

    # A real absence is a real break.
    add(conn, "WhatsApp.Root.exe", "11:00:00", 60)
    conn.commit()
    whatsapp = next(a for a in web._app_rollup(conn, DAY) if a["app"] == "WhatsApp.Root.exe")

    print("\nbreaks")
    results.append(check("a long absence starts a new visit", len(whatsapp["visits"]), 2))
    results.append(check("the break is reported on the visit that follows it",
                         whatsapp["visits"][1]["break_sec"] > long, True))
    results.append(check("the first visit has no break before it",
                         whatsapp["visits"][0]["break_sec"], None))
    results.append(check("total spans every visit", whatsapp["duration_sec"], 480))

    print("\ngrouping")
    add(conn, "chrome.exe", "10:00:00", 90, title="One", category="browsing")
    add(conn, "chrome.exe", "10:30:00", 30, title="Two", category="browsing")
    conn.commit()
    apps = web._app_rollup(conn, DAY)

    results.append(check("one row per application, not per window title",
                         len([a for a in apps if a["app"] == "chrome.exe"]), 1))
    results.append(check("applications are ordered by time spent",
                         [a["app"] for a in apps][0], "WhatsApp.Root.exe"))
    results.append(check("the busiest window titles the row",
                         next(a for a in apps if a["app"] == "chrome.exe")["top_title"], "One"))

    print("\nexclusions")
    add(conn, "__idle__", "12:00:00", 600, category="idle")
    conn.commit()
    apps = web._app_rollup(conn, DAY)
    results.append(check("idle is not an application", [a["app"] for a in apps].count("__idle__"), 0))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
