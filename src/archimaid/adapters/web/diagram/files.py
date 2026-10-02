import re
import unicodedata


def filename_slug(name: str, fallback: str = "application") -> str:
    """Lower-case ASCII letters, digits and hyphens only; safe in a Content-Disposition header."""
    ascii_name = unicodedata.normalize("NFKD", name).encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-z0-9]+", "-", ascii_name.lower()).strip("-")[:60].strip("-")
    return slug or fallback
