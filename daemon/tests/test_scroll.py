"""The /api/scroll endpoint Small Steps reads: shape, hour split, and who may read it."""

import json
import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-scroll-")

from cadence import config, db, scroll, web  # noqa: E402

DAY = "2026-08-27"


def add(conn, app, start, seconds, *, host=None, title="", category="distraction"):
    conn.execute(
        "INSERT INTO segments (started_at, day, app, title, is_idle, duration_sec, "
        "active_sec, input_sec, category, host) VALUES (?, ?, ?, ?, 0, ?, ?, ?, ?, ?)",
        (f"{DAY}T{start}", DAY, app, title, seconds, seconds, seconds, category, host),
    )


def check(label, got, want):
    ok = got == want
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))
    return ok


class FakeRequest:
    def __init__(self, origin):
        self.headers = {"origin": origin} if origin else {}


def main():
    conn = db.connect()  # the default path, so the route's read_connection sees it
    add(conn, "chrome.exe", "15:40:00", 90 * 60, host="www.youtube.com", title="secret video title")
    add(conn, "chrome.exe", "22:00:00", 600, host="www.reddit.com")
    add(conn, "Code.exe", "10:00:00", 3600, category="code")
    conn.commit()

    results = []
    data = scroll.scroll_day(conn, DAY)
    print("\nshape")
    results.append(check("only distraction counts", data["distraction_sec"], 90 * 60 + 600))
    results.append(check("a segment is split at hour boundaries",
                         data["by_hour"][15:17], [20 * 60, 60 * 60]))
    results.append(check("the tail lands in the next hour", data["by_hour"][17], 10 * 60))
    results.append(check("sinks are sites without www", [t["name"] for t in data["top"]],
                         ["youtube.com", "reddit.com"]))
    results.append(check("no window title leaks", "secret" in json.dumps(data), False))
    results.append(check("a day with segments is tracked", data["tracked"], True))
    results.append(check("a day Cadence never ran is not zero scrolling, it's untracked",
                         scroll.scroll_day(conn, "2026-08-01")["tracked"], False))

    print("\norigins")
    route = next(r for r in web.build_app("t").routes if getattr(r, "path", "") == "/api/scroll/{day}")
    allowed = route.endpoint(DAY, FakeRequest("http://localhost:3000"))
    stranger = route.endpoint(DAY, FakeRequest("https://evil.example"))
    results.append(check("Small Steps in dev may read it",
                         allowed.headers.get("access-control-allow-origin"), "http://localhost:3000"))
    results.append(check("any other origin may not", stranger.headers.get("access-control-allow-origin"), None))

    config.SCROLL_ORIGINS_PATH.write_text("https://small-steps.vercel.app/\n", encoding="utf-8")
    deployed = route.endpoint(DAY, FakeRequest("https://small-steps.vercel.app"))
    results.append(check("a deployed origin can be allowlisted in a file",
                         deployed.headers.get("access-control-allow-origin"), "https://small-steps.vercel.app"))

    print("\npreflight")
    pre = next(r for r in web.build_app("t").routes
               if getattr(r, "path", "") == "/api/scroll/{day}" and "OPTIONS" in r.methods)
    yes = pre.endpoint(DAY, FakeRequest("https://small-steps.vercel.app"))
    no = pre.endpoint(DAY, FakeRequest("https://evil.example"))
    results.append(check("an allowlisted site may reach the laptop",
                         yes.headers.get("access-control-allow-private-network"), "true"))
    results.append(check("any other site is refused", no.status_code, 403))

    print(f"\n{sum(results)}/{len(results)} passed")
    return 0 if all(results) else 1


if __name__ == "__main__":
    sys.exit(main())
