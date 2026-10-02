import html
import re
import unicodedata

# Characters XML 1.0 cannot carry (C0 controls except tab/newline/CR, lone surrogates, U+FFFE/F).
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def clean(text: str) -> str:
    return _FORBIDDEN.sub("", text)


def display_len(text: str) -> int:
    """Width in text columns: full-width (CJK) characters count for two."""
    return sum(2 if unicodedata.east_asian_width(c) in ("W", "F") else 1 for c in text)


def truncate(text: str, limit: int) -> str:
    text = clean(text)
    if display_len(text) <= limit:
        return text
    out, used = [], 0
    for c in text:
        width = display_len(c)
        if used + width > limit - 1:
            break
        out.append(c)
        used += width
    return "".join(out) + "…"


def text_width(text: str, size: float = 13) -> float:
    """Estimated rendered width: no font metrics are available, so 0.56 em per column."""
    return display_len(text) * size * 0.56


def escape(text: str) -> str:
    return html.escape(clean(text), quote=True)
