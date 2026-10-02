"""End-to-end check: extension POST -> ingest -> tracker -> SQLite.

The requests are driven straight into the ASGI application rather than over a
socket. Binding the real port made this suite unrunnable whenever Cadence itself
was running -- the requests reached the live daemon, which holds a different
token, and every assertion failed with a 401 that looked like a broken test. The
whole contract under test (token, origin, validation, routing) lives in the app
object, so nothing is lost by leaving the network out of it.
"""

import json
import os
import sys
import tempfile
from pathlib import Path

import anyio

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-test-")

from cadence import config, db, ingest  # noqa: E402
from cadence.tracker import Tracker  # noqa: E402
from cadence.win_probe import Window  # noqa: E402

TOKEN = "test-token-abc"
APP = ingest.build_app(TOKEN)


def call(method, path, payload=None, headers=None):
    """Send one request through the ASGI app, in this process."""
    body = b"" if payload is None else json.dumps(payload).encode()
    raw_headers = [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()]
    if payload is not None:
        raw_headers.append((b"content-type", b"application/json"))
        raw_headers.append((b"content-length", str(len(body)).encode()))

    scope = {
        "type": "http",
        "asgi": {"version": "3.0", "spec_version": "2.3"},
        "http_version": "1.1",
        "method": method,
        "scheme": "http",
        "path": path,
        "raw_path": path.encode(),
        "query_string": b"",
        "root_path": "",
        "headers": raw_headers,
        "client": ("127.0.0.1", 0),
        "server": (config.INGEST_HOST, config.INGEST_PORT),
    }

    status, chunks = {}, []

    async def receive():
        return {"type": "http.request", "body": body, "more_body": False}

    async def send(message):
        if message["type"] == "http.response.start":
            status["code"] = message["status"]
        elif message["type"] == "http.response.body":
            chunks.append(message.get("body", b""))

    anyio.run(APP, scope, receive, send)

    raw = b"".join(chunks)
    # A rejection returns its detail as JSON too, but the callers only ever read
    # a body after a success, so mirror the old helper and hand back None.
    if status["code"] >= 400:
        return status["code"], None
    return status["code"], (json.loads(raw) if raw else None)


def post(payload, token=TOKEN, origin=None):
    headers = {"X-Cadence-Token": token}
    if origin:
        headers["Origin"] = origin
    return call("POST", "/tab", payload, headers)


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {label}" + ("" if got == want else f"  (got {got!r}, want {want!r})"))
    return got == want


def main():
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

    print("\nwatching vs idle")
    tracker_mod.idle_millis = lambda: 10 * 60 * 1000  # no input for ten minutes
    tracker_mod.foreground_window = lambda: Window(app="chrome.exe", exe="C:/chrome.exe", title="video", pid=1)
    watcher = Tracker(conn, poll=1.0, idle_threshold=60, flush=999)

    post({"url": "https://www.youtube.com/watch?v=abc", "title": "video", "audible": True})
    watcher.tick()
    watcher._flush(closing=True)
    row = conn.execute("SELECT app, is_idle, host FROM segments ORDER BY id DESC LIMIT 1").fetchone()
    results.append(check("a playing video with no input is watching", (row["app"], row["is_idle"]), ("chrome.exe", 0)))
    results.append(check("and it's YouTube time", row["host"], "www.youtube.com"))

    post({"url": "https://www.youtube.com/watch?v=abc", "title": "video", "audible": False})
    watcher.tick()
    watcher._flush(closing=True)
    row = conn.execute("SELECT app, is_idle FROM segments ORDER BY id DESC LIMIT 1").fetchone()
    results.append(check("a silent tab with no input is idle", (row["app"], row["is_idle"]), ("__idle__", 1)))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
