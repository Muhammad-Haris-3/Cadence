# System Architecture & Live Schema

**Project Name:** cadence
**Architecture Pattern:** Local-first monorepo
**Tech Stack:** Python 3.13, SQLite, FastAPI (loopback only), Chrome MV3 extension

## 1. Repository Layout

- `/daemon`: Python application responsible for sampling the foreground window,
  measuring idle and input, persisting segments, receiving browser tab reports,
  categorizing, sessionizing, and reporting.
- `/extension`: Unpacked Chrome MV3 extension that reports the active tab to the
  daemon over loopback.
- `/docs`: Product, design, and architecture reference documents.

## 2. Runtime Architecture

The system is a single process with two threads and one file.

- **Main thread -- the sampler.** Wakes once per `POLL_SECONDS`, asks Windows
  which window holds foreground and how long since the last input, and folds the
  answer into the open segment. Owns all database writes.
- **Daemon thread -- the ingest server.** A FastAPI application bound to
  `127.0.0.1` receiving active-tab reports from the browser extension. Owns no
  database access; it updates one in-memory slot that the sampler reads.
- **SQLite** is the sole source of truth, in WAL mode so a dashboard or an ad-hoc
  query can read while the sampler writes.

There is no server, no account, and no network egress. The only listening socket
is on loopback.

## 3. Data Flow

1. The sampler reads `GetForegroundWindow`, resolves the owning process via
   `psutil`, and reads `GetLastInputInfo` for idle time.
2. A change of window, title, or idle state closes the open segment and opens a
   new one. Otherwise the tick accumulates into the current segment.
3. When the foreground process is a known browser, the sampler reads the most
   recent tab report and attaches its URL and host, provided that report is
   still within `TAB_MAX_AGE_SECONDS`.
4. The open segment is written back to disk every `FLUSH_SECONDS` and on close.
5. On demand, categorization and sessionizing recompute derived state from the
   segments table.

## 4. Live Database Schema

### `segments`

One contiguous stretch of time on a single window. The authoritative table.

- `id` (INTEGER, primary key)
- `started_at` (TEXT, ISO8601 local, required)
- `ended_at` (TEXT, nullable -- NULL while the segment is open)
- `day` (TEXT, YYYY-MM-DD, required, indexed)
- `app` (TEXT, required) -- process name, or the sentinels `__idle__` / `__locked__`
- `exe` (TEXT, nullable)
- `title` (TEXT, defaults to empty)
- `url` (TEXT, nullable) -- sanitized, supplied by the extension
- `host` (TEXT, nullable, indexed)
- `is_idle` (INTEGER, default 0)
- `duration_sec` (REAL) -- wall clock the window held foreground
- `active_sec` (REAL) -- that time minus idle stretches
- `input_sec` (REAL) -- seconds in which input occurred
- `category` (TEXT, nullable) -- derived
- `session_id` (INTEGER, nullable, indexed) -- derived
- Unique constraint on (`started_at`, `app`, `title`)

### `sessions`

A block of work as it was actually lived. Fully derived: it can be dropped and
rebuilt from `segments` at any time.

- `id` (INTEGER, primary key)
- `started_at` / `ended_at` (TEXT, required)
- `day` (TEXT, required, indexed)
- `duration_sec` / `active_sec` / `input_sec` (REAL)
- `category` (TEXT) -- dominant category by duration
- `top_app` / `top_title` (TEXT)
- `switches` (INTEGER) -- window changes within the block
- `interruptions` (INTEGER) -- brief off-category excursions absorbed into the block
- `focus_score` (REAL) -- 0-100 heuristic

## 5. Idle and Absence Handling

Idle time is attributed to a dedicated `__idle__` bucket rather than to whichever
window happened to hold foreground when the user walked away. A locked
workstation records as `__locked__`. This keeps per-application totals honest:
an editor left open overnight accrues nothing.

## 6. Sessionizing Rules

Segments fragment on every tab and file switch, so a two-hour block of work
arrives as hundreds of rows. Three rules reassemble it:

1. **Idle gaps.** A gap of at least `IDLE_BREAK_SECONDS` ends the session.
   Shorter gaps are absorbed -- thinking and reading are part of the work.
2. **Category change.** A sustained change of dominant category ends the
   session. An excursion shorter than `MIN_SWITCH_SECONDS` is instead recorded
   as an interruption inside it, so a brief message check does not split an hour
   of work into two.
3. **Day boundary.** A session never straddles two days, so daily rollups stay
   honest.

Rebuilding is a pure function of the segments table and is idempotent -- the
day's sessions are deleted and recomputed, so editing a rule reprocesses history
rather than applying only to new data.

## 7. Focus Score

A 0-100 heuristic, deliberately documented as such rather than presented as a
measurement. Three factors multiply:

- **presence** -- `active_sec / duration_sec`: how much of the block the user was
  at the machine at all.
- **engagement** -- `input_sec / active_sec`, weighted at half: reading
  documentation is real work with almost no keyboard input, and a score that
  called it slacking off would be wrong in the case most worth measuring
  honestly.
- **continuity** -- measured against `SWITCH_TOLERANCE` rather than against zero
  switching. Bouncing between an editor, a terminal, and a doc page is what
  development looks like; an earlier revision penalised every alt-tab equally
  and scored genuine work in the single digits.

## 8. Browser Tab Ingest

- **Endpoint:** `POST http://127.0.0.1:8765/tab`, loopback only.
- **Payload:** active tab URL, title, and whether the browser currently holds focus.
- **Authentication:** a shared token generated on first run, stored at
  `~/.cadence/extension_token.txt`, and sent in the `X-Cadence-Token` header.
  A custom header forces a CORS preflight that a hostile page cannot satisfy.
  Any `Origin` that is not `chrome-extension://` is rejected.
- **Freshness:** MV3 service workers are terminated when idle, so the extension
  cannot run its own timer. Browser events wake it on tab and focus changes, and
  a 30-second alarm heartbeats through long stretches on one tab. Any report
  older than `TAB_MAX_AGE_SECONDS` is treated as unknown rather than as still
  current -- a URL pinned to the wrong window is worse than an empty column.

### URL sanitizing

Query strings are stripped before storage, because that is where reset tokens,
session identifiers, and search terms live. Only allowlisted content identifiers
survive -- YouTube's `v` and `list`, for example. Non-HTTP schemes (`chrome://`,
`file://`, `devtools://`) are never recorded. The window title already carries
the human-readable subject, which is what categorization needs.

## 9. Migration Strategy

`db.migrate()` runs on every connect and applies additive migrations only --
`ALTER TABLE ... ADD COLUMN` guarded by a `PRAGMA table_info` check. Because
sessions and categories are derived, no data migration is required when their
rules change; the affected days are simply recomputed.

## 10. Privacy Boundary Implemented in Code

- `win_probe.py` reads window metadata and the *timestamp* of the last input.
  There is no keyboard hook, and keystroke content is not obtainable from the
  data captured.
- `urls.py` removes credential-bearing query parameters before any URL reaches
  the database.
- `ingest.py` binds to loopback, requires a token, and enforces an origin
  allowlist.
- The database and the pairing token live under `~/.cadence/` and are excluded
  from version control.
