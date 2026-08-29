"""One day, laid out as a shareable PDF.

The dashboard is for you; this is for someone else. That difference decides
what goes on the page. Anything that only makes sense while you are clicking it
is gone -- the philosophy switch, the day arrows, the expandable app rows -- and
what remains is the part a colleague could read cold: what the day was made of,
in what order, and how much of it was what.

The page itself, the palette and the closing note come from `sheet`, which the
week report uses too. What is here is only what is specific to a single day.
"""

from . import config, pdf, sheet
from .digest import fmt
from .sheet import INK, MARGIN, MUTED, RIGHT, RULE, Sheet, color_for, long_date

CONTENT_WIDTH = sheet.CONTENT_WIDTH


def clock(stamp) -> str:
    return sheet.clock(stamp)


# -- the sections -------------------------------------------------------------


def title_block(page: Sheet, payload: dict) -> None:
    doc = page.doc
    doc.text(MARGIN, 62, "Cadence", "bold", 22, INK)
    doc.text_right(RIGHT, 62, long_date(payload["day"]), "regular", 10, MUTED)
    doc.rule(MARGIN, 74, RIGHT, RULE)

    stats = payload["summary"]
    page.y = sheet.TOP_FIRST + 6
    if stats["sessions"]:
        line = (
            f"{stats['sessions']} sessions  -  {fmt(stats['blocks_sec'])} in blocks"
            f"  -  longest {fmt(stats['longest_sec'])}"
        )
    else:
        line = "Nothing tracked on this day."
    doc.text(MARGIN, page.y, line, "bold", 13, INK)
    page.y += 10

    if stats["tracked_sec"]:
        detail = (
            f"{fmt(stats['tracked_sec'])} at the machine, "
            f"{fmt(stats['active_sec'])} of it active, "
            f"{fmt(stats['input_sec'])} with input."
        )
        page.y += 12
        doc.text(MARGIN, page.y, detail, "regular", 9.5, MUTED)
        page.y += 6


def narrative(page: Sheet, payload: dict) -> None:
    if not payload.get("written"):
        return
    page.heading("the day in words")
    page.paragraph(payload["written"], 10.5, INK, 15.5)
    source = payload.get("written_source")
    if source:
        page.y += 2
        page.doc.text(MARGIN, page.y, f"Written by: {source}", "regular", 8, MUTED)
        page.y += 10


def timeline(page: Sheet, payload: dict) -> None:
    if not payload["sessions"]:
        return

    page.heading("the shape of it")
    height = 34.0
    page.need(height + 22)

    sheet.band(page.doc, MARGIN, page.y, CONTENT_WIDTH, height, payload["sessions"])
    page.y += height + 11
    sheet.hour_axis(page, MARGIN, CONTENT_WIDTH)


def sessions_table(page: Sheet, payload: dict) -> None:
    sessions = payload["sessions"]
    if not sessions:
        return

    page.heading("sessions")
    start_x = MARGIN
    length_x = MARGIN + 108
    focus_x = MARGIN + 152
    category_x = MARGIN + 168
    what_x = MARGIN + 250

    page.columns([
        (start_x, "START", "left"),
        (length_x, "LENGTH", "right"),
        (focus_x, "FOCUS", "right"),
        (category_x, "CATEGORY", "left"),
        (what_x, "WHAT", "left"),
    ])
    page.y += 12

    for session in sessions:
        page.need(17)
        doc = page.doc
        window = f"{clock(session['start'])} - {clock(session['end'])}"
        doc.text(start_x, page.y, window, "mono", 8.5, INK)
        doc.text_right(length_x, page.y, fmt(session["duration_sec"]), "mono", 8.5, INK)
        doc.text_right(focus_x, page.y, f"{round(session['focus_score'] or 0)}",
                       "mono", 8.5, MUTED)

        category = session["category"] or "other"
        doc.rect(category_x, page.y - 5, 5, 5, color_for(category))
        doc.text(category_x + 9, page.y, category, "regular", 8.5, INK)

        what = session["top_title"] or session["top_app"] or ""
        if session["interruptions"]:
            plural = "s" if session["interruptions"] > 1 else ""
            what += f"  (+{session['interruptions']} interruption{plural})"
        doc.text(what_x, page.y,
                 pdf.ellipsize(what, "regular", 8.5, RIGHT - what_x), "regular", 8.5, INK)

        page.y += 6
        doc.rule(MARGIN, page.y, RIGHT, RULE, 0.4)
        page.y += 11

    below = config.MIN_SESSION_SECONDS // 60
    page.y += 2
    page.doc.text(
        MARGIN, page.y,
        f"Blocks under {below} minutes are left out here; they are still counted "
        f"in the totals above.",
        "regular", 8, MUTED,
    )
    page.y += 10


# -- entry point --------------------------------------------------------------


def render(payload: dict, created: str = "") -> bytes:
    """A day payload -- exactly what the dashboard renders -- as PDF bytes."""
    doc = pdf.Document(
        title=f"Cadence - {long_date(payload['day'])}",
        created=created,
    )
    page = Sheet(doc)

    title_block(page, payload)
    narrative(page, payload)
    timeline(page, payload)
    sessions_table(page, payload)

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
    sheet.footers(doc, payload["day"])
    return doc.output()
