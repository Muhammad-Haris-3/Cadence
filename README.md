# Cadence

A personal automatic time tracker for Windows. Rize-style, single user, runs
entirely on this machine. No account, no cloud, no subscription.

## What it does

A background sampler asks Windows what window is in front and whether any input
happened, once a second, and folds that into contiguous *segments*. Every
segment carries three clocks:

| clock | meaning |
|---|---|
| `duration_sec` | the window was in front |
| `active_sec`   | ...and input had not gone quiet |
| `input_sec`    | ...and input actually happened that second |

The gap between them is the whole point. A YouTube tab left playing accrues
duration and nothing else; a real coding session accrues all three.

## Privacy

The tracker reads **window metadata only** -- process name and window title --
plus a boolean "was there input this second". There is no keyboard hook and
there must never be one; keystroke *content* is never read, stored, or derivable
from the database. Everything is written to a single SQLite file under
`~/.cadence/`, which is gitignored. Nothing leaves the machine.

## Run it

```
cd daemon
py -m venv .venv
.venv\Scripts\pip install -r requirements.txt
.venv\Scripts\pythonw tray_app.pyw
```

That puts an icon in the tray: three bars, charcoal while tracking and muted
while paused. Double-click opens the dashboard; right-click pauses or quits.

To start it automatically with Windows:

```
.venv\Scripts\python autostart.py install
```

If your machine's policy blocks creating scheduled tasks, use the mechanism that
needs no elevation instead:

```
.venv\Scripts\python autostart.py install startup
```

`autostart.py status` shows what is registered, and `autostart.py uninstall`
removes it. Only one instance can run at a time -- a second refuses to start
rather than counting every second twice.

To run in the foreground with a console instead, use `.venv\Scripts\python main.py`.

The dashboard is then at **http://127.0.0.1:8765/** for as long as the daemon
runs -- no build step, no second process. Arrow keys move between days.

Or, in the terminal:

```
.venv\Scripts\python report.py            # today
.venv\Scripts\python report.py 2026-08-26 # any day
```

Categories are plain regex rules in `daemon/cadence/categories.py`. Edit them
and rerun the report -- it recategorizes from scratch every time.

## Browser tabs

Without this, every tab is just `chrome.exe` and a YouTube tutorial is
indistinguishable from a YouTube rabbit hole. The extension closes that gap.

1. Start the daemon (`python main.py`). It prints a pairing token on first run
   and saves it to `~/.cadence/extension_token.txt`.
2. Open `chrome://extensions`, turn on **Developer mode**, click **Load
   unpacked**, and choose the `extension/` folder.
3. Open the extension's **Details -> Extension options**, paste the token, and
   click **Save & test connection**.

It stays unpacked -- publishing to the Chrome Web Store costs $5 and there is
nobody to publish it to.

**What it sends:** the active tab's URL and title, to `127.0.0.1:8765` only.
Query strings are stripped before storage, since that is where reset tokens,
session ids and search terms live; the only exceptions are allowlisted content
identifiers like YouTube's `v` (see `daemon/cadence/urls.py`). Non-web schemes
(`chrome://`, `file://`) are never recorded.

**Why it is guarded:** any process on the machine can reach a loopback port,
including a web page you are visiting. The endpoint requires a token in a custom
header -- which forces a CORS preflight a hostile page cannot satisfy -- and
rejects any `Origin` that is not `chrome-extension://`.

**Firefox/Safari** would each need their own port of the extension; only
Chromium browsers are wired up.

## Daily summary

The free path is the default and the better one:

```
.venv\Scripts\python daily_summary.py
```

That prints a compact digest of the day, including how it compares with your
previous seven tracked days. Open Claude Code in this repo and ask it to
summarise -- it reads the database directly, costs nothing beyond a subscription
you already pay for, and you can ask follow-up questions, which a stored summary
can never answer. Save what it writes:

```
.venv\Scripts\python daily_summary.py --save     (reads stdin)
.venv\Scripts\python daily_summary.py --show
```

Saved summaries appear at the top of the dashboard, labelled with who wrote them.

**Optional, and the only part that can cost money:**

```
.venv\Scripts\pip install -r requirements-ai.txt
.venv\Scripts\python daily_summary.py --ai
```

This sends the digest to the Claude API and prints what it spent. A day is a few
thousand tokens, so it lands around a few cents on Opus and well under a cent on
Haiku (`--model claude-haiku-4-5`). The `anthropic` package is kept out of the
main requirements so a default install stays free.

## Layout

```
daemon/
  cadence/
    config.py      paths, poll interval, idle threshold
    win_probe.py   the Win32 calls (foreground window, idle time)
    db.py          SQLite schema and access
    tracker.py     the sampling loop
    urls.py        strips credentials out of reported URLs
    ingest.py      localhost endpoint the browser extension reports to
    categories.py  app/title -> category rules
    web.py         dashboard JSON API and page routes
    tray.py        tray icon, pause/resume, single-instance guard
    digest.py      compact a day, with a trailing baseline
    summary.py     summary storage and the optional API call
    static/        the dashboard page
  tray_app.pyw     everyday entry point, no console
  main.py          foreground entry point, with a console
  autostart.py     register or remove the logon task
  daily_summary.py digest, and the optional AI summary
  report.py        daily breakdown
  tests/           end-to-end ingest check
extension/         unpacked Chrome MV3 extension
docs/
```

## Roadmap

- [x] Foreground window + idle sampling into SQLite
- [x] Rule-based categorization and a daily terminal report
- [x] Chrome extension reporting the active tab URL to localhost
- [x] Sessionizer: merge fragmented segments into meaningful work blocks
- [x] Local dashboard at 127.0.0.1:8765, served by the daemon (design carried over from core_tracker)
- [x] Tray app and autostart via Task Scheduler
- [x] AI daily summary (read the DB from Claude Code -- free -- or an opt-in API call)
