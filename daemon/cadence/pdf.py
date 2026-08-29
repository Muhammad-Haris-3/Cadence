"""A very small PDF writer: text, rules and filled rectangles.

Cadence installs with one `pip install -r requirements.txt` and no build step,
and a reporting library is a large thing to add to that for one button. A day
report needs no more than a typeface, a baseline and a coloured box, and PDF's
own drawing model is a handful of operators, so the format is written directly.

Only the fourteen fonts every reader has built in are used, which is what keeps
this small: no font file to embed, no subsetting, no glyph tables -- at the cost
of WinAnsi's character set, so anything outside it is transliterated on the way
in rather than silently dropped (see `encode`).

The coordinate system here is the one layout code thinks in: y counts *down*
from the top of the page, and a text y is its baseline. PDF's own origin is the
bottom-left corner, and the flip happens at the last moment, in the emitters.
"""

from typing import List, Optional, Union

# A4. The report is meant to be read on a screen and printed on either standard
# without reflowing, and A4 is the one that fits inside US Letter's width.
PAGE_WIDTH = 595.28
PAGE_HEIGHT = 841.89

FONTS = {
    "regular": ("F1", "Helvetica"),
    "bold": ("F2", "Helvetica-Bold"),
    "mono": ("F3", "Courier"),
    "mono-bold": ("F4", "Courier-Bold"),
}
FONT_ORDER = ("regular", "bold", "mono", "mono-bold")

# Character widths in 1/1000 em, for codes 32..126, taken from the Adobe core
# font metrics. Measuring is what makes right-alignment, centring and honest
# truncation possible; without it every column would have to be monospaced.
_HELVETICA = (
    278, 278, 355, 556, 556, 889, 667, 191, 333, 333, 389, 584, 278, 333, 278,
    278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 278, 278, 584, 584,
    584, 556, 1015, 667, 667, 722, 722, 667, 611, 778, 722, 278, 500, 667, 556,
    833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 278,
    278, 278, 469, 556, 333, 556, 556, 500, 556, 556, 278, 556, 556, 222, 222,
    500, 222, 833, 556, 556, 556, 556, 333, 500, 278, 556, 500, 722, 500, 500,
    500, 334, 260, 334, 584,
)
_HELVETICA_BOLD = (
    278, 333, 474, 556, 556, 889, 722, 238, 333, 333, 389, 584, 278, 333, 278,
    278, 556, 556, 556, 556, 556, 556, 556, 556, 556, 556, 333, 333, 584, 584,
    584, 611, 975, 722, 722, 722, 722, 667, 611, 778, 722, 278, 556, 722, 611,
    833, 722, 778, 667, 778, 722, 667, 611, 722, 667, 944, 667, 667, 611, 333,
    278, 333, 584, 556, 333, 556, 611, 556, 611, 556, 333, 611, 611, 278, 278,
    556, 278, 889, 611, 611, 611, 611, 389, 556, 333, 611, 556, 778, 556, 556,
    500, 389, 280, 389, 584,
)

# Everything outside the measured range: the accented Latin letters WinAnsi does
# carry sit close enough to their unaccented forms that one number covers them.
_FALLBACK_WIDTH = 556

# Characters the report is likely to meet that WinAnsi has no room for. Window
# titles are full of them -- em dashes from news sites, smart quotes from docs,
# arrows from terminals -- and a page of question marks reads as corruption, so
# they degrade to the nearest thing that is really there.
_TRANSLITERATE = {
    "‘": "'", "’": "'", "‚": ",", "“": '"', "”": '"',
    "–": "-", "—": "--", "…": "...", "•": "-",
    " ": " ", "→": "->", "←": "<-", "×": "x",
    "≤": "<=", "≥": ">=", "′": "'", "″": '"',
}


def encode(text: Optional[str]) -> bytes:
    """A string as WinAnsi bytes, with the unrepresentable made readable.

    Anything still outside the encoding after transliteration becomes '?' --
    emoji, CJK, most of the world's scripts. That is a real limitation of the
    built-in fonts rather than a shortcut, and it is confined to this function
    so that embedding a real font later would be a local change.
    """
    if not text:
        return b""
    for source, plain in _TRANSLITERATE.items():
        if source in text:
            text = text.replace(source, plain)
    return text.encode("cp1252", errors="replace")


def width_of(text: Union[str, bytes], font: str = "regular", size: float = 10) -> float:
    """How wide `text` will be, in points, set in `font` at `size`."""
    raw = text if isinstance(text, bytes) else encode(text)
    if font.startswith("mono"):
        return len(raw) * 0.6 * size      # Courier is 600/1000 for every glyph

    table = _HELVETICA_BOLD if font == "bold" else _HELVETICA
    total = 0
    for byte in raw:
        total += table[byte - 32] if 32 <= byte <= 126 else _FALLBACK_WIDTH
    return total * size / 1000.0


def ellipsize(text: str, font: str, size: float, limit: float) -> str:
    """`text`, shortened with an ellipsis until it fits inside `limit` points."""
    if width_of(text, font, size) <= limit:
        return text
    trimmed = text
    while trimmed and width_of(trimmed + "...", font, size) > limit:
        trimmed = trimmed[:-1]
    return (trimmed.rstrip() + "...") if trimmed else ""


def wrap(text: str, font: str, size: float, limit: float) -> List[str]:
    """Break `text` into lines that each fit inside `limit` points.

    A single word longer than the limit is left to overhang rather than being
    broken mid-word: it is nearly always a URL or a path, and both are easier to
    read intact than hyphenated.
    """
    lines, current = [], ""
    for word in (text or "").split():
        candidate = f"{current} {word}" if current else word
        if current and width_of(candidate, font, size) > limit:
            lines.append(current)
            current = word
        else:
            current = candidate
    if current:
        lines.append(current)
    return lines


def _num(value: float) -> str:
    """PDF numbers, without the trailing noise of full float repr."""
    return f"{value:.2f}".rstrip("0").rstrip(".") or "0"


def _rgb(color: str) -> str:
    """'#RRGGBB' as the three 0-1 components PDF's colour operators want."""
    value = color.lstrip("#")
    parts = (int(value[i:i + 2], 16) / 255.0 for i in (0, 2, 4))
    return " ".join(_num(part) for part in parts)


def _escape(raw: bytes) -> bytes:
    """Protect the three bytes that end a PDF string literal early."""
    out = bytearray()
    for byte in raw:
        if byte in (0x28, 0x29, 0x5C):      # ( ) and the escape character
            out.append(0x5C)
        out.append(byte)
    return bytes(out)


class Document:
    """A stack of pages, each an append-only stream of drawing operators."""

    def __init__(self, width: float = PAGE_WIDTH, height: float = PAGE_HEIGHT,
                 title: str = "", created: str = ""):
        self.width = width
        self.height = height
        self.title = title
        self.created = created
        self.pages: List[bytearray] = []
        # Which page drawing lands on. Normally the last one, but a footer pass
        # needs to go back over finished pages once the total is known.
        self.current = 0
        self.new_page()

    @property
    def page_count(self) -> int:
        return len(self.pages)

    def new_page(self) -> None:
        self.pages.append(bytearray())
        self.current = len(self.pages) - 1

    def _write(self, chunk: str) -> None:
        self.pages[self.current].extend(chunk.encode("cp1252", errors="replace"))

    # -- drawing -----------------------------------------------------------

    def text(self, x: float, y: float, body: str, font: str = "regular",
             size: float = 10, color: str = "#000000") -> float:
        """Draw `body` with its left edge at `x` and its baseline at `y`.

        Returns the x the text ended at, which is what lets a caller set a run
        of differently-styled words on one line without measuring twice.
        """
        raw = encode(body)
        if raw:
            alias = FONTS[font][0]
            self._write(
                f"BT {_rgb(color)} rg /{alias} {_num(size)} Tf "
                f"1 0 0 1 {_num(x)} {_num(self.height - y)} Tm "
            )
            self.pages[self.current].extend(b"(" + _escape(raw) + b") Tj ET\n")
        return x + width_of(raw, font, size)

    def text_right(self, right: float, y: float, body: str, font: str = "regular",
                   size: float = 10, color: str = "#000000") -> float:
        return self.text(right - width_of(body, font, size), y, body, font, size, color)

    def text_center(self, center: float, y: float, body: str, font: str = "regular",
                    size: float = 10, color: str = "#000000") -> float:
        return self.text(center - width_of(body, font, size) / 2, y, body, font, size, color)

    def rect(self, x: float, y: float, width: float, height: float,
             color: str = "#000000") -> None:
        """A filled rectangle with its *top* edge at `y`."""
        if width <= 0 or height <= 0:
            return
        self._write(
            f"{_rgb(color)} rg {_num(x)} {_num(self.height - y - height)} "
            f"{_num(width)} {_num(height)} re f\n"
        )

    def rule(self, x: float, y: float, to_x: float, color: str = "#E7E5E4",
             weight: float = 0.6) -> None:
        """A horizontal hairline. Drawn as a thin rectangle rather than a
        stroked path, so its weight is exact at any zoom instead of being
        rounded to a device pixel."""
        self.rect(x, y, to_x - x, weight, color)

    # -- output ------------------------------------------------------------

    def output(self) -> bytes:
        body = {}
        first_font = 3
        for index, name in enumerate(FONT_ORDER):
            body[first_font + index] = (
                "<< /Type /Font /Subtype /Type1 /BaseFont /%s "
                "/Encoding /WinAnsiEncoding >>" % FONTS[name][1]
            ).encode("latin-1")

        resources = "<< /Font << %s >> >>" % " ".join(
            f"/{FONTS[name][0]} {first_font + index} 0 R"
            for index, name in enumerate(FONT_ORDER)
        )

        next_id = first_font + len(FONT_ORDER)
        page_ids = []
        for stream in self.pages:
            page_id, content_id = next_id, next_id + 1
            next_id += 2
            page_ids.append(page_id)
            body[page_id] = (
                f"<< /Type /Page /Parent 2 0 R "
                f"/MediaBox [0 0 {_num(self.width)} {_num(self.height)}] "
                f"/Resources {resources} /Contents {content_id} 0 R >>"
            ).encode("latin-1")
            body[content_id] = (
                f"<< /Length {len(stream)} >>\nstream\n".encode("latin-1")
                + bytes(stream) + b"\nendstream"
            )

        info_id = next_id
        next_id += 1
        info = "<< /Producer (Cadence) /Creator (Cadence)"
        if self.title:
            info += " /Title (%s)" % _escape(encode(self.title)).decode("latin-1")
        if self.created:
            info += " /CreationDate (D:%s)" % self.created
        body[info_id] = (info + " >>").encode("latin-1")

        body[1] = b"<< /Type /Catalog /Pages 2 0 R >>"
        body[2] = (
            "<< /Type /Pages /Kids [%s] /Count %d >>"
            % (" ".join(f"{page_id} 0 R" for page_id in page_ids), len(page_ids))
        ).encode("latin-1")

        # The binary comment on the second line is conventional: it marks the
        # file as binary for anything that might otherwise line-ending-convert
        # the streams below and quietly corrupt them.
        out = bytearray(b"%PDF-1.4\n%\xe2\xe3\xcf\xd3\n")
        offsets = {}
        for object_id in range(1, next_id):
            offsets[object_id] = len(out)
            out += f"{object_id} 0 obj\n".encode("latin-1")
            out += body[object_id]
            out += b"\nendobj\n"

        start_xref = len(out)
        out += f"xref\n0 {next_id}\n".encode("latin-1")
        out += b"0000000000 65535 f \n"          # every entry is exactly 20 bytes
        for object_id in range(1, next_id):
            out += ("%010d 00000 n \n" % offsets[object_id]).encode("latin-1")
        out += (
            f"trailer\n<< /Size {next_id} /Root 1 0 R /Info {info_id} 0 R >>\n"
            f"startxref\n{start_xref}\n%%EOF\n"
        ).encode("latin-1")
        return bytes(out)
