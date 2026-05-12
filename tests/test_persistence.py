from __future__ import annotations

import json
import pathlib
import stat
import warnings

import pytest

from docuware import CredentialStore, JsonFileCredentialStore, TokenStore


# --- JsonFileCredentialStore ---


def test_load_returns_none_when_file_missing(tmp_path: pathlib.Path):
    store = JsonFileCredentialStore(tmp_path / "missing.json")
    assert store.load() is None


def test_save_then_load_roundtrip(tmp_path: pathlib.Path):
    path = tmp_path / "creds.json"
    bundle = {
        "method": "password",
        "url": "https://example.com",
        "username": "alice",
        "password": "secret",
        "organization": "Acme",
    }
    JsonFileCredentialStore(path).save(bundle)
    assert JsonFileCredentialStore(path).load() == bundle


def test_save_sets_mode_0o600(tmp_path: pathlib.Path):
    path = tmp_path / "creds.json"
    JsonFileCredentialStore(path).save({"method": "password"})
    mode = stat.S_IMODE(path.stat().st_mode)
    assert mode == 0o600, f"expected 0o600, got 0o{mode:o}"


def test_save_creates_parent_directories(tmp_path: pathlib.Path):
    path = tmp_path / "deep" / "nested" / "creds.json"
    JsonFileCredentialStore(path).save({"method": "password"})
    assert path.exists()


def test_save_is_atomic_no_tmp_leftover(tmp_path: pathlib.Path):
    """After a successful save no half-written temp file may linger."""
    path = tmp_path / "creds.json"
    JsonFileCredentialStore(path).save({"method": "password"})
    siblings = list(tmp_path.iterdir())
    assert siblings == [path], f"unexpected leftovers: {siblings}"


def test_load_returns_none_on_corrupt_json(tmp_path: pathlib.Path, caplog):
    path = tmp_path / "creds.json"
    path.write_text("{not valid json", encoding="utf-8")
    with caplog.at_level("WARNING", logger="docuware.persistence"):
        assert JsonFileCredentialStore(path).load() is None
    assert any("Failed to load credentials" in r.message for r in caplog.records)


def test_load_tolerates_utf8_bom(tmp_path: pathlib.Path):
    """Files written by Windows tools often carry a UTF-8 BOM."""
    path = tmp_path / "creds.json"
    path.write_bytes(b"\xef\xbb\xbf" + json.dumps({"url": "x"}).encode("utf-8"))
    assert JsonFileCredentialStore(path).load() == {"url": "x"}


def test_path_expanduser_resolves_tilde(tmp_path: pathlib.Path, monkeypatch):
    monkeypatch.setenv("HOME", str(tmp_path))
    store = JsonFileCredentialStore("~/creds.json")
    assert store.path == tmp_path / "creds.json"


def test_accepts_string_path(tmp_path: pathlib.Path):
    path = tmp_path / "creds.json"
    store = JsonFileCredentialStore(str(path))
    store.save({"method": "password"})
    assert store.load() == {"method": "password"}


def test_default_path_when_no_arg(monkeypatch, tmp_path):
    """No-arg construction uses default_credentials_file()."""
    monkeypatch.setenv("XDG_CONFIG_HOME", str(tmp_path))
    from docuware.utils import default_credentials_file
    store = JsonFileCredentialStore()
    assert store.path == pathlib.Path(default_credentials_file()).expanduser()


# --- TokenStore deprecated alias ---


def test_tokenstore_subclassing_warns():
    with pytest.warns(DeprecationWarning, match="TokenStore is deprecated"):
        class _TS(TokenStore):
            def load(self):
                return None
            def save(self, bundle):
                pass


def test_tokenstore_subclass_still_works_as_credential_store():
    """Backwards-compat: a TokenStore subclass behaves as a CredentialStore."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)

        class _LegacyStore(TokenStore):
            def __init__(self):
                self.bundle = None
            def load(self):
                return self.bundle
            def save(self, bundle):
                self.bundle = dict(bundle)

    s = _LegacyStore()
    assert isinstance(s, CredentialStore)
    assert s.load() is None
    s.save({"access_token": "x"})
    assert s.load() == {"access_token": "x"}
