"""One week, laid out as a shareable PDF.

Not seven day reports stapled together. A week is worth its own page because it
answers a question a single day cannot: whether that day was typical. So the
centre of this report is seven bands drawn against one shared 24-hour axis --
the shape of the week, where the days start and stop, where the good stretches
were, which day was the outlier.

The rollups underneath are the week's, not any day's, so a category that eats
an afternoon looks small and one that takes an hour every morning does not.

A week in progress is rendered up to today and says so. Padding it out to
Sunday would show empty bars for days that have not happened, which reads as
absence rather than as the future.
"""

from datetime import datetime

from . import pdf, sheet
from .digest import fmt
from .sheet import INK, MARGIN, MUTED, RIGHT, RULE, Sheet, color_for

CONTENT_WIDTH = sheet.CONTENT_WIDTH


def span_label(start: str, end: str) -> str:
    """'24 - 30 August 2026', collapsing whatever the two ends agree on."""
    try:
        first = datetime.strptime(start, "%Y-%m-%d")
        last = datetime.strptime(end, "%Y-%m-%d")
    except ValueError:
        return f"{start} - {end}"

    if first == last:
        return sheet.long_date(start)

    day_of = lambda when: str(when.day)                            # noqa: E731
    if (first.year, first.month) == (last.year, last.month):
        return f"{day_of(first)} - {day_of(last)} {last:%B %Y}"
    if first.year == last.year:
        return f"{day_of(first)} {first:%B} - {day_of(last)} {last:%B %Y}"
    return f"{day_of(first)} {first:%B %Y} - {day_of(last)} {last:%B %Y}"


# -- the sections -------------------------------------------------------------


def title_block(page: Sheet, payload: dict) -> None:
    doc = page.doc
    doc.text(MARGIN, 62, "Cadence", "bold", 22, INK)
    doc.text_right(RIGHT, 62, span_label(payload["start"], payload["through"]),
                   "regular", 10, MUTED)
    doc.rule(MARGIN, 74, RIGHT, RULE)

    stats = payload["summary"]
    page.y = sheet.TOP_FIRST + 6
    if stats["tracked_days"]:
        line = (
            f"{stats['tracked_days']} days tracked  -  "
            f"{fmt(stats['blocks_sec'])} in blocks  -  "
            f"{stats['sessions']} sessions"
        )
    else:
        line = "Nothing tracked this week."
    doc.text(MARGIN, page.y, line, "bold", 13, INK)
    page.y += 10

    if stats["tracked_sec"]:
        detail = (
            f"{fmt(stats['tracked_sec'])} at the machine, "
            f"{fmt(stats['active_sec'])} of it active. "
            f"Busiest day {payload['busiest']['name']}, "
            f"{fmt(payload['busiest']['tracked_sec'])}."
        )
        page.y += 12
        doc.text(MARGIN, page.y, detail, "regular", 9.5, MUTED)
        page.y += 6

    if payload["partial"]:
        page.y += 12
        doc.text(
            MARGIN, page.y,
            f"This week is still running; it is shown through {sheet.long_date(payload['through'])}.",
            "regular", 8.5, MUTED,
        )
        page.y += 4


def week_strip(page: Sheet, payload: dict) -> None:
    """Seven days against one axis: the picture the week is here for."""
    days = payload["days"]
    if not days:
        return

    page.heading("the shape of the week")

    label_width = 62.0
    total_width = 58.0
    band_x = MARGIN + label_width
    band_width = CONTENT_WIDTH - label_width - total_width
    row_height = 16.0

    page.need(len(days) * (row_height + 5) + 20)

    doc = page.doc
    busiest = max((day["summary"]["tracked_sec"] for day in days), default=0)

    for day in days:
        tracked = day["summary"]["tracked_sec"]
        # The weekday leads, because that is how a week is read; the date is
        # there to pin it to a real one.
        stamp = datetime.strptime(day["day"], "%Y-%m-%d")
        doc.text(MARGIN, page.y + 11, f"{stamp:%a} {stamp.day}", "regular", 8.5,
                 INK if tracked else MUTED)

        sheet.band(doc, band_x, page.y, band_width, row_height, day["sessions"])
        if not tracked:
            doc.text(band_x + 6, page.y + 11, "nothing tracked", "regular", 7.5, MUTED)

        doc.text_right(RIGHT, page.y + 11, fmt(tracked) if tracked else "-",
                       "mono", 8, INK if tracked == busiest and tracked else MUTED)
        page.y += row_height + 5

    page.y += 4
    sheet.hour_axis(page, band_x, band_width)


def days_table(page: Sheet, payload: dict) -> None:
    days = [day for day in payload["days"] if day["summary"]["tracked_sec"]]
    if not days:
        return

    page.heading("day by day")
    date_x = MARGIN
    tracked_x = MARGIN + 200
    blocks_x = MARGIN + 268
    sessions_x = MARGIN + 330
    longest_x = MARGIN + 400
    what_x = MARGIN + 410

    page.columns([
        (date_x, "DAY", "left"),
        (tracked_x, "AT THE MACHINE", "right"),
        (blocks_x, "IN BLOCKS", "right"),
        (sessions_x, "SESSIONS", "right"),
        (longest_x, "LONGEST", "right"),
        (what_x, "MOSTLY", "left"),
    ])
    page.y += 12

    for day in days:
        page.need(17)
        doc = page.doc
        stats = day["summary"]
        stamp = datetime.strptime(day["day"], "%Y-%m-%d")

        doc.text(date_x, page.y, f"{stamp:%A} {stamp.day}", "regular", 8.5, INK)
        doc.text_right(tracked_x, page.y, fmt(stats["tracked_sec"]), "mono", 8.5, INK)
        doc.text_right(blocks_x, page.y, fmt(stats["blocks_sec"]), "mono", 8.5, INK)
        doc.text_right(sessions_x, page.y, str(stats["sessions"]), "mono", 8.5, MUTED)
        doc.text_right(longest_x, page.y, fmt(stats["longest_sec"]), "mono", 8.5, MUTED)

        leading = day["top_category"]
        if leading:
            doc.rect(what_x, page.y - 5, 5, 5, color_for(leading))
            doc.text(what_x + 9, page.y, leading, "regular", 8.5, INK)

        page.y += 6
        doc.rule(MARGIN, page.y, RIGHT, RULE, 0.4)
        page.y += 11


# -- entry point --------------------------------------------------------------


def render(payload: dict, created: str = "") -> bytes:
    """A week payload as PDF bytes."""
    label = span_label(payload["start"], payload["through"])
    doc = pdf.Document(title=f"Cadence - week of {label}", created=created)
    page = Sheet(doc)

    title_block(page, payload)
    week_strip(page, payload)
    days_table(page, payload)

    active, idle_sec = sheet.active_categories(payload["categories"])
    idle_note = (
        f"Idle and away time ({fmt(idle_sec)}) is not counted here."
        if idle_sec else ""
    )
    sheet.share_table(
        page, "categories", active,
        lambda row: row["category"] or "other",
        lambda row: color_for(row["category"]),
        key="CATEGORY", share_of="SHARE OF CATEGORISED TIME", note=idle_note,
    )
    sheet.share_table(
        page, "applications", payload["apps"],
        lambda row: row.get("name") or row["app"],
        lambda row: color_for(row.get("category")),
        key="APPLICATION", share_of="SHARE OF APP TIME",
    )
    sheet.share_table(
        page, "sites", payload["sites"],
        lambda row: row["host"],
        lambda _row: sheet.CATEGORY_COLORS["browsing"],
        key="SITE", share_of="SHARE OF SITE TIME", limit=10,
    )

    sheet.closing_note(page)
    sheet.footers(doc, f"week of {label}")
    return doc.output()
