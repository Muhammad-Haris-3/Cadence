"""The day report, and the PDF writer under it.

A PDF is the one thing Cadence produces that leaves the machine, which makes it
the one thing nobody here can check for you: it is opened later, somewhere else,
by someone who will not report a broken file, only a bad impression. So the
checks below are about the two ways that goes wrong.

Structure first -- a cross-reference table whose offsets are a few bytes out, or
a stream whose declared length disagrees with its bytes, produces a file that
some readers open and others refuse, which is worse than one that fails
everywhere. `structure` re-derives both from the finished bytes.

Then the page itself. Window titles are arbitrary text: they arrive long, in
scripts the built-in fonts cannot set, and full of the parenthesis that ends a
PDF string early. None of that may push a column off the page or out of its
column, so the report is rendered and every mark on it measured.
"""

import os
import re
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-test-")

from cadence import dayreport, pdf  # noqa: E402


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {label}" + ("" if got == want else f"  (got {got!r}, want {want!r})"))
    return got == want


def check_true(label, got):
    return check(label, bool(got), True)


# -- reading a finished PDF back ----------------------------------------------


def structure(data: bytes) -> list:
    """Every structural complaint about `data`, as strings. Empty means valid."""
    problems = []
    if not data.startswith(b"%PDF-"):
        problems.append("no PDF header")
    if not data.rstrip().endswith(b"%%EOF"):
        problems.append("no EOF marker")

    found = re.search(rb"startxref\s+(\d+)", data)
    if not found:
        return problems + ["no startxref"]

    start = int(found.group(1))
    if data[start:start + 4] != b"xref":
        return problems + ["startxref does not point at the table"]

    rows = data[start:].split(b"\n")
    count = int(rows[1].split()[1])
    for object_id in range(1, count):
        entry = rows[2 + object_id]
        if len(entry) != 19:            # 20 bytes once the newline is back
            problems.append(f"xref entry {object_id} is {len(entry) + 1} bytes")
            continue
        offset = int(entry.split()[0])
        expected = b"%d 0 obj" % object_id
        if data[offset:offset + len(expected)] != expected:
            problems.append(f"xref offset {object_id} points at {data[offset:offset + 12]!r}")

    for match in re.finditer(rb"/Length (\d+) >>\s*stream\r?\n", data):
        declared = int(match.group(1))
        actual = data[match.end():].index(b"\nendstream")
        if declared != actual:
            problems.append(f"stream says {declared} bytes but holds {actual}")

    return problems


def streams(data: bytes) -> list:
    return [
        match.group(1).decode("cp1252")
        for match in re.finditer(rb"stream\r?\n(.*?)\nendstream", data, re.S)
    ]


def text_runs(data: bytes) -> list:
    """Every string drawn, in order, with PDF's escapes undone."""
    out = []
    for page in streams(data):
        for match in re.finditer(r"\((.*?)\) Tj", page):
            body = re.sub(r"\\(.)", r"\1", match.group(1))
            out.append(body)
    return out


BY_ALIAS = {alias: name for name, (alias, _base) in pdf.FONTS.items()}

# The whole text operator in one pattern: font, size, position and body have to
# come from the same BT block, or a run gets measured at some other run's size.
SET_TEXT = re.compile(
    r"BT [\d. ]+ rg /(F\d) ([\d.]+) Tf 1 0 0 1 ([\d.-]+) ([\d.-]+) Tm \((.*?)\) Tj"
)


def marks(data: bytes) -> list:
    """Every drawn thing as (x, y, width, height) in PDF's own coordinates, so
    the page's own edges are the only thing a bounds check needs to know.

    Text is boxed from its baseline up by the full point size, which is taller
    than any of these faces actually reach -- a bounds check should err towards
    complaining.
    """
    found = []
    for page in streams(data):
        for alias, size, x, y, body in SET_TEXT.findall(page):
            size = float(size)
            found.append((
                float(x), float(y),
                pdf.width_of(body, BY_ALIAS[alias], size), size,
            ))
        for match in re.finditer(r"([\d.-]+) ([\d.-]+) ([\d.-]+) ([\d.-]+) re f", page):
            found.append(tuple(float(g) for g in match.groups()))
    return found


# -- a day to render ----------------------------------------------------------

AWKWARD = (
    "Reading (a paper) about \\ escapes — with “smart quotes” "
    "and 中文 and an emoji \U0001f600 and then a very long tail that keeps "
    "going well past anything that could fit inside one column of a table"
)


def payload(sessions=3, written=None) -> dict:
    made = [
        {
            "start": f"2026-08-29T{9 + n:02d}:15:00",
            "end": f"2026-08-29T{9 + n:02d}:58:00",
            "offset_sec": (9 + n) * 3600 + 900,
            "duration_sec": 2580.0,
            "active_sec": 2400.0,
            "input_sec": 1200.0,
            "category": ["code", "ai", "distraction"][n % 3],
            "top_app": "Code.exe",
            "top_title": AWKWARD if n == 0 else f"session {n}",
            "switches": 40,
            "interruptions": n,
            "focus_score": 60 - n,
        }
        for n in range(sessions)
    ]
    return {
        "day": "2026-08-29",
        "written": written,
        "written_source": "manual" if written else None,
        "summary": {
            "sessions": len(made),
            "blocks_sec": sum(s["duration_sec"] for s in made),
            "longest_sec": max((s["duration_sec"] for s in made), default=0),
            "tracked_sec": sum(s["duration_sec"] for s in made),
            "active_sec": sum(s["active_sec"] for s in made),
            "input_sec": sum(s["input_sec"] for s in made),
        },
        "sessions": made,
        "categories": [
            {"category": "code", "duration_sec": 3600.0},
            {"category": "ai", "duration_sec": 1800.0},
            {"category": None, "duration_sec": 60.0},
        ],
        "apps": [
            {"app": "Code.exe", "name": AWKWARD, "category": "code", "duration_sec": 3600.0},
            {"app": "chrome.exe", "name": "Google Chrome", "category": "browsing",
             "duration_sec": 1800.0},
        ],
        "sites": [{"host": "github.com", "duration_sec": 1200.0}],
    }


def main():
    results = []

    print()
    print("measuring")
    results.append(check_true("wide letters measure wider than narrow ones",
                              pdf.width_of("MMMM") > pdf.width_of("iiii")))
    results.append(check("courier is exactly 0.6 em everywhere",
                         pdf.width_of("abcde", "mono", 10), 30.0))
    results.append(check_true("bold is wider than regular at the same size",
                              pdf.width_of("Cadence", "bold", 12)
                              > pdf.width_of("Cadence", "regular", 12)))
    results.append(check("width scales with size",
                         round(pdf.width_of("Cadence", "regular", 20), 4),
                         round(pdf.width_of("Cadence", "regular", 10) * 2, 4)))

    print()
    print("encoding what the fonts cannot set")
    results.append(check("smart quotes become straight ones",
                         pdf.encode("“ok”"), b'"ok"'))
    results.append(check("an em dash becomes two hyphens",
                         pdf.encode("a — b"), b"a -- b"))
    results.append(check("an emoji degrades rather than raising",
                         pdf.encode("hi \U0001f600"), b"hi ?"))
    results.append(check("accented latin survives intact",
                         pdf.encode("café"), "café".encode("cp1252")))

    print()
    print("fitting text to a column")
    squeezed = pdf.ellipsize(AWKWARD, "regular", 9, 120)
    results.append(check_true("an ellipsized string fits its limit",
                              pdf.width_of(squeezed, "regular", 9) <= 120))
    results.append(check_true("and says it was cut", squeezed.endswith("...")))
    results.append(check("a short string is left alone",
                         pdf.ellipsize("short", "regular", 9, 120), "short"))
    lines = pdf.wrap(AWKWARD, "regular", 10, 200)
    results.append(check_true("every wrapped line fits",
                              all(pdf.width_of(line, "regular", 10) <= 200
                                  for line in lines[:-1])))
    results.append(check("wrapping loses no words",
                         " ".join(lines).split(), AWKWARD.split()))

    print()
    print("the file a reader has to open")
    rendered = dayreport.render(payload(), created="20260829100000")
    results.append(check("nothing structurally wrong", structure(rendered), []))
    results.append(check_true("the day is titled for the file manager",
                              b"/Title" in rendered))

    drawn = text_runs(rendered)
    results.append(check_true("the headline is on the page",
                              any("3 sessions" in run for run in drawn)))
    results.append(check_true("so is the privacy note",
                              any("No keystroke content" in run for run in drawn)))
    results.append(check_true("and the focus caveat",
                              any("not a measure of worth" in run for run in drawn)))
    results.append(check_true("a bracket in a window title survives escaping",
                              any("(a paper)" in run for run in drawn)))
    results.append(check("the uncategorised row is named, not blank",
                         drawn.count("other"), 1))

    print()
    print("nothing falls off the page")
    off_page = [
        mark for mark in marks(rendered)
        if mark[0] < 0 or mark[1] < 0
        or mark[0] + mark[2] > pdf.PAGE_WIDTH + 0.5
        or mark[1] + mark[3] > pdf.PAGE_HEIGHT + 0.5
    ]
    results.append(check("every mark is inside the page", off_page, []))

    print()
    print("a day that needs more than one page")
    long_day = dayreport.render(payload(sessions=40))
    results.append(check_true("it paginates", long_day.count(b"/Type /Page ") > 1))
    results.append(check("and is still structurally sound", structure(long_day), []))
    numbering = [run for run in text_runs(long_day) if re.fullmatch(r"\d+ of \d+", run)]
    total = numbering[0].split()[-1]
    results.append(check("every page is numbered out of the same total",
                         numbering, [f"{n + 1} of {total}" for n in range(int(total))]))

    print()
    print("the days that are not a normal day")
    empty = payload(sessions=0)
    empty["categories"], empty["apps"], empty["sites"] = [], [], []
    blank = dayreport.render(empty)
    results.append(check("an untracked day still renders", structure(blank), []))
    results.append(check_true("and says so rather than showing an empty frame",
                              any("Nothing tracked" in run for run in text_runs(blank))))

    told = dayreport.render(payload(written="A long morning on one thing, then a scatter."))
    results.append(check_true("a written summary is carried into the report",
                              any("A long morning" in run for run in text_runs(told))))

    results.append(check("a date renders without a leading zero",
                         dayreport.long_date("2026-08-05"), "Wednesday, 5 August 2026"))
    results.append(check("a malformed day is passed through, not crashed on",
                         dayreport.long_date("not-a-day"), "not-a-day"))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
