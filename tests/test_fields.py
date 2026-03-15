from __future__ import annotations

from datetime import date, datetime

import pytest

from docuware.errors import DataError
from docuware.fields import (
    DateTimeFieldValue,
    DecimalFieldValue,
    FieldValue,
    IntFieldValue,
    KeywordsFieldValue,
    StringFieldValue,
)


def _make_config(**kwargs):
    base = {
        "FieldLabel": "My Field",
        "FieldName": "MY_FIELD",
        "ItemElementName": "String",
        "ReadOnly": False,
        "SystemField": False,
        "Item": "some value",
    }
    base.update(kwargs)
    return base


# --- FieldValue base class ---

def test_field_value_attributes():
    config = _make_config()
    fv = FieldValue(config)
    assert fv.name == "My Field"
    assert fv.id == "MY_FIELD"
    assert fv.content_type == "String"
    assert fv.read_only is False
    assert fv.internal is False
    assert fv.value == "some value"


def test_field_value_defaults():
    fv = FieldValue({})
    assert fv.name == ""
    assert fv.id == ""
    assert fv.content_type is None
    assert fv.read_only is True
    assert fv.internal is False
    assert fv.value is None


def test_field_value_str_contains_all_parts():
    config = _make_config()
    fv = FieldValue(config)
    s = str(fv)
    assert "My Field" in s
    assert "MY_FIELD" in s
    assert "String" in s
    assert "some value" in s


# --- from_config() dispatch ---

@pytest.mark.parametrize("type_name,expected_cls,item", [
    ("String", StringFieldValue, None),
    ("Keywords", KeywordsFieldValue, {"Keyword": []}),
    ("Int", IntFieldValue, None),
    ("Decimal", DecimalFieldValue, None),
    ("Date", DateTimeFieldValue, None),
    ("DateTime", DateTimeFieldValue, None),
])
def test_from_config_dispatch(type_name, expected_cls, item):
    config = {"ItemElementName": type_name, "Item": item}
    result = FieldValue.from_config(config)
    assert isinstance(result, expected_cls)


def test_from_config_unknown_type():
    config = {"ItemElementName": "Unknown", "Item": None}
    result = FieldValue.from_config(config)
    assert type(result) is FieldValue


@pytest.mark.parametrize("type_name", ["string", "STRING", "String"])
def test_from_config_case_insensitive(type_name):
    config = {"ItemElementName": type_name, "Item": None}
    result = FieldValue.from_config(config)
    assert isinstance(result, StringFieldValue)


# --- StringFieldValue ---

def test_string_field_value_converts_to_str():
    config = _make_config(ItemElementName="String", Item=42)
    fv = StringFieldValue(config)
    assert fv.value == "42"
    assert isinstance(fv.value, str)


def test_string_field_value_none():
    config = _make_config(ItemElementName="String", Item=None)
    fv = StringFieldValue(config)
    assert fv.value is None


def test_string_field_value_str_contains_text():
    config = _make_config(FieldLabel="Subject", FieldName="SUBJECT", ItemElementName="String", Item="Hello")
    fv = StringFieldValue(config)
    assert "Text" in str(fv)


# --- KeywordsFieldValue ---

def test_keywords_field_value_extracts_list():
    config = _make_config(
        ItemElementName="Keywords",
        Item={"Keyword": ["alpha", "beta"]},
    )
    fv = KeywordsFieldValue(config)
    assert fv.value == ["alpha", "beta"]


def test_keywords_field_value_empty_list():
    config = _make_config(
        ItemElementName="Keywords",
        Item={"Keyword": []},
    )
    fv = KeywordsFieldValue(config)
    assert fv.value is None


# --- IntFieldValue ---

def test_int_field_value_valid():
    config = _make_config(ItemElementName="Int", Item="42")
    fv = IntFieldValue(config)
    assert fv.value == 42


def test_int_field_value_none():
    config = _make_config(ItemElementName="Int", Item=None)
    fv = IntFieldValue(config)
    assert fv.value is None


def test_int_field_value_invalid():
    config = _make_config(ItemElementName="Int", Item="abc")
    with pytest.raises(DataError):
        IntFieldValue(config)


def test_int_field_value_str_contains_integer():
    config = _make_config(FieldLabel="Count", FieldName="CNT", ItemElementName="Int", Item="5")
    fv = IntFieldValue(config)
    assert "Integer" in str(fv)


# --- DecimalFieldValue ---

def test_decimal_field_value_valid():
    config = _make_config(ItemElementName="Decimal", Item="3.14")
    fv = DecimalFieldValue(config)
    assert fv.value == pytest.approx(3.14)


def test_decimal_field_value_none():
    config = _make_config(ItemElementName="Decimal", Item=None)
    fv = DecimalFieldValue(config)
    assert fv.value is None


def test_decimal_field_value_invalid():
    config = _make_config(ItemElementName="Decimal", Item="abc")
    with pytest.raises(DataError):
        DecimalFieldValue(config)


def test_decimal_field_value_str_contains_decimal():
    config = _make_config(FieldLabel="Price", FieldName="PRICE", ItemElementName="Decimal", Item="9.99")
    fv = DecimalFieldValue(config)
    assert "Decimal" in str(fv)


# --- DateTimeFieldValue ---

def test_datetime_field_value_date_type():
    # /Date(86400000)/ = 1 day after epoch; result type must be date (not datetime)
    config = _make_config(ItemElementName="Date", Item="/Date(86400000)/")
    fv = DateTimeFieldValue(config)
    assert isinstance(fv.value, date)
    assert not isinstance(fv.value, datetime)


def test_datetime_field_value_datetime_type():
    config = _make_config(ItemElementName="DateTime", Item="/Date(86400000)/")
    fv = DateTimeFieldValue(config)
    assert isinstance(fv.value, datetime)


def test_datetime_field_value_none():
    config = _make_config(ItemElementName="Date", Item=None)
    fv = DateTimeFieldValue(config)
    assert fv.value is None
