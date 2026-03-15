from __future__ import annotations

import json
import stat
from unittest.mock import MagicMock, patch

import httpx
import pytest

from docuware import DocuwareClient, errors
from docuware.client import connect

BASE_URL = "https://example.com"


def _auth_handler():
    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(200, json={"IdentityServiceUrl": f"{BASE_URL}/DocuWare/Identity"})
        if "openid-configuration" in path:
            return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
        if "/connect/token" in path:
            return httpx.Response(200, json={"access_token": "test_token"})
        if path == "/DocuWare/Platform":
            return httpx.Response(200, json={"Version": "7.10", "Links": [], "Resources": []})
        return httpx.Response(404)
    return handler


def _patched_init(handler):
    """Returns a __init__ replacement that injects the mock transport."""
    original = DocuwareClient.__init__

    def patched(self, url, verify_certificate=True):
        original(self, url, verify_certificate)
        self.conn.session = httpx.Client(transport=httpx.MockTransport(handler))

    return patched


# --- DocuwareClient.login ---

def test_login_sets_version():
    client = DocuwareClient(BASE_URL)
    client.conn.session = httpx.Client(transport=httpx.MockTransport(_auth_handler()))
    client.login("user", "pass")
    assert client.version == "7.10"


# --- DocuwareClient.logoff ---

def test_logoff_delegates_to_authenticator():
    client = DocuwareClient(BASE_URL)
    mock_auth = MagicMock()
    client.conn.authenticator = mock_auth
    client.logoff()
    mock_auth.logoff.assert_called_once_with(client.conn)


def test_logoff_noop_without_authenticator():
    client = DocuwareClient(BASE_URL)
    client.conn.authenticator = None
    client.logoff()  # must not raise


# --- connect() ---

def test_connect_raises_without_url(monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    with pytest.raises(errors.AccountError, match="URL is required"):
        connect()


def test_connect_uses_env_variables(monkeypatch):
    monkeypatch.setenv("DW_URL", BASE_URL)
    monkeypatch.setenv("DW_USERNAME", "envuser")
    monkeypatch.setenv("DW_PASSWORD", "envpass")
    monkeypatch.delenv("DW_ORG", raising=False)
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        client = connect()
    assert client.version == "7.10"


def test_connect_reads_credentials_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    monkeypatch.delenv("DW_USERNAME", raising=False)
    monkeypatch.delenv("DW_PASSWORD", raising=False)
    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps({"url": BASE_URL, "username": "fileuser", "password": "filepass"}))
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        client = connect(credentials_file=creds_file)
    assert client.version == "7.10"


def test_connect_saves_credentials_to_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    monkeypatch.delenv("DW_USERNAME", raising=False)
    monkeypatch.delenv("DW_PASSWORD", raising=False)
    creds_file = tmp_path / "new_creds.json"
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        connect(url=BASE_URL, username="saveuser", password="savepass", credentials_file=creds_file)
    assert creds_file.exists()
    saved = json.loads(creds_file.read_text())
    assert saved["username"] == "saveuser"
    assert saved["url"] == BASE_URL
    assert oct(stat.S_IMODE(creds_file.stat().st_mode)) == "0o600"


def test_connect_does_not_overwrite_unchanged_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    monkeypatch.delenv("DW_USERNAME", raising=False)
    monkeypatch.delenv("DW_PASSWORD", raising=False)
    creds = {"url": BASE_URL, "username": "u", "password": "p"}
    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps(creds))
    mtime_before = creds_file.stat().st_mtime
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        connect(credentials_file=creds_file)
    assert creds_file.stat().st_mtime == mtime_before
