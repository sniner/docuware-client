from __future__ import annotations

import pytest

from docuware.cidict import CaseInsensitiveDict

KEY1 = "key1"
KEY2 = "Key2"
KEY3 = "KEY3"

VALUE1 = "value1"
VALUE2 = "value2"
VALUE3 = "value3"

ITEM1 = (KEY1, VALUE1)
ITEM2 = (KEY2, VALUE2)
ITEM3 = (KEY3, VALUE3)

ITEMS = [ITEM1, ITEM2, ITEM3]


@pytest.fixture
def test_dict() -> CaseInsensitiveDict[str]:
    return CaseInsensitiveDict(ITEMS)


def test_get(test_dict):
    assert test_dict.get("KEY1") == VALUE1
    assert test_dict.get("Key1") == VALUE1
    assert test_dict.get("key1") == VALUE1
    assert test_dict.get("KEY2") == VALUE2
    assert test_dict.get("KEY3") == VALUE3
    assert test_dict.get("KEY4") is None


def test_getitem(test_dict):
    assert test_dict["KEY1"] == VALUE1
    assert test_dict["KEY2"] == VALUE2
    assert test_dict["KEY3"] == VALUE3
    with pytest.raises(KeyError):
        assert test_dict["KEY4"] is None


def test_setitem(test_dict):
    VALUE1A = VALUE1 + "a"
    assert test_dict.get("KEY1") == VALUE1
    test_dict["key1"] = VALUE1A
    assert test_dict.get("KEY1") == VALUE1A
    assert test_dict.get("key1") == VALUE1A


def test_delete(test_dict):
    del test_dict["KeY2"]
    assert list(test_dict.keys()) == [KEY1, KEY3]


def test_keys(test_dict):
    assert list(test_dict.keys()) == [KEY1, KEY2, KEY3]


def test_values(test_dict):
    assert list(test_dict.values()) == [VALUE1, VALUE2, VALUE3]


def test_items(test_dict):
    assert list(test_dict.items()) == ITEMS


def test_length(test_dict):
    assert len(test_dict) == 3


def test_eq(test_dict):
    assert test_dict == CaseInsensitiveDict([ITEM3, ITEM1, ITEM2])
    assert test_dict != CaseInsensitiveDict([ITEM1, ITEM2])


def test_copy(test_dict):
    dup = test_dict.copy()
    assert test_dict == dup


def test_repr(test_dict):
    r = "{" + ", ".join(f"'{k}': '{v}'" for k, v in ITEMS) + "}"
    assert repr(test_dict) == r
