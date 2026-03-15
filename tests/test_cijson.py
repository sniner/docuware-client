from __future__ import annotations

import io
import json

import pytest

from docuware import cidict, cijson


# --- loads() / dumps() round-trip ---

def test_loads_case_insensitive_access():
    data = cijson.loads('{"Key": "value"}')
    assert data["Key"] == "value"
    assert data["key"] == "value"
    assert data["KEY"] == "value"


def test_loads_nested_dicts():
    data = cijson.loads('{"Outer": {"Inner": 42}}')
    assert isinstance(data["outer"], cidict.CaseInsensitiveDict)
    assert data["outer"]["inner"] == 42


def test_dumps_case_insensitive_dict():
    d = cidict.CaseInsensitiveDict({"Hello": "world"})
    result = cijson.dumps(d)
    parsed = json.loads(result)
    assert parsed["Hello"] == "world"


def test_round_trip():
    original = {"Name": "Test", "Value": 42}
    serialized = cijson.dumps(original)
    restored = cijson.loads(serialized)
    assert restored["Name"] == "Test"
    assert restored["name"] == "Test"
    assert restored["Value"] == 42


# --- load() / dump() file I/O ---

def test_dump_and_load_stringio():
    data = {"Alpha": "beta", "Count": 10}
    buf = io.StringIO()
    cijson.dump(data, buf)
    buf.seek(0)
    result = cijson.load(buf)
    assert isinstance(result, cidict.CaseInsensitiveDict)
    assert result["alpha"] == "beta"
    assert result["count"] == 10


def test_dump_writes_valid_json(tmp_path):
    path = tmp_path / "test.json"
    data = {"X": 1}
    with open(path, "w") as f:
        cijson.dump(data, f)
    parsed = json.loads(path.read_text())
    assert parsed["X"] == 1


def test_load_returns_case_insensitive(tmp_path):
    path = tmp_path / "test.json"
    path.write_text('{"Hello": "world"}')
    with open(path) as f:
        result = cijson.load(f)
    assert isinstance(result, cidict.CaseInsensitiveDict)
    assert result["HELLO"] == "world"


# --- CIJSONEncoder ---

def test_encoder_handles_case_insensitive_dict():
    d = cidict.CaseInsensitiveDict({"Key": "val"})
    result = json.dumps(d, cls=cijson.CIJSONEncoder)
    parsed = json.loads(result)
    assert parsed["Key"] == "val"


def test_encoder_raises_for_unknown_type():
    class _Weird:
        pass

    with pytest.raises(TypeError):
        json.dumps(_Weird(), cls=cijson.CIJSONEncoder)


# --- print_json() ---

def test_print_json_output(capsys):
    cijson.print_json({"Hello": "world"})
    captured = capsys.readouterr()
    assert "Hello" in captured.out
    assert "world" in captured.out


def test_print_json_indent(capsys):
    cijson.print_json({"a": {"b": 1}})
    captured = capsys.readouterr()
    lines = captured.out.splitlines()
    assert any(line.startswith("    ") for line in lines)
