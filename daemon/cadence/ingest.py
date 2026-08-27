"""Localhost endpoint the browser extension reports the active tab to.

Runs on a daemon thread beside the sampler and owns one piece of shared state:
the most recently reported tab. The sampler reads it; nothing else writes it.

Two things guard the endpoint, because any local process -- including a web page
you happen to be visiting -- can reach a loopback port:

  1. A shared token in a custom header. A custom header forces a CORS preflight,
     which a hostile page cannot satisfy without knowing the token.
  2. An Origin allowlist: only chrome-extension:// origins (or no Origin at all,
     for curl and tests) are accepted.
"""

import socket
import threading
import time
from dataclasses import dataclass
from typing import Optional

import uvicorn
from fastapi import FastAPI, Header, HTTPException, Request
from pydantic import BaseModel

from . import config
from .urls import sanitize


@dataclass
class Tab:
    url: str
    host: str
    title: str
    reported_at: float

    def is_fresh(self, now: Optional[float] = None) -> bool:
        return (now or time.time()) - self.reported_at <= config.TAB_MAX_AGE_SECONDS


class TabState:
    """Thread-safe holder for the current tab."""

    def __init__(self):
        self._lock = threading.Lock()
        self._tab: Optional[Tab] = None

    def set(self, tab: Optional[Tab]) -> None:
        with self._lock:
            self._tab = tab

    def get_fresh(self) -> Optional[Tab]:
        with self._lock:
            tab = self._tab
        return tab if tab and tab.is_fresh() else None


STATE = TabState()


class TabReport(BaseModel):
    url: str = ""
    title: str = ""
    focused: bool = True


def build_app(token: str, state: TabState = STATE) -> FastAPI:
    app = FastAPI(title="Cadence ingest", docs_url=None, redoc_url=None)

    @app.post("/tab")
    def report_tab(
        report: TabReport,
        request: Request,
        x_cadence_token: str = Header(default=""),
    ):
        if x_cadence_token != token:
            raise HTTPException(status_code=401, detail="bad token")

        origin = request.headers.get("origin", "")
        if origin and not origin.startswith("chrome-extension://"):
            raise HTTPException(status_code=403, detail="bad origin")

        # Chrome lost focus, or the tab isn't a trackable page: report nothing
        # rather than letting the last known tab go stale in place.
        if not report.focused:
            state.set(None)
            return {"ok": True, "tracked": False}

        url, host = sanitize(report.url)
        if not url:
            state.set(None)
            return {"ok": True, "tracked": False}

        state.set(Tab(url=url, host=host, title=report.title or "", reported_at=time.time()))
        return {"ok": True, "tracked": True, "host": host}

    @app.get("/health")
    def health():
        tab = state.get_fresh()
        return {"ok": True, "current_host": tab.host if tab else None}

    return app


def port_in_use() -> bool:
    """Whether another Cadence already holds the port.

    Two samplers on one database would double-count every second, so both entry
    points check this before starting anything.
    """
    probe = socket.socket()
    try:
        probe.bind((config.INGEST_HOST, config.INGEST_PORT))
        return False
    except OSError:
        return True
    finally:
        probe.close()


def server_config(token: str, app=None) -> uvicorn.Config:
    """Built separately from the server so it can be constructed in a test
    without binding the port -- constructing it is where Cadence used to die."""
    return uvicorn.Config(
        app or build_app(token),
        host=config.INGEST_HOST,
        port=config.INGEST_PORT,
        log_level="warning",
        # Uvicorn's own logging config must not be installed. Building it calls
        # sys.stdout.isatty() to decide about colour, and under pythonw.exe --
        # which is how the logon task starts us -- sys.stdout is None. That
        # raised right here, before the tray icon or the sampler existed, and
        # killed the process silently at every single logon. None leaves
        # uvicorn on the handlers cadence.logs has already set up.
        log_config=None,
    )


def serve_in_background(token: str, app=None) -> threading.Thread:
    """Run the HTTP server on a daemon thread. `app` defaults to ingest alone;
    main.py passes the dashboard app, which wraps it."""
    server = uvicorn.Server(server_config(token, app))
    # uvicorn installs signal handlers on startup, which only works on the main
    # thread; the tracker owns those.
    server.install_signal_handlers = lambda: None

    thread = threading.Thread(target=server.run, daemon=True, name="cadence-ingest")
    thread.start()
    return thread
