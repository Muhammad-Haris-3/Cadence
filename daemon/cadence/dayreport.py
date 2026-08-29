"""One day, laid out as a shareable PDF.

The dashboard is for you; this is for someone else. That difference decides
what goes on the page. Anything that only makes sense while you are clicking it
is gone -- the philosophy switch, the day arrows, the expandable app rows -- and
what remains is the part a colleague could read cold: what the day was made of,
in what order, and how much of it was what.

Two things are stated on the page rather than left to be assumed, because the
report travels away from the machine that made it and the person reading it did
not install anything: that only window metadata was ever recorded, and that the
focus number is a heuristic. A report that leaves those out invites being read
as a productivity score, which is the one thing it is not.

Built on `pdf`, which knows about baselines and rectangles and nothing about
Cadence.
"""

from datetime import datetime

from . import config, pdf
from .digest import fmt

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
# recognisably the same day.
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

    def gap(self, height: float) -> None:
        self.y += height

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


def _bar(doc: pdf.Document, x: float, y: float, width: float, fraction: float,
         color: str) -> None:
    """A share-of-the-day meter. The track is always drawn, so a row with
    almost nothing in it still reads as a row rather than as blank space."""
    doc.rect(x, y, width, 3, RULE)
    doc.rect(x, y, max(width * min(max(fraction, 0.0), 1.0), 0.6), 3, color)


# -- the sections -------------------------------------------------------------


def title_block(sheet: Sheet, payload: dict) -> None:
    doc = sheet.doc
    doc.text(MARGIN, 62, "Cadence", "bold", 22, INK)
    doc.text_right(RIGHT, 62, long_date(payload["day"]), "regular", 10, MUTED)
    doc.rule(MARGIN, 74, RIGHT, RULE)

    stats = payload["summary"]
    sheet.y = TOP_FIRST + 6
    if stats["sessions"]:
        line = (
            f"{stats['sessions']} sessions  -  {fmt(stats['blocks_sec'])} in blocks"
            f"  -  longest {fmt(stats['longest_sec'])}"
        )
    else:
        line = "Nothing tracked on this day."
    doc.text(MARGIN, sheet.y, line, "bold", 13, INK)
    sheet.y += 10

    if stats["tracked_sec"]:
        detail = (
            f"{fmt(stats['tracked_sec'])} at the machine, "
            f"{fmt(stats['active_sec'])} of it active, "
            f"{fmt(stats['input_sec'])} with input."
        )
        sheet.y += 12
        doc.text(MARGIN, sheet.y, detail, "regular", 9.5, MUTED)
        sheet.y += 6


def narrative(sheet: Sheet, payload: dict) -> None:
    if not payload.get("written"):
        return
    sheet.heading("the day in words")
    sheet.paragraph(payload["written"], 10.5, INK, 15.5)
    source = payload.get("written_source")
    if source:
        sheet.y += 2
        sheet.doc.text(MARGIN, sheet.y, f"Written by: {source}", "regular", 8, MUTED)
        sheet.y += 10


def timeline(sheet: Sheet, payload: dict) -> None:
    sessions = payload["sessions"]
    if not sessions:
        return

    sheet.heading("the shape of it")
    band_height = 34.0
    sheet.need(band_height + 22)

    doc, top = sheet.doc, sheet.y
    doc.rect(MARGIN, top, CONTENT_WIDTH, band_height, WASH)

    for session in sessions:
        start = session["offset_sec"] / DAY_SECONDS
        span = (session["duration_sec"] or 0) / DAY_SECONDS
        # A two-minute session is a third of a point wide and would vanish; a
        # hairline is a truthful floor, and the table below carries the number.
        doc.rect(
            MARGIN + CONTENT_WIDTH * start, top,
            max(CONTENT_WIDTH * span, 0.8), band_height,
            color_for(session["category"]),
        )

    sheet.y = top + band_height + 11
    for hour in range(0, 25, 3):
        x = MARGIN + CONTENT_WIDTH * (hour / 24.0)
        label = f"{hour:02d}"
        if hour == 0:
            doc.text(x, sheet.y, label, "mono", 7, MUTED)
        elif hour == 24:
            doc.text_right(x, sheet.y, label, "mono", 7, MUTED)
        else:
            doc.text_center(x, sheet.y, label, "mono", 7, MUTED)
    sheet.y += 8


def sessions_table(sheet: Sheet, payload: dict) -> None:
    sessions = payload["sessions"]
    if not sessions:
        return

    sheet.heading("sessions")
    start_x = MARGIN
    length_x = MARGIN + 108
    focus_x = MARGIN + 152
    category_x = MARGIN + 168
    what_x = MARGIN + 250

    sheet.columns([
        (start_x, "START", "left"),
        (length_x, "LENGTH", "right"),
        (focus_x, "FOCUS", "right"),
        (category_x, "CATEGORY", "left"),
        (what_x, "WHAT", "left"),
    ])
    sheet.y += 12

    for session in sessions:
        sheet.need(17)
        doc = sheet.doc
        window = f"{clock(session['start'])} - {clock(session['end'])}"
        doc.text(start_x, sheet.y, window, "mono", 8.5, INK)
        doc.text_right(length_x, sheet.y, fmt(session["duration_sec"]), "mono", 8.5, INK)
        doc.text_right(focus_x, sheet.y, f"{round(session['focus_score'] or 0)}",
                       "mono", 8.5, MUTED)

        category = session["category"] or "other"
        doc.rect(category_x, sheet.y - 5, 5, 5, color_for(category))
        doc.text(category_x + 9, sheet.y, category, "regular", 8.5, INK)

        what = session["top_title"] or session["top_app"] or ""
        if session["interruptions"]:
            plural = "s" if session["interruptions"] > 1 else ""
            what += f"  (+{session['interruptions']} interruption{plural})"
        doc.text(what_x, sheet.y,
                 pdf.ellipsize(what, "regular", 8.5, RIGHT - what_x), "regular", 8.5, INK)

        sheet.y += 6
        doc.rule(MARGIN, sheet.y, RIGHT, RULE, 0.4)
        sheet.y += 11

    below = config.MIN_SESSION_SECONDS // 60
    sheet.y += 2
    sheet.doc.text(
        MARGIN, sheet.y,
        f"Blocks under {below} minutes are left out here; they are still counted "
        f"in the totals above.",
        "regular", 8, MUTED,
    )
    sheet.y += 10


def share_table(sheet: Sheet, title: str, rows: list, label_of, color_of,
                total: float, key: str = "NAME", limit: int = 12) -> None:
    """The three rollups below are the same table with a different key."""
    rows = [row for row in rows if row.get("duration_sec")][:limit]
    if not rows:
        return

    sheet.heading(title)
    time_x = MARGIN + 250
    bar_x = MARGIN + 262
    bar_width = 150.0

    sheet.columns([
        (MARGIN, key, "left"),
        (time_x, "TIME", "right"),
        (bar_x, "SHARE OF THE DAY", "left"),
    ])
    sheet.y += 12

    for row in rows:
        sheet.need(16)
        doc = sheet.doc
        color = color_of(row)
        doc.rect(MARGIN, sheet.y - 5, 5, 5, color)
        doc.text(MARGIN + 9, sheet.y,
                 pdf.ellipsize(label_of(row), "regular", 9, time_x - MARGIN - 24),
                 "regular", 9, INK)
        doc.text_right(time_x, sheet.y, fmt(row["duration_sec"]), "mono", 8.5, INK)

        fraction = (row["duration_sec"] / total) if total else 0
        _bar(doc, bar_x, sheet.y - 3, bar_width, fraction, color)
        doc.text(bar_x + bar_width + 8, sheet.y, f"{round(fraction * 100)}%",
                 "mono", 8, MUTED)
        sheet.y += 15


def footers(doc: pdf.Document, day: str) -> None:
    """Drawn last, on every page, because the total was not known until now."""
    total = doc.page_count
    baseline = pdf.PAGE_HEIGHT - 42
    for index in range(total):
        doc.current = index
        doc.rule(MARGIN, baseline - 12, RIGHT, RULE)
        doc.text(MARGIN, baseline, f"Cadence  -  {day}", "regular", 8, MUTED)
        doc.text_right(RIGHT, baseline, f"{index + 1} of {total}", "regular", 8, MUTED)


def closing_note(sheet: Sheet) -> None:
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


# -- entry point --------------------------------------------------------------


def render(payload: dict, created: str = "") -> bytes:
    """A day payload -- exactly what the dashboard renders -- as PDF bytes."""
    doc = pdf.Document(
        title=f"Cadence - {long_date(payload['day'])}",
        created=created,
    )
    sheet = Sheet(doc)

    title_block(sheet, payload)
    narrative(sheet, payload)
    timeline(sheet, payload)
    sessions_table(sheet, payload)

    tracked = payload["summary"]["tracked_sec"]
    share_table(
        sheet, "categories", payload["categories"],
        lambda row: row["category"] or "other",
        lambda row: color_for(row["category"]),
        tracked, key="CATEGORY",
    )
    share_table(
        sheet, "applications", payload["apps"],
        lambda row: row.get("name") or row["app"],
        lambda row: color_for(row.get("category")),
        tracked, key="APPLICATION",
    )
    share_table(
        sheet, "sites", payload["sites"],
        lambda row: row["host"],
        lambda _row: CATEGORY_COLORS["browsing"],
        tracked, key="SITE", limit=10,
    )

    closing_note(sheet)
    footers(doc, payload["day"])
    return doc.output()
