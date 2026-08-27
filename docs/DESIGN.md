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
- **The local dashboard**, served by the daemon at `127.0.0.1:8765`, inherits
  the core-tracker design system wholesale -- palette, typography, spatial
  rhythm -- so the two projects feel like one body of work. It is a single
  static page rather than a Next.js application: the design system is CSS
  variables and web fonts, which need no component framework, and a tracker that
  runs continuously should not need a second process started before its own data
  can be read.

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

## 5. Dashboard Conventions

The dashboard obeys the terminal report's hierarchy and adds the affordances a
screen allows.

- **The day band** is the one element with no terminal equivalent: a full
  24-hour strip with each session positioned by its true clock offset, so the
  shape of the day is legible before a single number is read. Gaps are left
  empty rather than filled with grey -- absence is shown by absence.
- **Category color appears only in data.** Dots, band blocks, and meter fills
  carry it; headings, borders, and body text never do.
- **Meters over bars.** A 4px rule with a colored fill, not a chart. The number
  sits beside it in muted text, because the figure is the fact and the meter is
  only the shape of it.
- **Tabular figures everywhere** (`font-variant-numeric: tabular-nums`), with
  numeric columns right-aligned and text columns left-aligned, so durations form
  a readable column rather than a ragged one.
- **Long titles truncate with an ellipsis** and keep their full text in the
  native tooltip. A window title must never be allowed to reflow the table.
- **Section omission over empty state.** A section with no data is not rendered
  at all; only the sessions list, which is the point of the page, states its
  own absence in the display face.
- **Quiet liveness.** Today's view refetches on a slow interval with no spinner,
  no flash, and no "last updated" chrome. Historical days do not poll.
- **Keyboard first.** Left and right arrows move between days; forward is
  disabled on today rather than hidden, so the boundary is visible.

## 6. Tray Icon

The only surface visible while you work, so it says exactly one thing: whether
tracking is on.

- **The mark** is three bars of rising height -- the three clocks -- drawn at
  64px and downscaled by the shell. No glyph, no letterform, nothing that needs
  to survive antialiasing at 16px.
- **State is carried by ink, not by badge.** Active is `--text-primary` charcoal;
  paused is muted stone, the same value used for secondary text. A paused
  tracker should look dimmed, not alarmed.
- **The tooltip states the state in words** ("Cadence - tracking" /
  "Cadence - paused"), because a color difference alone is not readable to
  everyone.
- **Double-click opens the dashboard.** The most common intent should not
  require reading a menu.

## 7. Information Hierarchy

The report is ordered by how a person actually asks about their day.

1. **Sessions** -- the day as blocks of work. The headline, because it is the
   only view that matches lived experience.
2. **Categories** -- where the hours went, with engagement alongside duration so
   screen time is never mistaken for work.
3. **Top windows** -- the drill-down, for when a category total is surprising.
4. **Top sites** -- the browser drill-down, present only when tab data exists.

Absence of data is rendered as absence, not as zero. A section with nothing to
report is omitted rather than shown empty.

## 8. Tone of Reported Numbers

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
- **Say what the score is not.** The dashboard footer states in plain words that
  focus is a heuristic and not a measure of worth. A number this easy to
  over-read must carry its own disclaimer on the page, not only in the docs.

## 9. Extension Options Screen Pattern

The one browser-facing surface follows the same restraint.

- **Structure:** single narrow column, no cards, generous vertical rhythm.
- **Controls:** underline-adjacent inputs with minimal borders; one primary action.
- **Feedback:** inline single-line status beneath the action, in success green or
  error red, never a modal or a toast.
- **Theme:** `color-scheme: light dark` so it follows the browser rather than
  imposing a background.
- **Copy:** states plainly what is transmitted and where it goes. A tool that
  reads your tabs earns trust by being explicit, not by being quiet.
