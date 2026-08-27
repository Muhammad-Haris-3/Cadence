"""End-to-end check: extension POST -> ingest -> tracker -> SQLite."""

import json
import os
import sys
import tempfile
import time
import urllib.error
import urllib.request
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-test-")

from cadence import config, db, ingest  # noqa: E402
from cadence.tracker import Tracker  # noqa: E402
from cadence.win_probe import Window  # noqa: E402

TOKEN = "test-token-abc"
URL = f"http://{config.INGEST_HOST}:{config.INGEST_PORT}/tab"


def post(payload, token=TOKEN, origin=None):
    headers = {"Content-Type": "application/json", "X-Cadence-Token": token}
    if origin:
        headers["Origin"] = origin
    req = urllib.request.Request(URL, data=json.dumps(payload).encode(), headers=headers, method="POST")
    try:
        with urllib.request.urlopen(req, timeout=5) as res:
            return res.status, json.load(res)
    except urllib.error.HTTPError as e:
        return e.code, None


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {label}" + ("" if got == want else f"  (got {got!r}, want {want!r})"))
    return got == want


def main():
    ingest.serve_in_background(TOKEN)
    for _ in range(50):  # wait for the thread's server to bind
        try:
            urllib.request.urlopen(f"http://{config.INGEST_HOST}:{config.INGEST_PORT}/health", timeout=1)
            break
        except Exception:
            time.sleep(0.1)

    results = []
    print("\nendpoint")
    results.append(check("valid token accepted", post({"url": "https://example.com/a", "title": "A"})[0], 200))
    results.append(check("wrong token rejected", post({"url": "https://example.com"}, token="nope")[0], 401))
    results.append(check("non-extension origin rejected",
                         post({"url": "https://example.com"}, origin="https://evil.test")[0], 403))
    results.append(check("extension origin accepted",
                         post({"url": "https://example.com"}, origin="chrome-extension://abc")[0], 200))

    print("\nsanitizing")
    _, body = post({"url": "https://www.youtube.com/watch?v=xyz789&si=SECRET", "title": "Video"})
    results.append(check("youtube host tracked", body["host"], "www.youtube.com"))
    _, body = post({"url": "chrome://settings", "title": "Settings"})
    results.append(check("chrome:// not tracked", body["tracked"], False))

    print("\nfreshness")
    post({"url": "https://github.com/foo/bar", "title": "foo/bar"})
    results.append(check("fresh tab readable", ingest.STATE.get_fresh().host, "github.com"))
    ingest.STATE._tab.reported_at -= config.TAB_MAX_AGE_SECONDS + 1
    results.append(check("stale tab withheld", ingest.STATE.get_fresh(), None))
    post({"focused": False})
    results.append(check("unfocused browser clears tab", ingest.STATE.get_fresh(), None))

    print("\ntracker enrichment")
    conn = db.connect()
    tracker = Tracker(conn, poll=1.0, idle_threshold=999, flush=999)

    import cadence.tracker as tracker_mod
    tracker_mod.foreground_window = lambda: Window(app="chrome.exe", exe="C:/chrome.exe", title="foo/bar", pid=1)

    post({"url": "https://github.com/foo/bar?token=SECRET", "title": "foo/bar"})
    tracker.tick()
    tracker._flush(closing=True)

    row = conn.execute("SELECT app, url, host FROM segments ORDER BY id DESC LIMIT 1").fetchone()
    results.append(check("url attached to browser segment", row["url"], "https://github.com/foo/bar"))
    results.append(check("host attached", row["host"], "github.com"))

    tracker_mod.foreground_window = lambda: Window(app="Code.exe", exe="C:/Code.exe", title="main.py", pid=2)
    tracker.tick()
    tracker._flush(closing=True)
    row = conn.execute("SELECT app, url FROM segments ORDER BY id DESC LIMIT 1").fetchone()
    results.append(check("non-browser segment gets no url", row["url"], None))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
