# Product Requirements Document (PRD)

**Project Name:** cadence
**Phase:** MVP (Minimum Viable Product) Core Definition
**Architecture Style:** Local-first (Python daemon / SQLite / local dashboard)
**Design Language:** Editorial / Zen Minimalism (inherited from core-tracker)

## 1. Problem Statement & Objective

**The Problem:** Manual time tracking fails for the same reason manual habit
logging does -- it demands the discipline it is supposed to measure. Automatic
trackers solve that, but the mature ones (Rize, RescueTime, Timing) are
subscription products built for teams: they route personal activity through a
vendor's cloud, price per seat, and optimise for manager-facing reporting rather
than self-knowledge. Worse, every one of them reports *screen time* as though it
were *work* -- an editor left open on a second monitor scores identically to an
hour of actual thinking.

**The Objective:** To engineer a fully local automatic time tracker for a single
Windows machine that answers one question the paid tools answer poorly: was that
a real working session, or was the window merely open? The system must capture
activity silently and continuously with zero user interaction, distinguish
presence from engagement, and cost nothing to run.

## 2. Target Audience (User Personas)

**The Single Operator (the author):** One developer, one machine, no team. Values
data ownership absolutely -- activity data is not to leave the device under any
circumstance. Technically capable of editing rule files rather than needing a
settings UI. Wants insight into personal focus patterns, not billable-hour
reports or client invoicing.

Explicitly *not* built for: teams, clients, managers, or public distribution.
Those constraints may be revisited if the project is ever open-sourced.

## 3. Core Data Strategy (The Three Clocks)

Every recorded segment carries three independent time measurements. The gaps
between them are the product.

- `duration_sec` (Real): wall clock during which the window held foreground.
- `active_sec` (Real): that time minus stretches where input had gone quiet
  past the idle threshold.
- `input_sec` (Real): seconds in which keyboard or mouse input actually occurred.

Supporting fields captured per segment:

- `id` (Integer): Primary Key
- `started_at` / `ended_at` (Text, ISO8601 local): segment bounds
- `day` (Text, YYYY-MM-DD): denormalised for cheap daily rollups
- `app` (Text): foreground process name
- `exe` (Text): full executable path
- `title` (Text): window title
- `url` / `host` (Text): active tab, supplied by the browser extension
- `is_idle` (Boolean): whether the segment represents absence
- `category` (Text): derived from rules, recomputed on demand
- `session_id` (Integer): the work block this segment was grouped into

**Privacy boundary (non-negotiable):** The system captures window *metadata* and
the *presence* of input. It must never capture keystroke content. There is no
keyboard hook in the codebase and none may be added.

## 4. Feature Prioritization (MoSCoW Method)

### Must-Have (Critical for MVP)

- Background sampler capturing foreground window and idle state without user interaction.
- Three-clock measurement distinguishing screen time from engaged time.
- Local SQLite persistence with no network dependency.
- Browser extension supplying active tab URL and title, with credential-bearing
  query strings stripped before storage.
- Rule-based categorization that is inspectable and editable as source.
- Sessionizer grouping fragmented segments into work blocks as they were lived.
- Daily terminal report.

### Should-Have (Important, target for launch)

- Local web dashboard reusing the core-tracker editorial design language.
- Tray application with autostart, so tracking requires no daily action.
- Focus-score trend over time rather than per-day only.

### Could-Have (Future Scope / V2)

- AI daily summary, via a Claude Code session reading the database directly
  (no marginal cost) or a scheduled API call.
- Distraction blocking during declared focus sessions.
- Screen-text capture via the Windows OCR API for finer activity classification.
- Calendar correlation to separate meetings from solo work.

### Won't-Have (Out of scope for MVP)

- Any cloud sync, hosted account, or off-device transmission of activity data.
- Multi-user support, teams, roles, or sharing.
- Client billing, invoicing, or profitability reporting.
- Mobile or macOS builds.
- Chrome Web Store distribution (the extension is loaded unpacked).

## 5. User Stories

- **Story 1:** As the operator, I want tracking to run without my touching it, so
  the data is complete rather than reflecting only the days I remembered.
- **Story 2:** As the operator, I want a window left open while I am away to be
  recorded as absence, so my totals are not flattered by idle time.
- **Story 3:** As the operator, I want to know whether a browser hour was
  documentation or distraction, so "3h in Chrome" becomes actionable.
- **Story 4:** As the operator, I want my day expressed as a handful of work
  blocks rather than hundreds of window switches, so the report matches how I
  actually experienced the day.
- **Story 5:** As the operator, I want a brief message check inside an hour of
  work recorded as an interruption within that hour, not as a boundary that
  splits it in two.
- **Story 6:** As the operator, I want reading documentation to score as real
  work despite low keyboard input, so the focus metric does not quietly punish
  thinking.
- **Story 7:** As the operator, I want to edit the categorization rules as plain
  source and recompute history, so the system never becomes an opaque oracle.

## 6. Non-Functional Requirements

- **Cost:** The system must be buildable and operable at zero recurring cost. Any
  paid component (an LLM summary) must be strictly optional with a free path.
- **Privacy:** No activity data leaves the machine. The ingest endpoint binds to
  loopback only, is guarded by a shared token in a custom header, and rejects
  non-extension origins. Keystroke content is never captured.
- **Performance:** The sampler must be negligible against a development
  workload -- a one-second poll of a few Win32 calls, with database writes
  batched to the flush interval rather than per tick.
- **Durability:** An unclean shutdown may lose at most one flush interval.
  Segments left open by a crash are closed on next start rather than bleeding
  time into the following session.
- **Derivability:** Sessions and categories are derived artefacts, never
  authoritative. Both must be reproducible from the segments table alone so that
  changing a rule reprocesses history instead of only affecting new data.
- **Maintainability:** Categorization and sessionizing thresholds live in named
  configuration constants, not inline literals.
