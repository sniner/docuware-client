from __future__ import annotations

import pathlib
from datetime import date, datetime
from unittest.mock import patch

import pytest

from docuware.errors import DataError, InternalError
from docuware.utils import (
    date_from_string,
    date_to_string,
    datetime_from_string,
    datetime_to_string,
    default_credentials_file,
    quote_value,
    random_password,
    safe_str,
    unique_filename,
    write_binary_file,
)

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


# --- safe_str() ---

def test_safe_str_printable_chars():
    assert safe_str("hello world") == "hello world"


def test_safe_str_removes_tab():
    assert safe_str("hello\tworld") == "helloworld"


def test_safe_str_removes_newline():
    assert safe_str("line\nnewline") == "linenewline"


def test_safe_str_removes_null():
    assert safe_str("null\x00char") == "nullchar"


def test_safe_str_removes_escape():
    assert safe_str("esc\x1bseq") == "escseq"


def test_safe_str_int_input():
    assert safe_str(42) == "42"


# --- _parse_timestamp() via datetime_from_string() ---

def test_datetime_from_string_negative_timestamp_raises():
    # /Date(-N)/ does not match the \d+ regex → DataError
    with pytest.raises(DataError):
        datetime_from_string("/Date(-86400000)/")


def test_datetime_from_string_invalid_format_raises():
    with pytest.raises(DataError):
        datetime_from_string("2024-01-01")


def test_datetime_from_string_overflow_timestamp():
    # Timestamp far beyond datetime range causes overflow → None
    result = datetime_from_string("/Date(9999999999999999)/")
    assert result is None


# --- datetime_from_string() auto_date ---

def test_datetime_from_string_auto_date_midnight():
    dt = datetime(2024, 1, 15, 0, 0, 0)
    ts_ms = int(dt.timestamp() * 1000)
    result = datetime_from_string(f"/Date({ts_ms})/", auto_date=True)
    assert isinstance(result, date)
    assert not isinstance(result, datetime)


def test_datetime_from_string_auto_date_with_time():
    dt = datetime(2024, 6, 15, 10, 30, 0)
    ts_ms = int(dt.timestamp() * 1000)
    result = datetime_from_string(f"/Date({ts_ms})/", auto_date=True)
    assert isinstance(result, datetime)


def test_datetime_from_string_no_auto_date():
    dt = datetime(2024, 1, 15, 0, 0, 0)
    ts_ms = int(dt.timestamp() * 1000)
    result = datetime_from_string(f"/Date({ts_ms})/")
    assert isinstance(result, datetime)


def test_datetime_from_string_zero_timestamp():
    # Design decision: /Date(0)/ is treated as missing (DocuWare uses 0 for "no date")
    result = datetime_from_string("/Date(0)/")
    assert result is None


# --- datetime_to_string() / date_to_string() round-trip ---

def test_datetime_to_string_round_trip():
    dt = datetime(2024, 6, 15, 14, 30, 0)
    encoded = datetime_to_string(dt)
    decoded = datetime_from_string(encoded)
    assert decoded == dt


def test_date_to_string_round_trip():
    d = date(2024, 6, 15)
    encoded = date_to_string(d)
    decoded = date_from_string(encoded)
    assert decoded == d


def test_datetime_to_string_format():
    dt = datetime(2024, 1, 15, 10, 30, 0)
    result = datetime_to_string(dt)
    assert result.startswith("/Date(")
    assert result.endswith(")/")


# --- unique_filename() ---

def test_unique_filename_nonexistent(tmp_path):
    path = tmp_path / "new_file.txt"
    assert unique_filename(path) == path


def test_unique_filename_existing(tmp_path):
    path = tmp_path / "file.txt"
    path.touch()
    assert unique_filename(path) == tmp_path / "file(1).txt"


def test_unique_filename_multiple_duplicates(tmp_path):
    base = tmp_path / "doc.pdf"
    base.touch()
    (tmp_path / "doc(1).pdf").touch()
    assert unique_filename(base) == tmp_path / "doc(2).pdf"


def test_unique_filename_limit_exceeded(tmp_path, monkeypatch):
    monkeypatch.setattr("docuware.utils.UNIQUE_FILENAME_LIMIT", 3)
    base = tmp_path / "doc.pdf"
    base.touch()
    for i in range(1, 4):
        (tmp_path / f"doc({i}).pdf").touch()
    with pytest.raises(InternalError):
        unique_filename(base)


# --- default_credentials_file() ---

def test_default_credentials_file_local(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    local = tmp_path / ".credentials"
    local.touch()
    result = default_credentials_file()
    assert result == pathlib.Path(".credentials")


def test_default_credentials_file_xdg(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    config_home = tmp_path / "config"
    monkeypatch.setenv("XDG_CONFIG_HOME", str(config_home))
    result = default_credentials_file()
    assert result == config_home / "docuware-client" / ".credentials"


def test_default_credentials_file_fallback(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("XDG_CONFIG_HOME", raising=False)
    fake_home = tmp_path / "home"
    fake_home.mkdir()
    with patch("pathlib.Path.home", return_value=fake_home):
        result = default_credentials_file()
    assert result == fake_home / ".docuware-client.cred"


# --- write_binary_file() ---

def test_write_binary_file_writes_content(tmp_path):
    path = tmp_path / "output.bin"
    data = b"hello world"
    result = write_binary_file(data, path)
    assert result == path
    assert path.read_bytes() == data


def test_write_binary_file_returns_path(tmp_path):
    path = tmp_path / "out.bin"
    result = write_binary_file(b"test", path)
    assert isinstance(result, pathlib.Path)


# --- random_password() ---

def test_random_password_default_length():
    assert len(random_password()) == 16


def test_random_password_custom_length():
    assert len(random_password(32)) == 32


def test_random_password_valid_chars():
    allowed = set("0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,;:-_/+=")
    pw = random_password(200)
    assert all(c in allowed for c in pw)
