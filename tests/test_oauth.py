"""Tests for docuware.oauth — discovery, URL normalization, and code exchange."""

from __future__ import annotations

from unittest.mock import patch, MagicMock

import httpx
import pytest

from docuware import errors
from docuware.oauth import (
    OAuthEndpoints,
    discover_oauth_endpoints,
    exchange_pkce_code,
    normalize_docuware_url,
)

DW_URL = "https://acme.docuware.cloud/DocuWare/Platform"
IDENTITY_URL = "https://login-emea.docuware.cloud/e0193dd7-ab5f-8abc4c612e8b"
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


def _make_info_resp(identity_url=IDENTITY_URL):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {"IdentityServiceUrl": identity_url}
    resp.raise_for_status = MagicMock()
    return resp


def _make_oidc_resp(auth_ep=AUTH_EP, token_ep=TOKEN_EP):
    resp = MagicMock(spec=httpx.Response)
    resp.status_code = 200
    resp.json.return_value = {
        "authorization_endpoint": auth_ep,
        "token_endpoint": token_ep,
    }
    resp.raise_for_status = MagicMock()
    return resp


# --- normalize_docuware_url ---


class TestNormalizeDocuwareUrl:
    def test_empty_string(self):
        assert normalize_docuware_url("") == ""
        assert normalize_docuware_url("  ") == ""

    def test_bare_tenant_name(self):
        assert normalize_docuware_url("acme") == (
            "https://acme.docuware.cloud/DocuWare/Platform"
        )

    def test_hostname_with_dots(self):
        assert normalize_docuware_url("dw.example.com") == (
            "https://dw.example.com/DocuWare/Platform"
        )

    def test_cloud_hostname(self):
        assert normalize_docuware_url("acme.docuware.cloud") == (
            "https://acme.docuware.cloud/DocuWare/Platform"
        )

    def test_full_https_url(self):
        assert normalize_docuware_url("https://acme.docuware.cloud") == (
            "https://acme.docuware.cloud/DocuWare/Platform"
        )

    def test_full_platform_url_unchanged(self):
        url = "https://acme.docuware.cloud/DocuWare/Platform"
        assert normalize_docuware_url(url) == url

    def test_http_url(self):
        assert normalize_docuware_url("http://dw.local") == (
            "http://dw.local/DocuWare/Platform"
        )

    def test_trailing_slash_stripped(self):
        assert normalize_docuware_url("https://acme.docuware.cloud/") == (
            "https://acme.docuware.cloud/DocuWare/Platform"
        )

    def test_whitespace_stripped(self):
        assert normalize_docuware_url("  acme  ") == (
            "https://acme.docuware.cloud/DocuWare/Platform"
        )

    def test_preserves_existing_docuware_path(self):
        url = "https://dw.example.com/DocuWare/Platform/Home"
        assert normalize_docuware_url(url) == url


# --- discover_oauth_endpoints ---


class TestDiscoverOAuthEndpoints:
    def test_returns_oauth_endpoints_named_tuple(self):
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

        with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
            result = discover_oauth_endpoints(DW_URL)

        assert isinstance(result, OAuthEndpoints)
        assert result.authorization_endpoint == AUTH_EP
        assert result.token_endpoint == TOKEN_EP
        assert result.identity_service_url == IDENTITY_URL

    def test_returns_endpoints_tuple_unpacking(self):
        """Verify that the 3-element NamedTuple can be unpacked."""
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

        with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
            auth_ep, token_ep, identity_url = discover_oauth_endpoints(DW_URL)

        assert auth_ep == AUTH_EP
        assert token_ep == TOKEN_EP
        assert identity_url == IDENTITY_URL

    def test_accepts_bare_hostname(self):
        """Short tenant name should be expanded before discovery."""
        captured_urls = []
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

        def mock_get(url, **kwargs):
            captured_urls.append(url)
            if len(captured_urls) == 1:
                return info_resp
            return oidc_resp

        with patch("docuware.oauth.httpx.get", side_effect=mock_get):
            discover_oauth_endpoints("acme")

        assert captured_urls[0] == (
            "https://acme.docuware.cloud/DocuWare/Platform/Home/IdentityServiceInfo"
        )

    def test_accepts_base_server_url(self):
        """Server URL without /DocuWare/Platform should be normalized."""
        captured_urls = []
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

        def mock_get(url, **kwargs):
            captured_urls.append(url)
            if len(captured_urls) == 1:
                return info_resp
            return oidc_resp

        with patch("docuware.oauth.httpx.get", side_effect=mock_get):
            discover_oauth_endpoints("https://acme.docuware.cloud")

        assert captured_urls[0] == (
            "https://acme.docuware.cloud/DocuWare/Platform/Home/IdentityServiceInfo"
        )

    def test_identity_service_url_on_separate_host(self):
        """Cloud instances have identity on a different host than the platform API."""
        cloud_identity = "https://login-emea.docuware.cloud/some-org-uuid"
        info_resp = _make_info_resp(identity_url=cloud_identity)
        oidc_resp = _make_oidc_resp(
            auth_ep=f"{cloud_identity}/connect/authorize",
            token_ep=f"{cloud_identity}/connect/token",
        )

        with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
            result = discover_oauth_endpoints(DW_URL)

        assert result.identity_service_url == cloud_identity
        assert "login-emea" in result.authorization_endpoint
        assert "login-emea" in result.token_endpoint

    def test_self_hosted_identity_same_host(self):
        """Self-hosted instances return their own host as identity service."""
        self_hosted_identity = "https://dw.example.com/DocuWare/Identity"
        info_resp = _make_info_resp(identity_url=self_hosted_identity)
        oidc_resp = _make_oidc_resp(
            auth_ep=f"{self_hosted_identity}/connect/authorize",
            token_ep=f"{self_hosted_identity}/connect/token",
        )

        with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
            result = discover_oauth_endpoints("https://dw.example.com/DocuWare/Platform")

        assert result.identity_service_url == self_hosted_identity

    def test_passes_accept_json_header(self):
        """IdentityServiceInfo should be requested as JSON, not XML."""
        captured_kwargs = {}
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

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

    def test_passes_verify_false(self):
        """verify=False should be forwarded to httpx.get calls."""
        verify_values = []
        info_resp = _make_info_resp()
        oidc_resp = _make_oidc_resp()

        def mock_get(url, **kwargs):
            verify_values.append(kwargs.get("verify"))
            if len(verify_values) == 1:
                return info_resp
            return oidc_resp

        with patch("docuware.oauth.httpx.get", side_effect=mock_get):
            discover_oauth_endpoints(DW_URL, verify=False)

        assert verify_values == [False, False]

    def test_raises_on_unreachable(self):
        with patch("docuware.oauth.httpx.get", side_effect=httpx.ConnectError("refused")):
            with pytest.raises(RuntimeError, match="not reachable"):
                discover_oauth_endpoints(DW_URL)

    def test_raises_on_missing_identity_url(self):
        info_resp = MagicMock(spec=httpx.Response)
        info_resp.status_code = 200
        info_resp.json.return_value = {}  # no IdentityServiceUrl
        info_resp.raise_for_status = MagicMock()

        with patch("docuware.oauth.httpx.get", return_value=info_resp):
            with pytest.raises(RuntimeError, match="IdentityServiceUrl missing"):
                discover_oauth_endpoints(DW_URL)

    def test_raises_on_missing_endpoints(self):
        info_resp = _make_info_resp()
        oidc_resp = MagicMock(spec=httpx.Response)
        oidc_resp.status_code = 200
        oidc_resp.json.return_value = {}  # no endpoints
        oidc_resp.raise_for_status = MagicMock()

        with patch("docuware.oauth.httpx.get", side_effect=_mock_get([info_resp, oidc_resp])):
            with pytest.raises(RuntimeError, match="Endpoints missing"):
                discover_oauth_endpoints(DW_URL)


# --- exchange_pkce_code ---


class TestExchangePkceCode:
    def test_posts_correct_data(self):
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

    def test_includes_client_secret_when_provided(self):
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
                redirect_uri="http://localhost:18080/callback",
                token_endpoint=TOKEN_EP,
                client_id="test-client",
                client_secret="test-secret",
            )

        assert tokens["access_token"] == "at_123"
        posted_data = mock_post.call_args.kwargs.get("data", {})
        assert posted_data["client_secret"] == "test-secret"
        assert posted_data["client_id"] == "test-client"
        assert posted_data["code_verifier"] == "verifier_xyz"

    def test_omits_client_secret_when_empty(self):
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
            )

        posted_data = mock_post.call_args.kwargs.get("data", {})
        assert "client_secret" not in posted_data

    def test_passes_verify_false(self):
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

    def test_raises_account_error_on_400(self):
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

    def test_raises_http_error_on_500(self):
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
