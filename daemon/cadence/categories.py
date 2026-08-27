"""App/title -> category, by plain rules.

Rize uses an ML model for this. For one person on one machine a rules file is
better: it is inspectable, editable, and never surprises you. Edit RULES freely.
"""

import re

# (category, [patterns matched case-insensitively against "app | title"])
RULES = [
    ("code",       [r"\bcode\.exe", r"devenv\.exe", r"pycharm", r"idea64", r"sublime_text",
                    r"windowsterminal", r"powershell", r"\bcmd\.exe", r"wezterm", r"alacritty"]),
    ("design",     [r"figma", r"photoshop", r"illustrator", r"blender"]),
    ("docs",       [r"winword", r"onenote", r"obsidian", r"notion", r"typora"]),
    ("comms",      [r"slack", r"discord", r"teams", r"outlook", r"whatsapp", r"telegram"]),
    ("learning",   [r"youtube.*(tutorial|course|docs|how to)", r"stackoverflow", r"\bdocs\.",
                    r"developer\.mozilla", r"coursera", r"udemy"]),
    ("distraction",[r"youtube", r"netflix", r"instagram", r"twitter", r"\bx\.com", r"reddit",
                    r"tiktok", r"facebook", r"twitch", r"monkeytype", r"steam"]),
    ("ai",         [r"claude", r"chatgpt", r"openai", r"perplexity", r"gemini"]),
    ("browsing",   [r"chrome\.exe", r"msedge\.exe", r"firefox\.exe", r"brave\.exe"]),
]

_COMPILED = [(name, [re.compile(p, re.I) for p in pats]) for name, pats in RULES]


def categorize(app: str, title: str = "", url: str = "") -> str:
    if app == "__idle__":
        return "idle"
    if app == "__locked__":
        return "away"

    haystack = f"{app} | {title} | {url}"
    for name, patterns in _COMPILED:
        if any(p.search(haystack) for p in patterns):
            return name
    return "other"


def backfill(conn, day=None) -> int:
    """Recategorize segments. Safe to rerun after editing RULES.

    Scoped to one day when given, so the sampler's periodic pass stays cheap as
    the database grows; unscoped for a full reprocess after a rules change.
    """
    if day is None:
        rows = conn.execute("SELECT id, app, title, url FROM segments").fetchall()
    else:
        rows = conn.execute(
            "SELECT id, app, title, url FROM segments WHERE day = ?", (day,)
        ).fetchall()
    for r in rows:
        conn.execute(
            "UPDATE segments SET category = ? WHERE id = ?",
            (categorize(r["app"], r["title"] or "", r["url"] or ""), r["id"]),
        )
    return len(rows)
