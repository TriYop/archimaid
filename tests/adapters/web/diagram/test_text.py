import pytest

from archimaid.adapters.web.diagram.files import filename_slug
from archimaid.adapters.web.diagram.text import clean, escape, text_width, truncate


def test_clean_removes_characters_xml_forbids_and_keeps_the_allowed_ones():
    # Review Focus test (1)
    assert clean("a\x00b\x0bc\x0cd\x1fe\ud800f￾g￿h") == "abcdefgh"
    assert clean("tab\there\nnew\rline") == "tab\there\nnew\rline"
    assert clean("café — 日本語") == "café — 日本語"


def test_escape_escapes_markup_and_cleans():
    assert escape('<a href="x">&\'</a>\x00') == "&lt;a href=&quot;x&quot;&gt;&amp;&#x27;&lt;/a&gt;"


def test_escaped_text_always_encodes_to_utf8():
    # Review Focus test (1): a lone surrogate would make .encode("utf-8") raise
    escape("bad \ud800 text").encode("utf-8")


def test_truncate_cuts_with_an_ellipsis_and_cleans():
    assert truncate("short", 10) == "short"
    assert truncate("exactly10!", 10) == "exactly10!"
    assert truncate("0123456789ABC", 10) == "012345678…"
    assert truncate("a\x00bc", 10) == "abc"


def test_text_width_is_proportional_to_length_and_size():
    assert text_width("") == 0
    assert text_width("abcd", 10) == pytest.approx(22.4)
    assert text_width("abcd") == pytest.approx(4 * 13 * 0.56)


@pytest.mark.parametrize(
    ("name", "slug"),
    [
        ("Billing", "billing"),
        ('Billing / "Core" <v2>', "billing-core-v2"),
        ("  Léa's  App  ", "lea-s-app"),
        ("../../etc/passwd", "etc-passwd"),
        ("日本語", "application"),
        ("", "application"),
        ("a\r\nContent-Type: text/html", "a-content-type-text-html"),
        ("x" * 200, "x" * 60),
    ],
)
def test_filename_slug_is_safe_ascii(name, slug):
    # Review Focus test (4)
    assert filename_slug(name) == slug
    assert all(c.isascii() and (c.isalnum() or c == "-") for c in filename_slug(name))
