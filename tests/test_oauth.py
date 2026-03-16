"""Tests for docuware.oauth — discover_oauth_endpoints() and exchange_pkce_code()."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import httpx
import pytest

from docuware import errors
from docuware.oauth import discover_oauth_endpoints, exchange_pkce_code

DW_URL = "https://acme.docuware.cloud/DocuWare/Platform"
IDENTITY_URL = "https://acme.docuware.cloud/DocuWare/Identity"
AUTH_EP = f"{IDENTITY_URL}/connect/authorize"
TOKEN_EP = f"{IDENTITY_URL}/connect/token"


def _mock_get(responses):
    """Return a side_effect for httpx.get that returns responses in order."""
    call_count = {"n": 0}

    def side_effect(url, **kwargs):
        idx = call_count["n"]
        call_count["n"] += 1
        if idx < len(responses):
            return responses[idx]
        return httpx.Response(404)

    return side_effect


# --- discover_oauth_endpoints ---


def test_discover_returns_endpoints():
    info_resp = MagicMock(spec=httpx.Response)
    info_resp.status_code = 200
    info_resp.json.return_value = {"IdentityServiceUrl": IDENTITY_URL}
    info_resp.raise_for_status = MagicMock()

    oidc_resp = MagicMock(spec=httpx.Response)
    oidc_resp.status_code = 200
    oidc_resp.json.return_value = {
        "authorization_endpoint": AUTH_EP,
        "token_endpoint": TOKEN_EP,
    }
    oidc_resp.raise_for_status = MagicMock()

    with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
        auth_ep, token_ep = discover_oauth_endpoints(DW_URL)

    assert auth_ep == AUTH_EP
    assert token_ep == TOKEN_EP


def test_discover_passes_accept_json_header():
    """IdentityServiceInfo should be requested as JSON, not XML."""
    captured_kwargs = {}

    info_resp = MagicMock(spec=httpx.Response)
    info_resp.status_code = 200
    info_resp.json.return_value = {"IdentityServiceUrl": IDENTITY_URL}
    info_resp.raise_for_status = MagicMock()

    oidc_resp = MagicMock(spec=httpx.Response)
    oidc_resp.status_code = 200
    oidc_resp.json.return_value = {
        "authorization_endpoint": AUTH_EP,
        "token_endpoint": TOKEN_EP,
    }
    oidc_resp.raise_for_status = MagicMock()

    call_count = {"n": 0}

    def mock_get(url, **kwargs):
        if call_count["n"] == 0:
            captured_kwargs.update(kwargs)
            call_count["n"] += 1
            return info_resp
        return oidc_resp

    with patch("docuware.oauth.httpx.get", side_effect=mock_get):
        discover_oauth_endpoints(DW_URL)

    assert captured_kwargs.get("headers", {}).get("Accept") == "application/json"


def test_discover_passes_verify_false():
    """verify=False should be forwarded to httpx.get calls."""
    verify_values = []

    info_resp = MagicMock(spec=httpx.Response)
    info_resp.status_code = 200
    info_resp.json.return_value = {"IdentityServiceUrl": IDENTITY_URL}
    info_resp.raise_for_status = MagicMock()

    oidc_resp = MagicMock(spec=httpx.Response)
    oidc_resp.status_code = 200
    oidc_resp.json.return_value = {
        "authorization_endpoint": AUTH_EP,
        "token_endpoint": TOKEN_EP,
    }
    oidc_resp.raise_for_status = MagicMock()

    def mock_get(url, **kwargs):
        verify_values.append(kwargs.get("verify"))
        if len(verify_values) == 1:
            return info_resp
        return oidc_resp

    with patch("docuware.oauth.httpx.get", side_effect=mock_get):
        discover_oauth_endpoints(DW_URL, verify=False)

    assert verify_values == [False, False]


def test_discover_raises_on_unreachable():
    with patch("docuware.oauth.httpx.get", side_effect=httpx.ConnectError("refused")):
        with pytest.raises(RuntimeError, match="not reachable"):
            discover_oauth_endpoints(DW_URL)


def test_discover_raises_on_missing_identity_url():
    info_resp = MagicMock(spec=httpx.Response)
    info_resp.status_code = 200
    info_resp.json.return_value = {}  # no IdentityServiceUrl
    info_resp.raise_for_status = MagicMock()

    with patch("docuware.oauth.httpx.get", return_value=info_resp):
        with pytest.raises(RuntimeError, match="IdentityServiceUrl missing"):
            discover_oauth_endpoints(DW_URL)


def test_discover_raises_on_missing_endpoints():
    info_resp = MagicMock(spec=httpx.Response)
    info_resp.status_code = 200
    info_resp.json.return_value = {"IdentityServiceUrl": IDENTITY_URL}
    info_resp.raise_for_status = MagicMock()

    oidc_resp = MagicMock(spec=httpx.Response)
    oidc_resp.status_code = 200
    oidc_resp.json.return_value = {}  # no endpoints
    oidc_resp.raise_for_status = MagicMock()

    with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
        with pytest.raises(RuntimeError, match="Endpoints missing"):
            discover_oauth_endpoints(DW_URL)


# --- exchange_pkce_code ---


def test_exchange_posts_correct_data():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {
        "access_token": "at_123",
        "refresh_token": "rt_456",
        "expires_in": 3600,
    }
    mock_resp.raise_for_status = MagicMock()

    with patch("docuware.oauth.httpx.post", return_value=mock_resp) as mock_post:
        tokens = exchange_pkce_code(
            code="auth_code",
            code_verifier="verifier_xyz",
            redirect_uri="http://localhost:18923/callback",
            token_endpoint=TOKEN_EP,
            client_id="test-client",
        )

    assert tokens["access_token"] == "at_123"
    assert tokens["refresh_token"] == "rt_456"
    mock_post.assert_called_once_with(
        TOKEN_EP,
        data={
            "grant_type": "authorization_code",
            "code": "auth_code",
            "redirect_uri": "http://localhost:18923/callback",
            "client_id": "test-client",
            "code_verifier": "verifier_xyz",
        },
        timeout=15,
        verify=True,
    )


def test_exchange_passes_verify_false():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 200
    mock_resp.json.return_value = {"access_token": "at", "expires_in": 3600}
    mock_resp.raise_for_status = MagicMock()

    with patch("docuware.oauth.httpx.post", return_value=mock_resp) as mock_post:
        exchange_pkce_code(
            code="c",
            code_verifier="v",
            redirect_uri="http://localhost/cb",
            token_endpoint=TOKEN_EP,
            client_id="cid",
            verify=False,
        )

    assert mock_post.call_args.kwargs.get("verify") is False


def test_exchange_raises_account_error_on_400():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 400
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad request", request=MagicMock(), response=mock_resp
    )

    with patch("docuware.oauth.httpx.post", return_value=mock_resp):
        with pytest.raises(errors.AccountError):
            exchange_pkce_code(
                code="bad",
                code_verifier="v",
                redirect_uri="http://localhost/cb",
                token_endpoint=TOKEN_EP,
                client_id="cid",
            )


def test_exchange_raises_http_error_on_500():
    mock_resp = MagicMock(spec=httpx.Response)
    mock_resp.status_code = 500
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_resp
    )

    with patch("docuware.oauth.httpx.post", return_value=mock_resp):
        with pytest.raises(httpx.HTTPStatusError):
            exchange_pkce_code(
                code="bad",
                code_verifier="v",
                redirect_uri="http://localhost/cb",
                token_endpoint=TOKEN_EP,
                client_id="cid",
            )
