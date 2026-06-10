from __future__ import annotations

import json
import stat
from unittest.mock import MagicMock, patch

import httpx
import pytest

from docuware import CredentialStore, DocuwareClient, errors
from docuware.client import connect, connect_with_tokens
from docuware.auth import TokenAuthenticator

BASE_URL = "https://example.com"

# connect_with_tokens is deprecated but still under test until removal
_DEPRECATION_OK = pytest.mark.filterwarnings(
    "ignore:connect_with_tokens is deprecated:DeprecationWarning"
)


def _auth_handler():
    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(
                200, json={"IdentityServiceUrl": f"{BASE_URL}/DocuWare/Identity"}
            )
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            return httpx.Response(200, json={"access_token": "test_token"})
        if path == "/DocuWare/Platform":
            return httpx.Response(200, json={"Version": "7.10", "Links": [], "Resources": []})
        return httpx.Response(404)

    return handler


def _patched_init(handler):
    """Returns a __init__ replacement that injects the mock transport."""
    original = DocuwareClient.__init__

    def patched(self, url, verify_certificate=True, timeout=None, authenticator=None):
        original(self, url, verify_certificate, timeout=timeout, authenticator=authenticator)
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
    creds_file.write_text(
        json.dumps({"url": BASE_URL, "username": "fileuser", "password": "filepass"})
    )
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        client = connect(credentials_file=creds_file)
    assert client.version == "7.10"


def test_connect_saves_credentials_to_file(tmp_path, monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    monkeypatch.delenv("DW_USERNAME", raising=False)
    monkeypatch.delenv("DW_PASSWORD", raising=False)
    creds_file = tmp_path / "new_creds.json"
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        connect(
            url=BASE_URL, username="saveuser", password="savepass", credentials_file=creds_file
        )
    assert creds_file.exists()
    saved = json.loads(creds_file.read_text())
    assert saved["username"] == "saveuser"
    assert saved["url"] == BASE_URL
    assert oct(stat.S_IMODE(creds_file.stat().st_mode)) == "0o600"


def test_connect_does_not_overwrite_unchanged_credentials(tmp_path, monkeypatch):
    monkeypatch.delenv("DW_URL", raising=False)
    monkeypatch.delenv("DW_USERNAME", raising=False)
    monkeypatch.delenv("DW_PASSWORD", raising=False)
    # Pre-write the bundle in the 0.8 shape (with method) so connect() reads
    # exactly what it would write — no rewrite expected.
    creds = {"method": "password", "url": BASE_URL, "username": "u", "password": "p"}
    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps(creds, indent=4))
    mtime_before = creds_file.stat().st_mtime
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_auth_handler())):
        connect(credentials_file=creds_file)
    assert creds_file.stat().st_mtime == mtime_before


# --- connect() with authenticator / credential_store DI ---


def test_connect_with_explicit_authenticator(tmp_path, monkeypatch):
    """Path 1: authenticator= wins; bundle gets saved to credential_store."""
    monkeypatch.delenv("DW_URL", raising=False)
    creds_file = tmp_path / "creds.json"
    from docuware.auth import ClientCredentialsAuthenticator
    from docuware.persistence import JsonFileCredentialStore

    cc_handler = _token_handler_for_client_credentials()
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(cc_handler)):
        connect(
            url=BASE_URL,
            authenticator=ClientCredentialsAuthenticator(
                client_id="cid", client_secret="sec",
            ),
            credential_store=JsonFileCredentialStore(creds_file),
        )
    saved = json.loads(creds_file.read_text())
    assert saved["method"] == "client_credentials"
    assert saved["url"] == BASE_URL
    assert saved["client_id"] == "cid"
    assert saved["client_secret"] == "sec"


def test_connect_rebuilds_authenticator_from_store(tmp_path, monkeypatch):
    """Path 2: populated store with method='client_credentials' rebuilds the auth."""
    monkeypatch.delenv("DW_URL", raising=False)
    creds_file = tmp_path / "creds.json"
    creds_file.write_text(json.dumps({
        "method": "client_credentials",
        "url": BASE_URL,
        "client_id": "stored_cid",
        "client_secret": "stored_sec",
        "scope": "docuware.platform",
    }))
    from docuware.auth import ClientCredentialsAuthenticator
    from docuware.persistence import JsonFileCredentialStore

    cc_handler = _token_handler_for_client_credentials()
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(cc_handler)):
        client = connect(credential_store=JsonFileCredentialStore(creds_file))
    assert isinstance(client.conn.authenticator, ClientCredentialsAuthenticator)
    assert client.conn.authenticator.client_id == "stored_cid"


def test_connect_credentials_file_and_credential_store_mutually_exclusive(tmp_path):
    from docuware.persistence import JsonFileCredentialStore
    with pytest.raises(ValueError, match="mutually exclusive"):
        connect(
            credentials_file=tmp_path / "a.json",
            credential_store=JsonFileCredentialStore(tmp_path / "b.json"),
        )


def _token_handler_for_client_credentials():
    """Mock the discovery + token endpoints for the client_credentials grant."""
    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(
                200, json={"IdentityServiceUrl": f"{BASE_URL}/DocuWare/Identity"}
            )
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            return httpx.Response(200, json={"access_token": "cc_at"})
        if path == "/DocuWare/Platform":
            return httpx.Response(200, json={"Version": "7.11", "Links": [], "Resources": []})
        return httpx.Response(404)
    return handler


# --- connect_with_tokens() ---


def _token_handler():
    """Handler for connect_with_tokens — no OAuth2 login, just Platform init."""

    def handler(req):
        path = req.url.path
        if path == "/DocuWare/Platform":
            return httpx.Response(200, json={"Version": "7.11", "Links": [], "Resources": []})
        return httpx.Response(404)

    return handler


@_DEPRECATION_OK
def test_connect_with_tokens_sets_version():
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        client = connect_with_tokens(
            url=BASE_URL,
            access_token="at_123",
            refresh_token="rt_456",
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
        )
    assert client.version == "7.11"
    assert isinstance(client.conn.authenticator, TokenAuthenticator)


@_DEPRECATION_OK
def test_connect_with_tokens_sets_bearer_auth():
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        client = connect_with_tokens(
            url=BASE_URL,
            access_token="at_123",
            refresh_token="rt_456",
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
        )
    assert client.conn.session.auth is not None
    assert client.conn.session.auth.token == "at_123"


@_DEPRECATION_OK
def test_connect_with_tokens_passes_callback():
    callback = MagicMock()
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        client = connect_with_tokens(
            url=BASE_URL,
            access_token="at_123",
            refresh_token="rt_456",
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            on_token_refresh=callback,
        )
    assert client.conn.authenticator.on_token_refresh is callback


# --- connect_with_tokens() with CredentialStore ---


class _MemoryCredentialStore(CredentialStore):
    """In-memory CredentialStore for tests; records every save() call."""

    def __init__(self, initial=None):
        self._bundle = initial
        self.saves: list = []

    def load(self):
        return self._bundle

    def save(self, tokens):
        self._bundle = dict(tokens)
        self.saves.append(dict(tokens))


@_DEPRECATION_OK
def test_connect_with_tokens_uses_store_tokens():
    store = _MemoryCredentialStore({"access_token": "from_store", "refresh_token": "rt_store"})
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        client = connect_with_tokens(
            url=BASE_URL,
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
        )
    assert client.conn.session.auth.token == "from_store"
    assert client.conn.authenticator.refresh_token == "rt_store"
    # on_token_refresh is auto-wired to a closure that calls store.save with
    # the full bundle (including the url field added by connect()).
    assert callable(client.conn.authenticator.on_token_refresh)
    # The minimal stored bundle gets enriched on first use — connect() writes
    # the full {method, client_id, access_token, refresh_token, token_endpoint, url}.
    assert len(store.saves) == 1
    enriched = store.saves[0]
    assert enriched["method"] == "token"
    assert enriched["url"] == BASE_URL
    assert enriched["access_token"] == "from_store"
    assert enriched["refresh_token"] == "rt_store"
    assert enriched["client_id"] == "test-client"


@_DEPRECATION_OK
def test_connect_with_tokens_bootstrap_seeds_empty_store():
    store = _MemoryCredentialStore()  # empty
    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        connect_with_tokens(
            url=BASE_URL,
            access_token="at_seed",
            refresh_token="rt_seed",
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
        )
    assert len(store.saves) == 1
    # Bootstrap writes the full bundle, not just access/refresh — so the next
    # process start can reconstruct the TokenAuthenticator from the store alone.
    assert store.saves[0] == {
        "method": "token",
        "url": BASE_URL,
        "client_id": "test-client",
        "access_token": "at_seed",
        "refresh_token": "rt_seed",
        "token_endpoint": "https://login.example.com/token",
    }


@_DEPRECATION_OK
def test_connect_with_tokens_empty_store_without_seed_raises():
    store = _MemoryCredentialStore()  # empty
    with pytest.raises(errors.AccountError, match="token_store is empty"):
        connect_with_tokens(
            url=BASE_URL,
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
        )


@_DEPRECATION_OK
def test_connect_with_tokens_store_and_callback_mutually_exclusive():
    store = _MemoryCredentialStore({"access_token": "a", "refresh_token": "r"})
    with pytest.raises(ValueError, match="mutually exclusive"):
        connect_with_tokens(
            url=BASE_URL,
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
            on_token_refresh=lambda t: None,
        )


@_DEPRECATION_OK
def test_connect_with_tokens_incomplete_store_bundle_raises():
    store = _MemoryCredentialStore({"access_token": "a"})  # no refresh_token
    with pytest.raises(errors.AccountError, match="incomplete bundle"):
        connect_with_tokens(
            url=BASE_URL,
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
        )


@_DEPRECATION_OK
def test_connect_with_tokens_refresh_triggers_store_save():
    """End-to-end: refresh → save() chain populates the store with rotated tokens."""
    store = _MemoryCredentialStore({"access_token": "old_at", "refresh_token": "old_rt"})

    with patch("docuware.client.DocuwareClient.__init__", _patched_init(_token_handler())):
        client = connect_with_tokens(
            url=BASE_URL,
            token_endpoint="https://login.example.com/token",
            client_id="test-client",
            token_store=store,
        )
    # First save: connect() enriches the minimal store bundle to the full shape.
    assert len(store.saves) == 1

    # TokenAuthenticator.authenticate() makes a one-shot httpx.post that does
    # not go through the patched session — patch the call directly.
    refresh_response = MagicMock()
    refresh_response.json.return_value = {
        "access_token": "new_at",
        "refresh_token": "new_rt",
        "expires_in": 3600,
    }
    refresh_response.raise_for_status.return_value = None
    with patch("docuware.auth.httpx.post", return_value=refresh_response) as mock_post:
        client.conn.authenticator.authenticate(client.conn)

    mock_post.assert_called_once()
    assert client.conn.authenticator.access_token == "new_at"
    assert client.conn.authenticator.refresh_token == "new_rt"
    # Second save: refresh callback persisted the rotated tokens via the store.
    assert len(store.saves) == 2
    assert store.saves[-1]["access_token"] == "new_at"
    assert store.saves[-1]["refresh_token"] == "new_rt"
    assert store.saves[-1]["url"] == BASE_URL
    assert store.saves[-1]["method"] == "token"


def test_credential_store_is_abstract():
    """CredentialStore cannot be instantiated without overriding load/save."""
    with pytest.raises(TypeError):
        CredentialStore()  # type: ignore[abstract]
