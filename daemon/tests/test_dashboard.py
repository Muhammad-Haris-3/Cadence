"""The dashboard's script, which until now nothing checked at all.

The daemon is tested from four angles and the page it serves was tested from
none, so a bug there could only be found by a person looking at the screen --
and the page has one message that actively hides bugs from that person. Adding
a twelve-hour clock introduced a second `function clock` in a file that already
had one; the later declaration won, its body called what it thought was the
first, and it called itself instead. Every render threw. The catch in `load`
could not tell a broken render from an unreachable daemon, so the page said
"waiting for the tracker" while the tracker sat there answering every request
in fifteen milliseconds.

Three checks, aimed at exactly that:

  - the script parses at all
  - no name is declared twice at the top level
  - the page's clock and the daemon's clock agree, character for character

The last one matters because the rule is written twice on purpose -- a static
page cannot import Python -- and two copies of a rule are two copies until
something forces them to stay one.

Needs node, which is on the machine this is developed on. Without it the two
static checks still run and the comparison reports itself as skipped rather
than quietly passing.
"""

import json
import os
import re
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ.setdefault("CADENCE_DATA_DIR", tempfile.mkdtemp(prefix="cadence-test-"))

from cadence.digest import clock, hour_label  # noqa: E402

PAGE = Path(__file__).resolve().parent.parent / "cadence" / "static" / "index.html"


def check(label, got, want):
    status = "PASS" if got == want else "FAIL"
    print(f"  [{status}] {label}" + ("" if got == want else f"  (got {got!r}, want {want!r})"))
    return got == want


def check_true(label, got):
    return check(label, bool(got), True)


def script() -> str:
    """The page's own <script> block, as the browser would run it."""
    html = PAGE.read_text(encoding="utf-8")
    return re.search(r"<script>(.*)</script>", html, re.S).group(1)


def js_function(source: str, name: str) -> str:
    """One top-level function, lifted out by matching its braces."""
    start = source.index(f"function {name}(")
    depth, index = 0, source.index("{", start)
    for position in range(index, len(source)):
        if source[position] == "{":
            depth += 1
        elif source[position] == "}":
            depth -= 1
            if depth == 0:
                return source[start:position + 1]
    raise ValueError(f"unbalanced braces in {name}")


def run_node(body: str):
    handle, path = tempfile.mkstemp(suffix=".mjs", prefix="cadence-js-")
    os.close(handle)
    Path(path).write_text(body, encoding="utf-8")
    try:
        result = subprocess.run([shutil.which("node"), path], capture_output=True,
                                text=True, encoding="utf-8", errors="replace")
    finally:
        os.unlink(path)
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip())
    return json.loads(result.stdout)


CASES = [
    "2026-08-31T00:00:00", "2026-08-31T00:08:00", "2026-08-31T03:55:00",
    "2026-08-31T09:30:00", "2026-08-31T11:59:00", "2026-08-31T12:00:00",
    "2026-08-31T12:45:00", "2026-08-31T13:05:00", "2026-08-31T19:08:00",
    "2026-08-31T23:59:00",
]


def main():
    results = []
    source = script()
    node = shutil.which("node")

    print()
    print("the script itself")
    if node:
        handle, path = tempfile.mkstemp(suffix=".js", prefix="cadence-syntax-")
        os.close(handle)
        Path(path).write_text(source, encoding="utf-8")
        checked = subprocess.run([node, "--check", path], capture_output=True, text=True)
        os.unlink(path)
        results.append(check("it parses", checked.returncode, 0))
    else:
        print("  [SKIP] it parses  (node not found)")

    print()
    print("nothing is declared twice")
    # Top-level declarations sit at column 0 in this file. A second one silently
    # replaces the first, which is how `clock` came to call itself.
    declared = re.findall(r"^function (\w+)\(", source, re.M)
    repeated = sorted({name for name in declared if declared.count(name) > 1})
    results.append(check("no function name is used twice", repeated, []))

    consts = re.findall(r"^(?:const|let|var) (\w+)", source, re.M)
    results.append(check("no top-level binding is declared twice",
                         sorted({n for n in consts if consts.count(n) > 1}), []))

    print()
    print("every element the script reaches for exists in the markup")
    html = PAGE.read_text(encoding="utf-8")
    ids = set(re.findall(r'\bid="([^"]+)"', html))
    wanted = set(re.findall(r'\bel\("([^"]+)"\)', source))
    results.append(check("no missing id", sorted(wanted - ids), []))

    print()
    print("the page's clock and the daemon's clock agree")
    if not node:
        print("  [SKIP] node not found")
    else:
        body = "\n".join([
            js_function(source, "clock"),
            js_function(source, "hourLabel"),
            f"const cases = {json.dumps(CASES)};",
            "console.log(JSON.stringify({",
            "  clock: cases.map(clock),",
            "  axis: [0,3,6,9,12,15,18,21,24].map(hourLabel),",
            "  empty: [clock(null), clock(''), clock('nonsense')],",
            "}));",
        ])
        try:
            got = run_node(body)
        except RuntimeError as failure:
            results.append(check("the page's clock runs at all", str(failure), ""))
        else:
            results.append(check("same times as the daemon",
                                 got["clock"], [clock(c) for c in CASES]))
            results.append(check("same axis as the daemon",
                                 got["axis"], [hour_label(h) for h in range(0, 25, 3)]))
            results.append(check("same answer for nothing at all",
                                 got["empty"], ["", "", ""]))
            results.append(check("midnight is 12am on the page too",
                                 got["clock"][0], "12:00 am"))
            results.append(check("noon is 12pm on the page too",
                                 got["clock"][5], "12:00 pm"))

    print()
    print("a broken render may not blame the daemon")
    # The reassuring message is only allowed inside the fetch's catch. If it can
    # be reached from the render's, the page can accuse a healthy tracker again.
    # Anchored inside load(), because "render(data)" also matches the function's
    # own definition forty lines earlier -- which is what this helper did first,
    # and it made the check pass by reading the wrong half of the file.
    body = source[source.index("async function load(day)"):]
    body = body[:body.index("function shift(")]
    fetch_catch = body[:body.index("render(data);")]
    after_render = body[body.index("render(data);"):]
    results.append(check_true("the waiting message lives with the fetch",
                              "Waiting for the tracker" in fetch_catch))
    results.append(check("and not with the render",
                         "Waiting for the tracker" in after_render, False))
    results.append(check_true("a render failure still reaches the console",
                              "throw err" in after_render))

    print(f"\n{sum(results)}/{len(results)} passed\n")
    return 0 if all(results) else 1


if __name__ == "__main__":
    raise SystemExit(main())
