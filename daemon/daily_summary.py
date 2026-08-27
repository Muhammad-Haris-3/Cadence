"""Daily summary.

    python daily_summary.py                  # print the digest (free path)
    python daily_summary.py --save           # read a summary from stdin and store it
    python daily_summary.py --show           # print the stored summary
    python daily_summary.py --ai             # generate via the Claude API (costs money)
    python daily_summary.py --ai --model claude-haiku-4-5

Any of these takes an optional YYYY-MM-DD; the default is today.

The free path is the default and the recommended one. Print the digest, then ask
Claude Code to summarise the day -- it reads this database directly, costs
nothing beyond a subscription you already have, and unlike a stored summary you
can ask it follow-up questions.
"""

import argparse
import sys
from datetime import date

from cadence import categories, db, digest, sessionizer, summary

# Both ends need UTF-8. Window titles arrive with emoji, and summaries get
# written with dashes and quotes that cp1252 mangles into mojibake on the way in.
sys.stdout.reconfigure(encoding="utf-8", errors="replace")
sys.stdin.reconfigure(encoding="utf-8", errors="replace")


def parse_args():
    parser = argparse.ArgumentParser(add_help=True, description=__doc__)
    parser.add_argument("day", nargs="?", default=date.today().strftime("%Y-%m-%d"))
    parser.add_argument("--ai", action="store_true", help="generate via the Claude API (costs money)")
    parser.add_argument("--model", default=summary.DEFAULT_MODEL)
    parser.add_argument("--save", action="store_true", help="store a summary read from stdin")
    parser.add_argument("--show", action="store_true", help="print the stored summary")
    parser.add_argument(
        "--yes", action="store_true",
        help="skip the spend confirmation (for unattended runs)",
    )
    return parser.parse_args()


def confirm_spend(conn, day: str, model: str) -> bool:
    """Never let money leave without a number on screen and a typed yes.

    The estimate is from the digest length, so it is approximate -- but it is the
    right order of magnitude, which is what the decision actually turns on.
    """
    text = digest.build(conn, day)
    approx_in = len(text) // 4
    approx_out = 400
    cost = summary.estimate_cost(model, approx_in, approx_out)

    print(f"\nThis calls the Claude API and costs real money.")
    print(f"  model     {model}")
    print(f"  estimate  ~{approx_in} in / ~{approx_out} out  ->  about ${cost:.4f}")
    print("\nThe free path costs nothing: run without --ai, and ask Claude Code")
    print("to summarise the digest it prints.\n")

    try:
        return input("Continue and spend? [y/N] ").strip().lower() in ("y", "yes")
    except (EOFError, KeyboardInterrupt):
        print()
        return False


def main() -> int:
    args = parse_args()
    conn = db.connect()

    # The digest reads derived state, so make sure it is current for that day.
    categories.backfill(conn, args.day)
    sessionizer.rebuild(conn, args.day)

    if args.show:
        stored = summary.get(conn, args.day)
        if not stored:
            print(f"No summary stored for {args.day}.")
            return 1
        print(f"\n{args.day} — {stored['source']}, {stored['model'] or 'written by hand'}\n")
        print(stored["text"])
        print()
        return 0

    if args.save:
        text = sys.stdin.read().strip()
        if not text:
            print("Nothing on stdin to save.")
            return 1
        summary.save(conn, args.day, text, source="manual")
        print(f"Saved the summary for {args.day}.")
        return 0

    if args.ai:
        if not args.yes and not confirm_spend(conn, args.day, args.model):
            print("Cancelled. Nothing was sent and nothing was spent.")
            return 1

        try:
            result = summary.generate(conn, args.day, model=args.model)
        except RuntimeError as exc:
            print(f"{exc}")
            return 1

        print(f"\n{args.day}\n")
        print(result["text"])
        print(
            f"\n[{result['model']} · {result['input_tokens']} in / "
            f"{result['output_tokens']} out · about ${result['cost_usd']:.4f}]"
        )
        return 0

    # Default: the free path.
    print(digest.build(conn, args.day))
    print(
        "\n---\n"
        "Ask Claude Code to summarise this, or run with --ai to use the API.\n"
        "To store a summary you wrote or Claude Code produced:\n"
        f"    python daily_summary.py {args.day} --save   (reads stdin)"
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
