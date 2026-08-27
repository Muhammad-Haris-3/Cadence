"""Rule-by-rule check of segment -> session grouping."""

import os
import sys
import tempfile
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
os.environ["CADENCE_DATA_DIR"] = tempfile.mkdtemp(prefix="cadence-sess-")

from cadence import config, sessionizer  # noqa: E402

_next_id = [0]


def seg(app, category, dur, *, active=None, inp=None, day="2026-08-27", title=None):
    _next_id[0] += 1
    return {
        "id": _next_id[0],
        "started_at": f"{day}T10:00:00",
        "ended_at": f"{day}T10:00:00",
        "day": day,
        "app": app,
        "title": title or app,
        "category": category,
        "duration_sec": float(dur),
        "active_sec": float(dur if active is None else active),
        "input_sec": float(dur * 0.8 if inp is None else inp),
    }


def code(dur, **kw):
    return seg("Code.exe", "code", dur, **kw)


def idle(dur):
    return seg("__idle__", "idle", dur, active=0, inp=0)


results = []


def check(label, got, want):
    ok = got == want
    results.append(ok)
    print(f"  [{'PASS' if ok else 'FAIL'}] {label}" + ("" if ok else f"  (got {got!r}, want {want!r})"))


print("\nrule 1 -- idle gaps")
s = sessionizer.build([code(600), idle(config.IDLE_BREAK_SECONDS + 60), code(600)])
check("long idle splits the session", len(s), 2)

s = sessionizer.build([code(600), idle(120), code(600)])
check("short idle is absorbed", len(s), 1)
check("absorbed idle counts toward duration", s[0].duration, 1320.0)
check("absorbed idle does not count as active", s[0].active, 1200.0)

print("\nrule 2 -- category changes")
s = sessionizer.build([code(600), seg("slack.exe", "comms", 30), code(600)])
check("brief excursion keeps one session", len(s), 1)
check("...and is recorded as an interruption", s[0].interruptions, 1)
check("...with its time still counted", s[0].duration, 1230.0)

s = sessionizer.build([code(600), seg("slack.exe", "comms", 300), code(600)])
check("sustained change splits", len(s), 3)
check("the excursion becomes its own session", s[1].dominant, "comms")
check("work resumes as a new session", s[2].dominant, "code")

print("\nrule 3 -- day boundary")
s = sessionizer.build([code(600), code(600, day="2026-08-28")])
check("a session never straddles two days", len(s), 2)

print("\nfocus score")
typing = sessionizer.build([code(1800)])[0]
reading = sessionizer.build([code(1800, inp=180)])[0]  # 10% input: reading docs
scattered = sessionizer.build([code(5) for _ in range(180)])[0]  # ~12 switches/min
absent = sessionizer.build([code(1800, active=300, inp=200)])[0]

check("focused typing scores high", typing.focus_score() > 70, True)
check("reading is not punished as slacking", reading.focus_score() > 45, True)
check("scattered switching scores below focused", scattered.focus_score() < 40, True)
check("steady alt-tabbing is not punished as scattered",
      sessionizer.build([code(30) for _ in range(60)])[0].focus_score() > 55, True)
check("walking away scores low", absent.focus_score() < 25, True)
print(f"       typing {typing.focus_score()} | reading {reading.focus_score()} | "
      f"scattered {scattered.focus_score()} | absent {absent.focus_score()}")

print(f"\n{sum(results)}/{len(results)} passed\n")
raise SystemExit(0 if all(results) else 1)
