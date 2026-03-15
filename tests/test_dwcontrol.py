from __future__ import annotations

import xml.etree.ElementTree as ET
from datetime import date, datetime

import pytest

from docuware.dwcontrol import ControlFile, FieldItem, FieldType


# --- FieldType ---

def test_field_type_text():
    assert FieldType.TEXT == "Text"

def test_field_type_date():
    assert FieldType.DATE == "Date"

def test_field_type_datetime():
    assert FieldType.DATETIME == "DateTime"

def test_field_type_keyword():
    assert FieldType.KEYWORD == "Keyword"

def test_field_type_memo():
    assert FieldType.MEMO == "Memo"

def test_field_type_numeric():
    assert FieldType.NUMERIC == "Numeric"


# --- FieldItem.to_dict() ---

def test_field_item_to_dict_required_fields():
    item = FieldItem(name="MyField", kind=FieldType.TEXT, value="Hello")
    d = item.to_dict()
    assert d["dbName"] == "MyField"
    assert d["type"] == "Text"
    assert d["value"] == "Hello"


def test_field_item_to_dict_with_attrs():
    item = FieldItem(name="Amount", kind=FieldType.NUMERIC, value="3.14", attrs={"digits": "2"})
    d = item.to_dict()
    assert d["dbName"] == "Amount"
    assert d["type"] == "Numeric"
    assert d["value"] == "3.14"
    assert d["digits"] == "2"


def test_field_item_to_dict_no_attrs():
    item = FieldItem(name="Name", kind=FieldType.TEXT, value="Test")
    d = item.to_dict()
    assert set(d.keys()) == {"dbName", "type", "value"}


# --- ControlFile.add_field() type detection ---

def test_add_field_datetime():
    cf = ControlFile()
    cf.add_field("ts", datetime(2024, 1, 15, 10, 30))
    f = cf.fields[0]
    assert f.kind == FieldType.DATETIME
    assert f.value == "15.01.2024 10:30"
    assert f.attrs["culture"] == "de-DE"
    assert f.attrs["format"] == "dd.MM.yyyy H:mm"


def test_add_field_date():
    cf = ControlFile()
    cf.add_field("d", date(2024, 1, 15))
    f = cf.fields[0]
    assert f.kind == FieldType.DATE
    assert f.value == "15.01.2024"
    assert f.attrs["culture"] == "de-DE"
    assert f.attrs["format"] == "dd.MM.yyyy"


def test_add_field_float_default_digits():
    cf = ControlFile()
    cf.add_field("amount", 3.14)
    f = cf.fields[0]
    assert f.kind == FieldType.NUMERIC
    assert f.attrs["digits"] == 2


def test_add_field_float_custom_digits():
    cf = ControlFile()
    cf.add_field("amount", 3.14, digits=4)
    f = cf.fields[0]
    assert f.attrs["digits"] == 4


def test_add_field_int():
    cf = ControlFile()
    cf.add_field("count", 42)
    f = cf.fields[0]
    assert f.kind == FieldType.NUMERIC
    assert "digits" not in f.attrs


def test_add_field_str():
    cf = ControlFile()
    cf.add_field("name", "Hallo")
    f = cf.fields[0]
    assert f.kind == FieldType.TEXT


def test_add_field_type_override():
    cf = ControlFile()
    cf.add_field("note", "some text", field_type=FieldType.MEMO)
    f = cf.fields[0]
    assert f.kind == FieldType.MEMO


def test_add_field_culture_override():
    cf = ControlFile()
    cf.add_field("d", date(2024, 1, 15), culture="en-US")
    f = cf.fields[0]
    assert f.attrs["culture"] == "en-US"


def test_add_field_format_override():
    cf = ControlFile()
    cf.add_field("d", date(2024, 1, 15), format="MM/dd/yyyy")
    f = cf.fields[0]
    assert f.attrs["format"] == "MM/dd/yyyy"


# --- Fluent interface ---

def test_add_field_returns_self():
    cf = ControlFile()
    result = cf.add_field("a", "x").add_field("b", "y")
    assert result is cf
    assert len(cf.fields) == 2


# --- ControlFile.to_xml() ---

_NS = "http://dev.docuware.com/Jobs/Control"
_NP = f"{{{_NS}}}"  # namespace prefix for ET lookups: {ns}Tag


def test_to_xml_has_namespaces():
    cf = ControlFile()
    xml = cf.to_xml()
    assert f'xmlns="{_NS}"' in xml
    assert 'xmlns:xsi="http://www.w3.org/2001/XMLSchema-instance"' in xml


def test_to_xml_basket():
    cf = ControlFile(basket="MyBasket")
    root = ET.fromstring(cf.to_xml())
    page = root.find(f"{_NP}Page")
    assert page is not None
    basket = page.find(f"{_NP}Basket")
    assert basket is not None
    assert basket.attrib["name"] == "MyBasket"


def test_to_xml_file_cabinet():
    cf = ControlFile(file_cabinet="MyFC")
    root = ET.fromstring(cf.to_xml())
    page = root.find(f"{_NP}Page")
    assert page is not None
    fc = page.find(f"{_NP}FileCabinet")
    assert fc is not None
    assert fc.attrib["name"] == "MyFC"


def test_to_xml_no_basket():
    cf = ControlFile()
    root = ET.fromstring(cf.to_xml())
    page = root.find(f"{_NP}Page")
    assert page is not None
    assert page.find(f"{_NP}Basket") is None


def test_to_xml_no_file_cabinet():
    cf = ControlFile()
    root = ET.fromstring(cf.to_xml())
    page = root.find(f"{_NP}Page")
    assert page is not None
    assert page.find(f"{_NP}FileCabinet") is None


def test_to_xml_fields():
    cf = ControlFile()
    cf.add_field("Name", "Mustermann").add_field("Count", 5)
    root = ET.fromstring(cf.to_xml())
    page = root.find(f"{_NP}Page")
    assert page is not None
    fields = page.findall(f"{_NP}Field")
    assert len(fields) == 2
    names = {f.attrib["dbName"] for f in fields}
    assert "Name" in names
    assert "Count" in names


def test_str_equals_to_xml():
    cf = ControlFile(basket="B")
    cf.add_field("x", "y")
    assert str(cf) == cf.to_xml()
