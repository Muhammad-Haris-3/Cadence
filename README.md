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
.venv\Scripts\python main.py
```

Then, any time:

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
  main.py          start tracking (sampler + ingest)
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
- [ ] FastAPI on 127.0.0.1 + Next.js dashboard (design carried over from core_tracker)
- [ ] Tray app and autostart via Task Scheduler
- [ ] AI daily summary (read the DB from Claude Code -- free -- or a nightly API call)
