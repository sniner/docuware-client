from __future__ import annotations

import pytest

from docuware import client, dialogs, filecabinet, organization

def _search_fields(dlg: dialogs.SearchDialog) -> dict:
    SAMPLE_FIELDS = [
        {"DBFieldName": "FIELD1", "DlgLabel": "TestField.1", "DWFieldType": "Text"},
        {"DBFieldName": "FIELD2", "DlgLabel": "TestField.2", "DWFieldType": "Numeric"},
    ]
    fields = [dialogs.SearchField(item, dlg) for item in SAMPLE_FIELDS]
    return {f.name:f for f in fields}

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
    assert condition_parser.parse('FIELD1=123') == [('FIELD1', ['123'])]
    assert condition_parser.parse('FIELD1="123","345"') == [('FIELD1', ['123', '345'])]

def test_condition_parser_list_str(condition_parser):
    assert condition_parser.parse(['FIELD1=123']) == [('FIELD1', ['123'])]
    assert condition_parser.parse(['FIELD1=123', 'FIELD2=345']) == [('FIELD1', ['123']), ('FIELD2', ['345'])]

def test_condition_parser_dict_str(condition_parser):
    assert condition_parser.parse({'FIELD1': '123'}) == [('FIELD1', ['123'])]
    assert condition_parser.parse({'FIELD1': ['123', '234'], 'FIELD2': '456'}) == [('FIELD1', ['123', '234']), ('FIELD2', ['456'])]
