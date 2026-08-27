# UI/UX Design System & Aesthetic Guidelines

**Project Name:** cadence
**Aesthetic Direction:** Two philosophies, switchable at runtime
**Core Philosophy:** A tracker that quantifies your day must not also shout at
you about it. That conviction produced **Editorial**, the default. But restraint
is a preference, not a truth, and some days you want the instrument panel rather
than the notebook -- so **Studio** sits beside it, one click away, and the choice
is remembered.

## 1. Surfaces

Cadence has two presentation surfaces, and they share one voice.

- **The terminal report** (`report.py`) is the MVP surface and remains the
  fastest path to the data. It must stay readable in a plain console with no
  color support.
- **The local dashboard**, served by the daemon at `127.0.0.1:8765`, offers both
  philosophies and both light and dark. It is installable as a desktop app, so it
  can live in the taskbar with its own window and icon. It inherits
  the core-tracker design system wholesale -- palette, typography, spatial
  rhythm -- so the two projects feel like one body of work. It is a single
  static page rather than a Next.js application: the design system is CSS
  variables and web fonts, which need no component framework, and a tracker that
  runs continuously should not need a second process started before its own data
  can be read.

## 2. The Two Philosophies

| | Editorial (default) | Studio |
| --- | --- | --- |
| Canvas | warm off-white / warm charcoal | cool slate / near-black navy |
| Structure | rules and negative space | cards with radius and shadow |
| Type | Caveat display, IBM Plex Mono body | Inter throughout, mono for figures |
| Headings | small, uppercase, tracked | larger, sentence case, semibold |
| Category color | muted, restrained | saturated, confident |
| App icons | hidden -- the dot suffices | real icons, extracted from the executables |
| Feels like | a notebook page | an instrument panel |

**They share one stylesheet, one set of rules, and identical markup.** Every
structural difference is expressed as a variable rather than as a rule:

```
section { background: var(--surface); border-radius: var(--radius);
          box-shadow: var(--shadow); padding: var(--card-pad); }
```

Editorial sets `--surface: transparent`, `--radius: 0`, `--shadow: none`,
`--card-pad: 0`, and the card vanishes into flat editorial layout. Studio gives
them real values and the same element becomes a card. Nothing is duplicated and
nothing is conditionally rendered.

This is the rule for any future work here: **if a philosophy needs a new
structural difference, add a token, not a branch.** The moment there are two
code paths, they drift.

State lives on the root element as `data-philosophy` and `data-mode`, is
persisted to `localStorage` behind try/catch, and defaults the mode from
`prefers-color-scheme` on a first visit.

## 3. Color Palette (CSS Variables)

Editorial carries the core-tracker palette over unchanged, avoiding pure black
and pure white. Studio uses a cooler slate family and permits pure white as a
card surface, since a card needs to lift off its canvas.

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

## 4. Typography System

The dual-font strategy from core-tracker, with the balance shifted toward the
functional face because Cadence is denser with figures.

- **Display / Accent Font:** `Caveat` or `Kalam`
  - **Usage:** the day heading and section labels only.
  - **Purpose:** notebook warmth against otherwise numeric content.
- **Body / Functional Font:** `IBM Plex Mono` or `Geist Mono`
  - **Usage:** all durations, scores, session tables, and application names.
  - **Purpose:** tabular figures must align vertically. Proportional fonts are
    disqualified for any column of numbers.

## 5. Terminal Report Conventions

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

## 6. Dashboard Conventions

The dashboard obeys the terminal report's hierarchy and adds the affordances a
screen allows.

- **The day band** is the one element with no terminal equivalent: a full
  24-hour strip with each session positioned by its true clock offset, so the
  shape of the day is legible before a single number is read. Gaps are left
  empty rather than filled with grey -- absence is shown by absence.
- **Category color appears only in data.** Dots, band blocks, and meter fills
  carry it; headings, borders, and body text never do. This holds in both
  philosophies -- Studio raises the saturation, not the surface area.
- **Application icons are the real ones**, extracted from each executable rather
  than matched from an icon pack, so an obscure tool is identified as accurately
  as a famous one. A binary with no extractable icon falls back to the category
  dot rather than to a generic placeholder.
- **An application is one row, whatever it was called.** A program appears once,
  under the name a person would use for it, with its total beside it. Repeating
  the same application down the page under its changing window titles describes
  the windows rather than the work.
- **Names come from the binaries**, the same way icons do: `WhatsApp.Root.exe`
  is not what anyone calls that program, and a lookup table would get the famous
  dozen right and mislabel everything else. Windows already stores the real name
  in the version resource, so it is asked; a filename is tidied only when the
  resource is missing.
- **A row opens into its own story.** Clicking an application reveals when it
  was picked up, how long each stretch lasted, and how long it was left alone in
  between -- the shape of a habit, which a single total cannot show. Breaks are
  drawn as indented space with no rule and no marker, so absence reads as
  absence here exactly as it does in the day band. What is open survives the
  refresh, since a poll that collapsed what you were reading would be worse than
  no poll at all.
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
- **An unreachable tracker names the fix.** The page is cached by the service
  worker, so it still renders when the daemon is down -- which is the only
  reason a person sees this state instead of a browser connection error. The
  lede therefore says what to do (start it from the tray, or `autostart.py
  start`) rather than asking a question the reader has no way to answer, and it
  keeps retrying so the page heals itself when the daemon comes back.

## 7. Tray Icon

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

## 8. The Written Summary

Prose among figures, so it is set apart by measure and rule rather than by a box.

- **A left rule, not a card.** Two pixels of `--border-subtle` and generous
  padding. The page has no boxes anywhere else and gains none here.
- **Prose measure**, capped near 62 characters, with relaxed line height. Full
  width is for tables; a paragraph read at table width is a paragraph nobody
  finishes.
- **Set in the functional face, not the display one.** Caveat is for headings and
  labels; several sentences of it would be charming once and tiring daily.
- **Attribution is always shown** -- "Written by Claude" or "Written by hand" --
  in the same muted label style as section headings. A reader should never have
  to wonder whether a judgement about their day was made by a person or a model.
- **It sits above the data**, because it is the interpretation the rest of the
  page supports, and it is omitted entirely when absent.

## 9. Information Hierarchy

The report is ordered by how a person actually asks about their day.

1. **Sessions** -- the day as blocks of work. The headline, because it is the
   only view that matches lived experience.
2. **Categories** -- where the hours went, with engagement alongside duration so
   screen time is never mistaken for work.
3. **Applications** -- the drill-down, for when a category total is surprising.
   Each opens into its own visits, which is where "why is that number so high"
   is actually answered.
4. **Top sites** -- the browser drill-down, present only when tab data exists.

Absence of data is rendered as absence, not as zero. A section with nothing to
report is omitted rather than shown empty.

## 10. Tone of Reported Numbers

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

## 11. Extension Options Screen Pattern

The one browser-facing surface follows the same restraint.

- **Structure:** single narrow column, no cards, generous vertical rhythm.
- **Controls:** underline-adjacent inputs with minimal borders; one primary action.
- **Feedback:** inline single-line status beneath the action, in success green or
  error red, never a modal or a toast.
- **Theme:** `color-scheme: light dark` so it follows the browser rather than
  imposing a background.
- **Copy:** states plainly what is transmitted and where it goes. A tool that
  reads your tabs earns trust by being explicit, not by being quiet.
