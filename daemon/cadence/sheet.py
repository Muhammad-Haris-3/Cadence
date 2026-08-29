"""The shared furniture of a printed report: page, palette, cursor, rollups.

A day report and a week report differ in what they put on the page, not in how
a page works. Both are the same paper, the same margins, the same colours as
the dashboard, the same rule about not orphaning a heading from its rows, and
the same two sentences at the end that have to travel with anything leaving
this machine. All of that lives here so the two reports cannot drift apart on
anything except the part that is genuinely different.

Knows about layout and about Cadence's palette. Knows nothing about PDF's
internals -- that is `pdf` -- and nothing about what a day or a week contains.
"""

from datetime import datetime

from . import pdf

MARGIN = 56.0
CONTENT_WIDTH = pdf.PAGE_WIDTH - MARGIN * 2
RIGHT = pdf.PAGE_WIDTH - MARGIN

# The first page gives the title block room; later pages start straight in.
TOP_FIRST = 92.0
TOP_CONTINUED = 64.0
BOTTOM = pdf.PAGE_HEIGHT - 64.0

INK = "#1C1917"
MUTED = "#78716C"
RULE = "#E7E5E4"
WASH = "#F5F5F4"

# The dashboard's category colours, so a report and the screen it came from are
# recognisably the same days.
CATEGORY_COLORS = {
    "code": "#4C4FA8",
    "learning": "#2F8F87",
    "docs": "#4F7CA8",
    "design": "#8A5CA8",
    "ai": "#7A6BA8",
    "comms": "#B98B3E",
    "distraction": "#B5697E",
    "browsing": "#7D8A97",
    "other": "#A8A29E",
    "idle": "#D6D3D1",
    "away": "#D6D3D1",
}

DAY_SECONDS = 24 * 3600


def color_for(category) -> str:
    return CATEGORY_COLORS.get(category or "other", CATEGORY_COLORS["other"])


def long_date(day: str) -> str:
    try:
        parsed = datetime.strptime(day, "%Y-%m-%d")
    except ValueError:
        return day
    # %-d and %#d disagree across platforms; strip the zero by hand instead.
    return parsed.strftime("%A, %d %B %Y").replace(" 0", " ", 1)


def clock(stamp) -> str:
    """The HH:MM out of an ISO timestamp, without reparsing it."""
    return (stamp or "")[11:16]


class Sheet:
    """A page with a cursor, which starts a new page when it runs out of room.

    Every section asks for the vertical space it needs *before* drawing any of
    it, so a heading can never be orphaned at the foot of a page from the rows
    it introduces.
    """

    def __init__(self, doc: pdf.Document):
        self.doc = doc
        self.y = TOP_FIRST

    def need(self, height: float) -> None:
        if self.y + height > BOTTOM:
            self.doc.new_page()
            self.y = TOP_CONTINUED

    # -- pieces ------------------------------------------------------------

    def heading(self, title: str) -> None:
        self.need(46)
        self.y += 12
        self.doc.text(MARGIN, self.y, title.upper(), "bold", 8, MUTED)
        self.y += 6
        self.doc.rule(MARGIN, self.y, RIGHT, RULE)
        self.y += 16

    def paragraph(self, body: str, size: float = 10, color: str = INK,
                  leading: float = 15.0) -> None:
        for line in pdf.wrap(body, "regular", size, CONTENT_WIDTH):
            self.need(leading)
            self.doc.text(MARGIN, self.y, line, "regular", size, color)
            self.y += leading

    def columns(self, cells, size: float = 8, font: str = "bold",
                color: str = MUTED) -> None:
        """One row of the little tables: (x, text, align) per cell."""
        for x, body, align in cells:
            if align == "right":
                self.doc.text_right(x, self.y, body, font, size, color)
            else:
                self.doc.text(x, self.y, body, font, size, color)


def meter(doc: pdf.Document, x: float, y: float, width: float, fraction: float,
          color: str, height: float = 3.0) -> None:
    """A share bar. The track is always drawn, so a row with almost nothing in
    it still reads as a row rather than as blank space."""
    doc.rect(x, y, width, height, RULE)
    doc.rect(x, y, max(width * min(max(fraction, 0.0), 1.0), 0.6), height, color)


def band(doc: pdf.Document, x: float, y: float, width: float, height: float,
         sessions: list) -> None:
    """One day drawn against a 24-hour axis.

    A two-minute session is a third of a point wide and would vanish, so the
    floor is a hairline: present, findable, and honest about being too small to
    measure by eye. The tables carry the number.
    """
    doc.rect(x, y, width, height, WASH)
    for session in sessions:
        start = session["offset_sec"] / DAY_SECONDS
        span = (session["duration_sec"] or 0) / DAY_SECONDS
        doc.rect(
            x + width * start, y,
            max(width * span, 0.8), height,
            color_for(session["category"]),
        )


def hour_axis(sheet: Sheet, x: float, width: float, step: int = 3) -> None:
    """The 00..24 ruler a band is read against."""
    doc = sheet.doc
    for hour in range(0, 25, step):
        at = x + width * (hour / 24.0)
        label = f"{hour:02d}"
        if hour == 0:
            doc.text(at, sheet.y, label, "mono", 7, MUTED)
        elif hour == 24:
            doc.text_right(at, sheet.y, label, "mono", 7, MUTED)
        else:
            doc.text_center(at, sheet.y, label, "mono", 7, MUTED)
    sheet.y += 8


def active_categories(rows: list):
    """The category rollup without idle and away, and how much that removed.

    The dashboard leaves both out of "where the time went" -- an afternoon the
    machine sat on the lock screen is not a category of work -- and a report
    that disagreed with the screen it came from would be worse than either
    choice. But leaving them out silently would let a mostly-idle week read as a
    busy one, so the caller is handed the number to say so with.
    """
    kept = [row for row in rows if row.get("category") not in ("idle", "away")]
    dropped = sum(
        row.get("duration_sec") or 0
        for row in rows
        if row.get("category") in ("idle", "away")
    )
    return kept, dropped


def share_table(page: Sheet, title: str, rows: list, label_of, color_of,
                key: str = "NAME", share_of: str = "SHARE", limit: int = 12,
                note: str = "") -> None:
    """The rollups at the foot of every report: the same table, different key.

    The denominator is the rollup's own total and cannot be passed in. It used
    to be, and a week whose idle time dwarfed its sessions came out at 164% --
    the rows were summing one thing and being divided by another. A share is
    always a share of what is in the table, so the table works it out.

    Truncation is announced rather than silent. A top-twelve that looks like the
    whole list is how a page ends up quietly lying about a long tail.
    """
    from .digest import fmt

    rows = [row for row in rows if row.get("duration_sec")]
    if not rows:
        return

    total = sum(row["duration_sec"] for row in rows)
    shown = rows[:limit]

    page.heading(title)
    time_x = MARGIN + 250
    bar_x = MARGIN + 262
    bar_width = 150.0

    page.columns([
        (MARGIN, key, "left"),
        (time_x, "TIME", "right"),
        (bar_x, share_of, "left"),
    ])
    page.y += 12

    for row in shown:
        page.need(16)
        doc = page.doc
        color = color_of(row)
        doc.rect(MARGIN, page.y - 5, 5, 5, color)
        doc.text(MARGIN + 9, page.y,
                 pdf.ellipsize(label_of(row), "regular", 9, time_x - MARGIN - 24),
                 "regular", 9, INK)
        doc.text_right(time_x, page.y, fmt(row["duration_sec"]), "mono", 8.5, INK)

        fraction = (row["duration_sec"] / total) if total else 0
        meter(doc, bar_x, page.y - 3, bar_width, fraction, color)
        doc.text(bar_x + bar_width + 8, page.y, f"{round(fraction * 100)}%",
                 "mono", 8, MUTED)
        page.y += 15

    footnotes = []
    if len(shown) < len(rows):
        footnotes.append(
            f"Showing the {len(shown)} largest of {len(rows)}; the rest come to "
            f"{fmt(total - sum(row['duration_sec'] for row in shown))}."
        )
    if note:
        footnotes.append(note)
    for line in footnotes:
        page.need(12)
        page.y += 2
        page.doc.text(MARGIN, page.y, line, "regular", 8, MUTED)
        page.y += 10


def footers(doc: pdf.Document, label: str) -> None:
    """Drawn last, on every page, because the total was not known until now."""
    total = doc.page_count
    baseline = pdf.PAGE_HEIGHT - 42
    for index in range(total):
        doc.current = index
        doc.rule(MARGIN, baseline - 12, RIGHT, RULE)
        doc.text(MARGIN, baseline, f"Cadence  -  {label}", "regular", 8, MUTED)
        doc.text_right(RIGHT, baseline, f"{index + 1} of {total}", "regular", 8, MUTED)


def closing_note(sheet: Sheet) -> None:
    """What the reader needs and the person exporting already knows.

    A report travels away from the machine that made it, to someone who did not
    install anything and has no reason to guess what was and was not recorded.
    Leaving these two out invites the page being read as a performance review,
    which is the one thing it is not.
    """
    sheet.need(46)
    sheet.y += 14
    sheet.doc.rule(MARGIN, sheet.y, RIGHT, RULE)
    sheet.y += 14
    for line in (
        "Recorded from window metadata only -- titles, applications and hostnames. "
        "No keystroke content was captured, and nothing left the machine this was "
        "recorded on.",
        "Focus is a heuristic built from presence, engagement and continuity. "
        "It is not a measure of worth.",
    ):
        sheet.paragraph(line, 8, MUTED, 11)
        sheet.y += 3
