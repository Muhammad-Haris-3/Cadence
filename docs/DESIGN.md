# UI/UX Design System & Aesthetic Guidelines

**Project Name:** cadence
**Aesthetic Direction:** Editorial / Zen Minimalism (continuous with core-tracker)
**Core Philosophy:** The report should read like a page from a notebook, not like
a dashboard. A tracker that quantifies your day must not also shout at you about
it. Restraint is the point: the numbers are uncomfortable enough on their own.

## 1. Surfaces

Cadence has two presentation surfaces, and they share one voice.

- **The terminal report** (`report.py`) is the MVP surface and remains the
  fastest path to the data. It must stay readable in a plain console with no
  color support.
- **The local dashboard** (planned) inherits the core-tracker design system
  wholesale -- palette, typography, spatial rhythm -- so the two projects feel
  like one body of work.

## 2. Color Palette (CSS Variables)

Carried over unchanged from core-tracker, avoiding pure black and pure white.

- `--bg-primary`: `#F5F5F4` (Warm Off-White / Stone 50) - the main canvas.
- `--text-primary`: `#1C1917` (Soft Charcoal / Stone 900) - readable without optical strain.
- `--text-secondary`: `#78716C` (Muted Stone / Stone 500) - timestamps and meta-information.
- `--border-subtle`: `#E7E5E4` (Stone 200) - dividing lines, used sparingly.

Cadence adds a semantic set for categories. These are the only saturated colors
in the system and they appear exclusively in data visualization, never in chrome.

- `--cat-code`: deep indigo - focused production work.
- `--cat-learning`: calm teal - documentation and study.
- `--cat-comms`: muted amber - messages and meetings.
- `--cat-distraction`: dusty rose, never alarm red - the tool reports, it does not scold.
- `--cat-idle`: `--text-secondary` - absence is absence, not a category.

## 3. Typography System

The dual-font strategy from core-tracker, with the balance shifted toward the
functional face because Cadence is denser with figures.

- **Display / Accent Font:** `Caveat` or `Kalam`
  - **Usage:** the day heading and section labels only.
  - **Purpose:** notebook warmth against otherwise numeric content.
- **Body / Functional Font:** `IBM Plex Mono` or `Geist Mono`
  - **Usage:** all durations, scores, session tables, and application names.
  - **Purpose:** tabular figures must align vertically. Proportional fonts are
    disqualified for any column of numbers.

## 4. Terminal Report Conventions

The terminal surface has its own constraints and they are binding.

- **Two-space left gutter** on every line. The report should never touch the
  edge of the console.
- **62-character rules** (`-`) beneath section headings; no box drawing, no
  Unicode frames -- they break in consoles that lack the font.
- **Right-aligned numeric columns**, left-aligned text columns. Always.
- **ASCII bars** (`#`) for engagement, scaled at one character per five percent.
  No block-drawing characters.
- **Durations degrade gracefully:** seconds below a minute, `Xm SSs` below an
  hour, `Xh MMm` above. A fresh database of short segments must not render as a
  column of `0m`.
- **UTF-8 output with replacement.** Window titles carry emoji and non-Latin
  script while the Windows console defaults to cp1252; one exotic tab title must
  never be able to kill the report.

## 5. Information Hierarchy

The report is ordered by how a person actually asks about their day.

1. **Sessions** -- the day as blocks of work. The headline, because it is the
   only view that matches lived experience.
2. **Categories** -- where the hours went, with engagement alongside duration so
   screen time is never mistaken for work.
3. **Top windows** -- the drill-down, for when a category total is surprising.
4. **Top sites** -- the browser drill-down, present only when tab data exists.

Absence of data is rendered as absence, not as zero. A section with nothing to
report is omitted rather than shown empty.

## 6. Tone of Reported Numbers

- **Report, never scold.** No red, no warnings, no streak-breaking language, no
  goals the user did not set. The distraction category is styled as calmly as
  the code category.
- **Name heuristics as heuristics.** The focus score is a derived opinion, and
  documentation and UI must both say so. It is never labelled "productivity."
- **Interruptions are counted, not judged.** `(+3 interruptions)` is a fact
  about the session, presented without adjective.
- **Show the working.** Every derived number must be traceable to the segments
  behind it, so a surprising figure can be investigated rather than merely
  disbelieved.

## 7. Extension Options Screen Pattern

The one browser-facing surface follows the same restraint.

- **Structure:** single narrow column, no cards, generous vertical rhythm.
- **Controls:** underline-adjacent inputs with minimal borders; one primary action.
- **Feedback:** inline single-line status beneath the action, in success green or
  error red, never a modal or a toast.
- **Theme:** `color-scheme: light dark` so it follows the browser rather than
  imposing a background.
- **Copy:** states plainly what is transmitted and where it goes. A tool that
  reads your tabs earns trust by being explicit, not by being quiet.
