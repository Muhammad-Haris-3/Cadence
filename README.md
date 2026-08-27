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

## Layout

```
daemon/
  cadence/
    config.py      paths, poll interval, idle threshold
    win_probe.py   the Win32 calls (foreground window, idle time)
    db.py          SQLite schema and access
    tracker.py     the sampling loop
    categories.py  app/title -> category rules
  main.py          start tracking
  report.py        daily breakdown
docs/
```

## Roadmap

- [x] Foreground window + idle sampling into SQLite
- [x] Rule-based categorization and a daily terminal report
- [ ] Chrome extension reporting the active tab URL to localhost
- [ ] Sessionizer: merge fragmented segments into meaningful work blocks
- [ ] FastAPI on 127.0.0.1 + Next.js dashboard (design carried over from core_tracker)
- [ ] Tray app and autostart via Task Scheduler
- [ ] AI daily summary (read the DB from Claude Code -- free -- or a nightly API call)
