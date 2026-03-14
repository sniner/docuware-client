from __future__ import annotations

from docuware.utils import quote_value

PARTIAL = frozenset("()")
ALL = frozenset("()?*")
NONE = frozenset()


def test_quote_parens():
    assert quote_value("Gutschrift (eingehend)", PARTIAL) == "Gutschrift \\(eingehend\\)"


def test_quote_idempotent():
    assert quote_value("Gutschrift \\(eingehend\\)", PARTIAL) == "Gutschrift \\(eingehend\\)"


def test_quote_no_special_chars():
    assert quote_value("plain value", PARTIAL) == "plain value"


def test_quote_wildcard_preserved_partial():
    assert quote_value("Müller*", PARTIAL) == "Müller*"
    assert quote_value("Clever?123", PARTIAL) == "Clever?123"


def test_quote_wildcard_escaped_all():
    assert quote_value("Müller*", ALL) == "Müller\\*"
    assert quote_value("Clever?123", ALL) == "Clever\\?123"


def test_quote_none_chars():
    assert quote_value("Gutschrift (eingehend)", NONE) == "Gutschrift (eingehend)"


def test_quote_empty_string():
    assert quote_value("", PARTIAL) == ""


def test_quote_only_special_chars():
    assert quote_value("()", PARTIAL) == "\\(\\)"


def test_quote_backslash_passthrough():
    # Backslash not followed by a special char: passes through unchanged
    assert quote_value("C:\\Documents", PARTIAL) == "C:\\Documents"


def test_quote_multiple_parens():
    assert quote_value("(a) and (b)", PARTIAL) == "\\(a\\) and \\(b\\)"
