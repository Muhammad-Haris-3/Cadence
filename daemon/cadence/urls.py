"""URL sanitizing.

Query strings are where credentials leak -- reset tokens, session ids, search
terms. A time tracker has no business storing them, so the default is to drop
the query entirely and keep only origin + path. The window title already
carries the human-readable "what" (the video name, the article headline), which
is what categorization actually needs.

The exception is the handful of params that ARE the content identifier rather
than a credential; those are allowlisted per host.
"""

from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

# host suffix -> query params worth keeping
KEEP_PARAMS = {
    "youtube.com": {"v", "list"},
    "youtu.be": {"v"},
    "github.com": set(),
    "stackoverflow.com": set(),
}

STRIP_FRAGMENT = True


def _keep_for(host: str) -> set:
    for suffix, params in KEEP_PARAMS.items():
        if host == suffix or host.endswith("." + suffix):
            return params
    return set()


def sanitize(raw: str) -> tuple[str, str]:
    """Return (sanitized_url, host). Both empty if the URL isn't trackable."""
    if not raw:
        return "", ""

    try:
        parts = urlsplit(raw)
    except ValueError:
        return "", ""

    # chrome://, about:, file://, devtools:// etc. are not browsing.
    if parts.scheme not in ("http", "https"):
        return "", ""

    host = (parts.hostname or "").lower()
    if not host:
        return "", ""

    keep = _keep_for(host)
    query = ""
    if keep:
        kept = [(k, v) for k, v in parse_qsl(parts.query, keep_blank_values=False) if k in keep]
        query = urlencode(kept)

    cleaned = urlunsplit((parts.scheme, host, parts.path, query, "" if STRIP_FRAGMENT else parts.fragment))
    return cleaned, host
