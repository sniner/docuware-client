from __future__ import annotations

from datetime import date, datetime

import pytest

from docuware import client, dialogs, filecabinet, organization


def _search_fields(dlg: dialogs.SearchDialog) -> dict:
    SAMPLE_FIELDS = [
        {"DBFieldName": "FIELD1", "DlgLabel": "TestField.1", "DWFieldType": "Text"},
        {"DBFieldName": "FIELD2", "DlgLabel": "TestField.2", "DWFieldType": "Numeric"},
    ]
    fields = [dialogs.SearchField(item, dlg) for item in SAMPLE_FIELDS]
    return {f.name: f for f in fields}


def _search_dialog() -> dialogs.SearchDialog:
    dw = client.DocuwareClient("http://localhost")
    org = organization.Organization({}, dw)
    dlg = dialogs.SearchDialog({}, filecabinet.FileCabinet({}, org))
    dlg._fields = _search_fields(dlg)
    return dlg


@pytest.fixture
def search_dialog() -> dialogs.SearchDialog:
    return _search_dialog()


@pytest.fixture
def condition_parser() -> dialogs.ConditionParser:
    sd = _search_dialog()
    cp = dialogs.ConditionParser(sd)
    return cp


def test_condition_parser_str(condition_parser):
    assert condition_parser.parse("FIELD1=123") == [("FIELD1", ["123"])]
    assert condition_parser.parse('FIELD1="123","345"') == [("FIELD1", ["123", "345"])]


def test_condition_parser_list_str(condition_parser):
    assert condition_parser.parse(["FIELD1=123"]) == [("FIELD1", ["123"])]
    assert condition_parser.parse(["FIELD1=123", "FIELD2=345"]) == [
        ("FIELD1", ["123"]),
        ("FIELD2", ["345"]),
    ]


def test_condition_parser_dict_str(condition_parser):
    assert condition_parser.parse({"FIELD1": "123"}) == [("FIELD1", ["123"])]
    assert condition_parser.parse({"FIELD1": ["123", "234"], "FIELD2": "456"}) == [
        ("FIELD1", ["123", "234"]),
        ("FIELD2", ["456"]),
    ]


def test_condition_parser_dict_quotes_parens(condition_parser):
    # Default (PARTIAL): parentheses are auto-escaped
    assert condition_parser.parse({"FIELD1": "Gutschrift (eingehend)"}) == [
        ("FIELD1", ["Gutschrift \\(eingehend\\)"])
    ]


def test_condition_parser_dict_idempotent(condition_parser):
    # Already-escaped value must not be double-escaped
    assert condition_parser.parse({"FIELD1": "Gutschrift \\(eingehend\\)"}) == [
        ("FIELD1", ["Gutschrift \\(eingehend\\)"])
    ]


def test_condition_parser_dict_wildcard_preserved(condition_parser):
    # PARTIAL mode: * and ? are NOT escaped
    assert condition_parser.parse({"FIELD1": "Müller*"}) == [("FIELD1", ["Müller*"])]
    assert condition_parser.parse({"FIELD1": "Clever?123"}) == [("FIELD1", ["Clever?123"])]


def test_condition_parser_dict_quote_mode_all(condition_parser):
    # ALL mode: * and ? are also escaped
    assert condition_parser.parse({"FIELD1": "Müller*"}, quote=dialogs.QuoteMode.ALL) == [
        ("FIELD1", ["Müller\\*"])
    ]
    assert condition_parser.parse({"FIELD1": "Clever?123"}, quote=dialogs.QuoteMode.ALL) == [
        ("FIELD1", ["Clever\\?123"])
    ]


def test_condition_parser_dict_quote_mode_none(condition_parser):
    # NONE mode: nothing is escaped
    assert condition_parser.parse(
        {"FIELD1": "Gutschrift (eingehend)"}, quote=dialogs.QuoteMode.NONE
    ) == [("FIELD1", ["Gutschrift (eingehend)"])]


def test_condition_parser_str_not_auto_escaped(condition_parser):
    # String form is never auto-escaped — the raw string goes through as-is
    assert condition_parser.parse("FIELD1=Gutschrift (eingehend)") == [
        ("FIELD1", ["Gutschrift (eingehend)"])
    ]


def test_condition_parser_dict_none_single(condition_parser):
    # None as single value → EMPTY() (search for empty field)
    assert condition_parser.parse({"FIELD1": None}) == [("FIELD1", ["EMPTY()"])]


def test_condition_parser_dict_none_in_list(condition_parser):
    # None in a list → EMPTY() and must NOT be escaped even in ALL mode
    assert condition_parser.parse({"FIELD1": [None]}, quote=dialogs.QuoteMode.ALL) == [
        ("FIELD1", ["EMPTY()"])
    ]


def test_condition_parser_dict_datetime(condition_parser):
    # datetime value → ISO 8601 format
    dt = datetime(2024, 3, 15, 12, 0, 0)
    assert condition_parser.parse({"FIELD1": dt}) == [("FIELD1", ["2024-03-15T12:00:00"])]


def test_condition_parser_dict_date(condition_parser):
    # date value → ISO format "yyyy-mm-dd" (DocuWare search condition format)
    d = date(2024, 3, 15)
    assert condition_parser.parse({"FIELD1": d}) == [("FIELD1", ["2024-03-15"])]


def test_condition_parser_dict_datetime_not_escaped(condition_parser):
    # ISO 8601 contains no DocuWare metacharacters — QuoteMode has no effect
    dt = datetime(2024, 3, 15, 12, 0, 0)
    result = condition_parser.parse({"FIELD1": dt}, quote=dialogs.QuoteMode.ALL)
    assert result == [("FIELD1", ["2024-03-15T12:00:00"])]


def test_condition_parser_dict_datetime_in_list(condition_parser):
    # datetime in a list → ISO 8601 format
    dt = datetime(2024, 3, 15, 12, 0, 0)
    result = condition_parser.parse({"FIELD1": [dt]}, quote=dialogs.QuoteMode.ALL)
    assert result == [("FIELD1", ["2024-03-15T12:00:00"])]
