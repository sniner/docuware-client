from __future__ import annotations

import http.client
import threading
import time
import urllib.parse
from unittest.mock import MagicMock, patch

import httpx
import pytest

from docuware import errors, oauth
from docuware.auth import BearerAuth, PkceAuthenticator
from docuware.conn import Connection

BASE = "https://dw.example.com"


def _conn():
    c = Connection(BASE)
    c.session = httpx.Client(transport=httpx.MockTransport(lambda r: httpx.Response(404)))
    return c


# --- login with stored tokens reuses them, no PKCE flow ---


def test_login_with_stored_tokens_applies_bearer_no_flow():
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="at",
        refresh_token="rt",
        token_endpoint="https://login.example/token",
    )
    conn = _conn()
    with patch.object(auth, "_run_pkce_flow") as flow:
        auth.login(conn)
    flow.assert_not_called()
    assert isinstance(conn.session.auth, BearerAuth)
    assert isinstance(conn.session.auth, BearerAuth)
    assert conn.session.auth.token == "at"


def test_login_without_tokens_runs_pkce_flow():
    auth = PkceAuthenticator(client_id="cid")
    conn = _conn()
    with patch.object(auth, "_run_pkce_flow") as flow:
        def _populate(c):
            auth.access_token = "fresh_at"
            auth.refresh_token = "fresh_rt"
        flow.side_effect = _populate
        auth.login(conn)
    flow.assert_called_once_with(conn)
    assert isinstance(conn.session.auth, BearerAuth)
    assert conn.session.auth.token == "fresh_at"


# --- authenticate() = refresh_token grant ---


def _refresh_response(at: str = "new_at", rt: str = "new_rt"):
    r = MagicMock()
    r.json.return_value = {"access_token": at, "refresh_token": rt, "expires_in": 3600}
    r.raise_for_status.return_value = None
    return r


def test_authenticate_calls_token_endpoint_and_rotates():
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="old_at",
        refresh_token="old_rt",
        token_endpoint="https://login.example/token",
    )
    conn = _conn()
    with patch("docuware.auth.httpx.post", return_value=_refresh_response()) as post:
        auth.authenticate(conn)
    post.assert_called_once()
    sent_data = post.call_args.kwargs.get("data") or post.call_args[0][-1]
    assert sent_data["grant_type"] == "refresh_token"
    assert sent_data["refresh_token"] == "old_rt"
    assert sent_data["client_id"] == "cid"
    assert "client_secret" not in sent_data  # public client
    assert auth.access_token == "new_at"
    assert auth.refresh_token == "new_rt"
    assert isinstance(conn.session.auth, BearerAuth)
    assert conn.session.auth.token == "new_at"


def test_authenticate_passes_client_secret_for_confidential_client():
    auth = PkceAuthenticator(
        client_id="cid",
        client_secret="webapp_secret",
        access_token="old_at",
        refresh_token="old_rt",
        token_endpoint="https://login.example/token",
    )
    with patch("docuware.auth.httpx.post", return_value=_refresh_response()) as post:
        auth.authenticate(_conn())
    sent_data = post.call_args.kwargs.get("data")
    assert sent_data is not None
    assert sent_data["client_secret"] == "webapp_secret"


def test_authenticate_invokes_on_token_refresh_with_bundle():
    captured = []
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="old_at",
        refresh_token="old_rt",
        token_endpoint="https://login.example/token",
        on_token_refresh=lambda b: captured.append(b),
    )
    with patch("docuware.auth.httpx.post", return_value=_refresh_response()):
        auth.authenticate(_conn())
    assert len(captured) == 1
    bundle = captured[0]
    assert bundle["method"] == "pkce"
    assert bundle["access_token"] == "new_at"
    assert bundle["refresh_token"] == "new_rt"


def test_authenticate_raises_when_no_refresh_token():
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="at",
        refresh_token=None,
        token_endpoint="https://login.example/token",
    )
    with pytest.raises(errors.AccountError, match="no refresh_token or token_endpoint"):
        auth.authenticate(_conn())


def test_authenticate_400_means_revoked():
    err_response = MagicMock()
    err_response.status_code = 400
    http_error = httpx.HTTPStatusError("400", request=MagicMock(), response=err_response)

    def _raise():
        raise http_error

    bad = MagicMock()
    bad.raise_for_status.side_effect = _raise

    auth = PkceAuthenticator(
        client_id="cid",
        access_token="at",
        refresh_token="rt",
        token_endpoint="https://login.example/token",
    )
    with patch("docuware.auth.httpx.post", return_value=bad):
        with pytest.raises(errors.AccountError, match="Refresh token expired or revoked"):
            auth.authenticate(_conn())


# --- to_bundle / from_bundle ---


def test_to_bundle_public_client_omits_secret():
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="at",
        refresh_token="rt",
        token_endpoint="https://login.example/token",
    )
    bundle = auth.to_bundle()
    assert bundle == {
        "method": "pkce",
        "client_id": "cid",
        "access_token": "at",
        "refresh_token": "rt",
        "token_endpoint": "https://login.example/token",
    }
    assert "client_secret" not in bundle


def test_to_bundle_confidential_client_includes_secret():
    auth = PkceAuthenticator(
        client_id="cid",
        client_secret="sec",
        access_token="at",
        refresh_token="rt",
        token_endpoint="https://login.example/token",
    )
    assert auth.to_bundle()["client_secret"] == "sec"


def test_from_bundle_roundtrip():
    bundle = {
        "method": "pkce",
        "client_id": "cid",
        "access_token": "at",
        "refresh_token": "rt",
        "token_endpoint": "https://login.example/token",
    }
    rebuilt = PkceAuthenticator.from_bundle(bundle)
    assert rebuilt.to_bundle() == bundle


def test_logoff_clears_tokens():
    auth = PkceAuthenticator(
        client_id="cid",
        access_token="at",
        refresh_token="rt",
        token_endpoint="https://login.example/token",
    )
    conn = _conn()
    conn.session.auth = BearerAuth("at")
    auth.logoff(conn)
    assert auth.access_token is None
    assert auth.refresh_token is None
    assert conn.session.auth is None


# --- End-to-end PKCE flow with fake browser ---


def test_pkce_flow_end_to_end_with_fake_browser():
    """Full PKCE round-trip — local callback server, mocked OAuth helpers."""
    captured_url = []

    def fake_browser(auth_url: str) -> None:
        captured_url.append(auth_url)
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
        state = qs["state"][0]
        redirect_uri = qs["redirect_uri"][0]
        cb = urllib.parse.urlparse(redirect_uri)

        def fire():
            time.sleep(0.05)  # let HTTPServer.handle_request() be entered
            c = http.client.HTTPConnection(cb.hostname or "", cb.port)
            c.request("GET", f"{cb.path}?code=AUTHCODE&state={state}")
            c.getresponse().read()
            c.close()

        threading.Thread(target=fire, daemon=True).start()

    on_refresh_calls = []
    auth = PkceAuthenticator(
        client_id="cid",
        redirect_port=0,
        on_browser_open=fake_browser,
        on_token_refresh=lambda b: on_refresh_calls.append(b),
    )

    fake_endpoints = oauth.OAuthEndpoints(
        authorization_endpoint="https://login.example/authorize",
        token_endpoint="https://login.example/token",
        identity_service_url="https://login.example",
    )
    with patch("docuware.oauth.discover_oauth_endpoints", return_value=fake_endpoints), \
         patch(
             "docuware.oauth.exchange_pkce_code",
             return_value={"access_token": "AT123", "refresh_token": "RT456"},
         ):
        auth._run_pkce_flow(_conn())

    assert captured_url and captured_url[0].startswith("https://login.example/authorize?")
    assert auth.access_token == "AT123"
    assert auth.refresh_token == "RT456"
    assert auth.token_endpoint == "https://login.example/token"
    assert len(on_refresh_calls) == 1
    assert on_refresh_calls[0]["access_token"] == "AT123"


def test_pkce_flow_state_mismatch_raises():
    """An attacker-supplied callback with wrong state must be rejected."""
    def evil_browser(auth_url: str) -> None:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
        redirect_uri = qs["redirect_uri"][0]
        cb = urllib.parse.urlparse(redirect_uri)

        def fire():
            time.sleep(0.05)
            c = http.client.HTTPConnection(cb.hostname or "", cb.port)
            c.request("GET", f"{cb.path}?code=AUTHCODE&state=WRONG")
            c.getresponse().read()
            c.close()

        threading.Thread(target=fire, daemon=True).start()

    auth = PkceAuthenticator(
        client_id="cid",
        redirect_port=0,
        on_browser_open=evil_browser,
    )
    fake_endpoints = oauth.OAuthEndpoints(
        "https://login.example/authorize", "https://login.example/token", "https://login.example",
    )
    with patch("docuware.oauth.discover_oauth_endpoints", return_value=fake_endpoints):
        with pytest.raises(errors.AccountError, match="state mismatch"):
            auth._run_pkce_flow(_conn())


def test_pkce_flow_error_callback_raises():
    """If DocuWare redirects back with ?error=..., the authenticator must raise."""
    def err_browser(auth_url: str) -> None:
        qs = urllib.parse.parse_qs(urllib.parse.urlparse(auth_url).query)
        redirect_uri = qs["redirect_uri"][0]
        cb = urllib.parse.urlparse(redirect_uri)

        def fire():
            time.sleep(0.05)
            c = http.client.HTTPConnection(cb.hostname or "", cb.port)
            c.request("GET", f"{cb.path}?error=access_denied")
            c.getresponse().read()
            c.close()

        threading.Thread(target=fire, daemon=True).start()

    auth = PkceAuthenticator(
        client_id="cid",
        redirect_port=0,
        on_browser_open=err_browser,
    )
    fake_endpoints = oauth.OAuthEndpoints(
        "https://login.example/authorize", "https://login.example/token", "https://login.example",
    )
    with patch("docuware.oauth.discover_oauth_endpoints", return_value=fake_endpoints):
        with pytest.raises(errors.AccountError, match="PKCE login failed: access_denied"):
            auth._run_pkce_flow(_conn())


def test_pkce_flow_timeout_raises():
    """If the callback never fires, the flow raises after callback_timeout."""
    def silent_browser(auth_url: str) -> None:
        pass  # never trigger the callback

    auth = PkceAuthenticator(
        client_id="cid",
        redirect_port=0,
        callback_timeout=0.5,
        on_browser_open=silent_browser,
    )
    fake_endpoints = oauth.OAuthEndpoints(
        "https://login.example/authorize", "https://login.example/token", "https://login.example",
    )
    with patch("docuware.oauth.discover_oauth_endpoints", return_value=fake_endpoints):
        with pytest.raises(errors.AccountError, match="timed out"):
            auth._run_pkce_flow(_conn())
