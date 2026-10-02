import html
import re

# Characters XML 1.0 cannot carry (C0 controls except tab/newline/CR, lone surrogates, U+FFFE/F).
_FORBIDDEN = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\ud800-\udfff￾￿]")


def clean(text: str) -> str:
    return _FORBIDDEN.sub("", text)


def truncate(text: str, limit: int) -> str:
    text = clean(text)
    return text if len(text) <= limit else text[: limit - 1] + "…"


def text_width(text: str, size: float = 13) -> float:
    """Estimated rendered width: no font metrics are available, so 0.56 em per character."""
    return len(text) * size * 0.56


def escape(text: str) -> str:
    return html.escape(clean(text), quote=True)
