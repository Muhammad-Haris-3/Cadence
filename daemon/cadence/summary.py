"""Daily summaries -- storage, and the optional API path.

Two ways to get one, and the free path is the default:

**Free.** `daily_summary.py` prints the digest. Open Claude Code in this repo and
ask it to summarise the day; it reads the database directly, costs nothing beyond
the subscription already being paid for, and you can ask follow-up questions --
which is the part an automated summary can never do. Save the result with
`daily_summary.py --save`.

**API.** `daily_summary.py --ai` sends the digest to the Claude API and stores
what comes back. This is the only part of Cadence that can cost money, so it is
opt-in, requires a key, and prints what it spent.

The `anthropic` package is deliberately not in requirements.txt. A default
install stays free and has no reason to carry an API client.
"""

from datetime import datetime
from typing import Optional

from . import digest

DEFAULT_MODEL = "claude-opus-5"

# Per million tokens, for the spend line printed after each call.
PRICING = {
    "claude-opus-5": (5.00, 25.00),
    "claude-sonnet-5": (2.00, 10.00),
    "claude-haiku-4-5": (1.00, 5.00),
}

SYSTEM_PROMPT = """You write one person's daily activity summary. They track \
their own computer use privately; nobody else reads this.

Write 3-5 sentences of plain prose. No headings, no bullets, no preamble.

What to do:
- Name the shape of the day: when the real work happened, how it was broken up.
- Lead with whatever is genuinely notable against their baseline. If nothing is, \
say the day was ordinary rather than inventing significance.
- Read the three clocks correctly. Tracked time is a window being open. Engaged \
time is input actually happening. A large gap between them means presence \
without activity, and is worth naming.
- Treat low engagement in a reading-heavy category as reading, not as slacking.

What not to do:
- Do not moralise. Distraction is a category, not a failing. Never suggest they \
should have done more, and never congratulate them for discipline.
- Do not give productivity advice unless a specific number in the data supports \
a specific observation.
- Do not restate the numbers they can already see. Say what the numbers mean.
- Do not treat the focus score as authoritative. It is a heuristic combining \
presence, engagement and continuity, and it reads rapid window switching as low \
continuity even when that is simply how the work looked."""


def get(conn, day: str) -> Optional[dict]:
    row = conn.execute("SELECT * FROM summaries WHERE day = ?", (day,)).fetchone()
    return dict(row) if row else None


def save(conn, day: str, text: str, model: str = None, source: str = "manual") -> None:
    conn.execute(
        "INSERT INTO summaries (day, text, model, source, created_at) VALUES (?, ?, ?, ?, ?) "
        "ON CONFLICT(day) DO UPDATE SET text = excluded.text, model = excluded.model, "
        "source = excluded.source, created_at = excluded.created_at",
        (day, text.strip(), model, source, datetime.now().isoformat(timespec="seconds")),
    )


def estimate_cost(model: str, input_tokens: int, output_tokens: int) -> float:
    rate_in, rate_out = PRICING.get(model, (0.0, 0.0))
    return (input_tokens / 1_000_000) * rate_in + (output_tokens / 1_000_000) * rate_out


def generate(conn, day: str, model: str = DEFAULT_MODEL) -> dict:
    """Send the day's digest to the Claude API and return the summary.

    Raises RuntimeError with an actionable message rather than a stack trace when
    the optional dependency or the key is missing.
    """
    try:
        import anthropic
    except ImportError:
        raise RuntimeError(
            "The anthropic package is not installed. It is optional, because the\n"
            "free path needs no API client:\n\n"
            "    .venv\\Scripts\\pip install anthropic"
        )

    text = digest.build(conn, day)
    if "Nothing was tracked" in text:
        raise RuntimeError(f"Nothing was tracked on {day}; there is nothing to summarise.")

    try:
        client = anthropic.Anthropic()
    except Exception as exc:
        raise RuntimeError(f"Could not create the API client: {exc}")

    try:
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            output_config={"effort": "medium"},
            betas=["server-side-fallback-2026-07-01"],
            fallbacks="default",
            messages=[{"role": "user", "content": text}],
        )
    except TypeError:
        # Older SDK without the server-side fallback parameters.
        response = client.messages.create(
            model=model,
            max_tokens=2000,
            system=SYSTEM_PROMPT,
            thinking={"type": "adaptive"},
            messages=[{"role": "user", "content": text}],
        )
    except anthropic.APIStatusError as exc:
        raise RuntimeError(f"The API rejected the request ({exc.status_code}): {exc.message}")
    except anthropic.APIConnectionError as exc:
        raise RuntimeError(f"Could not reach the API: {exc}")

    # A refusal returns HTTP 200 with no usable content, so check before reading.
    if getattr(response, "stop_reason", None) == "refusal":
        category = getattr(getattr(response, "stop_details", None), "category", None)
        raise RuntimeError(f"The model declined to answer (category: {category}).")

    written = "".join(
        block.text for block in response.content if getattr(block, "type", None) == "text"
    ).strip()

    if not written:
        raise RuntimeError("The API returned no text.")

    save(conn, day, written, model=response.model, source="api")

    usage = response.usage
    return {
        "text": written,
        "model": response.model,
        "input_tokens": usage.input_tokens,
        "output_tokens": usage.output_tokens,
        "cost_usd": estimate_cost(model, usage.input_tokens, usage.output_tokens),
    }
