"""Daily report: python report.py [YYYY-MM-DD]"""

import sys
from datetime import date

from cadence import categories, db


def fmt(seconds: float) -> str:
    m = int(seconds // 60)
    return f"{m // 60}h {m % 60:02d}m" if m >= 60 else f"{m}m"


def main(day: str) -> None:
    conn = db.connect()
    categories.backfill(conn)

    totals = conn.execute(
        "SELECT category, SUM(duration_sec) d, SUM(active_sec) a, SUM(input_sec) i "
        "FROM segments WHERE day = ? GROUP BY category ORDER BY d DESC",
        (day,),
    ).fetchall()

    if not totals:
        print(f"No activity recorded for {day}.")
        return

    print(f"\n  {day}\n")
    print(f"  {'category':<14}{'open':>9}{'active':>9}{'engaged':>9}   engagement")
    print("  " + "-" * 62)
    for r in totals:
        pct = (r["i"] / r["d"] * 100) if r["d"] else 0
        bar = "#" * round(pct / 5)
        print(f"  {r['category']:<14}{fmt(r['d']):>9}{fmt(r['a']):>9}{fmt(r['i']):>9}   {bar} {pct:.0f}%")

    print(f"\n  top windows\n  " + "-" * 62)
    top = conn.execute(
        "SELECT app, title, SUM(duration_sec) d, SUM(input_sec) i FROM segments "
        "WHERE day = ? AND category NOT IN ('idle','away') "
        "GROUP BY app, title ORDER BY d DESC LIMIT 12",
        (day,),
    ).fetchall()
    for r in top:
        pct = (r["i"] / r["d"] * 100) if r["d"] else 0
        print(f"  {fmt(r['d']):>8}  {pct:>3.0f}%  {r['app']:<16} {(r['title'] or '')[:40]}")
    print()


if __name__ == "__main__":
    main(sys.argv[1] if len(sys.argv) > 1 else date.today().strftime("%Y-%m-%d"))
