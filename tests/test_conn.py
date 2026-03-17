from __future__ import annotations

from unittest.mock import MagicMock, patch

import pytest
import httpx

from docuware import errors
from docuware.auth import BearerAuth, OAuth2Authenticator, TokenAuthenticator
from docuware.conn import Connection

BASE = "https://dw.example.com"


def _conn(handler):
    c = Connection(BASE)
    c.session = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def _auth_handler(token_status=200, token_body=None):
    """Handler that completes the standard OAuth2 login sequence."""

    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(200, json={"IdentityServiceUrl": f"{BASE}/DocuWare/Identity"})
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            body = token_body if token_body is not None else {"access_token": "tok"}
            return httpx.Response(token_status, json=body)
        return httpx.Response(404)

    return handler


# --- _server_message ---


def test_server_message_returns_none_on_non_json():
    from docuware.conn import _server_message

    resp = httpx.Response(500, content=b"plain error text")
    assert _server_message(resp) is None


def test_server_message_extracts_message():
    from docuware.conn import _server_message

    resp = httpx.Response(500, json={"Message": "Not found"})
    assert _server_message(resp) == "Not found"


def test_server_message_returns_none_when_no_message_key():
    from docuware.conn import _server_message

    resp = httpx.Response(500, json={"Code": 42})
    assert _server_message(resp) is None


# --- BearerAuth ---


def test_bearer_auth_sets_authorization_header():
    auth = BearerAuth("mytoken")
    request = httpx.Request("GET", "https://example.com/")
    flow = auth.auth_flow(request)
    req = next(flow)
    assert req.headers["Authorization"] == "Bearer mytoken"


# --- Authenticator._get / _post error branches ---


def test_authenticator_get_raises_resource_error_on_non_200():
    conn = _conn(lambda req: httpx.Response(500, json={"Message": "server error"}))
    auth = OAuth2Authenticator("u", "p")
    with pytest.raises(errors.ResourceError):
        auth._get(conn, "/some/path")


def test_authenticator_post_raises_resource_error_on_non_200():
    conn = _conn(lambda req: httpx.Response(401))
    auth = OAuth2Authenticator("u", "p")
    with pytest.raises(errors.ResourceError):
        auth._post(conn, "/some/path")


# --- _get_access_token error branches ---


def test_get_access_token_400_raises_account_error():
    conn = _conn(_auth_handler(token_status=400, token_body={"error": "invalid_grant"}))
    auth = OAuth2Authenticator("alice", "wrongpass")
    with pytest.raises(errors.AccountError, match="invalid username or password"):
        auth._get_access_token(conn)


def test_get_access_token_no_token_field_raises_account_error():
    conn = _conn(_auth_handler(token_status=200, token_body={"token_type": "Bearer"}))
    auth = OAuth2Authenticator("alice", "pass")
    with pytest.raises(errors.AccountError, match="No access token"):
        auth._get_access_token(conn)


# --- OAuth2Authenticator.login / logoff ---


def test_oauth2_login_sets_session_auth():
    conn = _conn(_auth_handler())
    auth = OAuth2Authenticator("user", "pass")
    auth.login(conn)
    assert auth.token == "tok"
    assert conn.session.auth is not None


def test_oauth2_logoff_clears_token():
    conn = Connection(BASE)
    conn.session = httpx.Client()
    auth = OAuth2Authenticator("user", "pass")
    auth.token = "existing_token"
    auth._apply_access_token(conn, auth.token)
    assert conn.session.auth is not None
    auth.logoff(conn)
    assert auth.token is None
    assert conn.session.auth is None


def test_oauth2_logoff_noop_when_no_token():
    conn = Connection(BASE)
    conn.session = httpx.Client()
    auth = OAuth2Authenticator("user", "pass")
    auth.token = None
    auth.logoff(conn)  # must not raise
    assert auth.token is None


# --- Connection.make_url with query ---


def test_make_url_with_query_appends_params():
    conn = Connection(BASE)
    url = conn.make_url("/some/path", {"key": "val ue", "n": "1"})
    assert "key=val+ue" in url
    assert "n=1" in url


# --- Connection.timeout ---


def test_connection_uses_custom_timeout():
    c = Connection(BASE, timeout=42.0)
    assert c.session.timeout.read == 42.0


def test_connection_uses_default_timeout():
    c = Connection(BASE)
    assert c.session.timeout.read == 30.0


# --- Connection._request: 401 retry ---


def test_request_retries_on_401():
    protected_calls = {"n": 0}

    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(200, json={"IdentityServiceUrl": f"{BASE}/DocuWare/Identity"})
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            return httpx.Response(200, json={"access_token": "new_tok"})
        if path == "/DocuWare/Platform/protected":
            protected_calls["n"] += 1
            if protected_calls["n"] == 1:
                return httpx.Response(401)
            return httpx.Response(200, json={})
        return httpx.Response(404)

    conn = _conn(handler)
    conn.authenticator = OAuth2Authenticator("user", "pass")
    resp = conn.get("/DocuWare/Platform/protected")
    assert resp.status_code == 200
    assert protected_calls["n"] == 2


# --- Connection.get ---


@pytest.mark.parametrize("status", [404, 500, 403])
def test_get_raises_resource_error_on_non_200(status):
    conn = _conn(lambda req: httpx.Response(status, json={"Message": "oops"}))
    with pytest.raises(errors.ResourceError) as exc_info:
        conn.get("/path")
    assert exc_info.value.status_code == status


def test_get_includes_server_message_in_error():
    conn = _conn(lambda req: httpx.Response(404, json={"Message": "Doc not found"}))
    with pytest.raises(errors.ResourceError, match="Doc not found"):
        conn.get("/path")


def test_get_text_returns_text():
    conn = _conn(lambda req: httpx.Response(200, text="hello"))
    assert conn.get_text("/path") == "hello"


# --- Connection.post ---


@pytest.mark.parametrize("status", [400, 500])
def test_post_raises_resource_error_on_non_200(status):
    conn = _conn(lambda req: httpx.Response(status, json={"Message": "POST failed"}))
    with pytest.raises(errors.ResourceError):
        conn.post("/path", json={"x": 1})


def test_post_json_returns_parsed_response():
    conn = _conn(lambda req: httpx.Response(200, json={"Result": "ok"}))
    result = conn.post_json("/path", json={"foo": "bar"})
    assert result.get("Result") == "ok"


def test_post_text_returns_string():
    conn = _conn(lambda req: httpx.Response(200, text="created\n"))
    assert conn.post_text("/path") == "created\n"


# --- Connection.put ---


@pytest.mark.parametrize("status", [404, 500])
def test_put_raises_resource_error_on_non_200(status):
    conn = _conn(lambda req: httpx.Response(status))
    with pytest.raises(errors.ResourceError):
        conn.put("/path", json={"x": 1})


def test_put_json_returns_parsed_response():
    conn = _conn(lambda req: httpx.Response(200, json={"Updated": True}))
    assert conn.put_json("/path", json={"field": "value"}).get("Updated") is True


def test_put_text_returns_string():
    conn = _conn(lambda req: httpx.Response(200, text="ok"))
    assert conn.put_text("/path") == "ok"


# --- Connection.delete ---


@pytest.mark.parametrize("status", [404, 500])
def test_delete_raises_resource_error_on_non_200(status):
    conn = _conn(lambda req: httpx.Response(status))
    with pytest.raises(errors.ResourceError):
        conn.delete("/path")


# --- Connection.get_bytes ---


def test_get_bytes_success():
    def handler(req):
        return httpx.Response(
            200,
            content=b"PDF data",
            headers={
                "Content-Type": "application/pdf",
                "Content-Disposition": 'attachment; filename="doc.pdf"',
            },
        )

    data, mime, filename = _conn(handler).get_bytes("/file")
    assert data == b"PDF data"
    assert mime == "application/pdf"
    assert filename == "doc.pdf"


def test_get_bytes_uses_unknown_bin_when_no_filename():
    def handler(req):
        return httpx.Response(
            200, content=b"data", headers={"Content-Type": "application/octet-stream"}
        )

    _, _, filename = _conn(handler).get_bytes("/file")
    assert filename == "unknown.bin"


def test_get_bytes_raises_on_content_length_mismatch():
    def handler(req):
        return httpx.Response(
            200,
            content=b"short",
            headers={"Content-Type": "application/pdf", "Content-Length": "9999"},
        )

    with pytest.raises(errors.ResourceError, match="content length"):
        _conn(handler).get_bytes("/file")


def test_get_bytes_raises_resource_not_found_on_error():
    conn = _conn(lambda req: httpx.Response(404, json={"Message": "Not found"}))
    with pytest.raises(errors.ResourceNotFoundError):
        conn.get_bytes("/file")


# --- TokenAuthenticator ---


def _token_conn(refresh_handler):
    """Create a Connection with a TokenAuthenticator and mock transport for refresh."""
    c = Connection(BASE)
    auth = TokenAuthenticator(
        access_token="at_initial",
        refresh_token="rt_initial",
        token_endpoint=f"{BASE}/token",
        client_id="test-client",
    )
    c.authenticator = auth

    def handler(req):
        path = req.url.path
        if path == "/token":
            return refresh_handler(req)
        # For protected resources, check bearer token
        auth_header = req.headers.get("Authorization", "")
        if "at_initial" in auth_header or "at_refreshed" in auth_header:
            return httpx.Response(200, json={"ok": True})
        return httpx.Response(401)

    c.session = httpx.Client(transport=httpx.MockTransport(handler))
    auth.login(c)
    return c, auth


def test_token_auth_login_sets_bearer():
    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_123",
        refresh_token="rt_456",
        token_endpoint=f"{BASE}/token",
        client_id="test-client",
    )
    auth.login(c)
    assert c.session.auth is not None
    assert c.session.auth.token == "at_123"


def test_token_auth_logoff_clears_auth():
    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_123",
        refresh_token="rt_456",
        token_endpoint=f"{BASE}/token",
        client_id="test-client",
    )
    auth.login(c)
    assert c.session.auth is not None
    auth.logoff(c)
    assert c.session.auth is None


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_refreshes_token(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "access_token": "at_refreshed",
                "refresh_token": "rt_refreshed",
                "expires_in": 3600,
            }
        ),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c, auth = _token_conn(lambda req: httpx.Response(404))
    auth.authenticate(c)
    assert auth.access_token == "at_refreshed"
    assert auth.refresh_token == "rt_refreshed"
    assert c.session.auth.token == "at_refreshed"
    mock_post.assert_called_once_with(
        f"{BASE}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "rt_initial",
            "client_id": "test-client",
        },
        timeout=15,
        verify=True,
    )


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_keeps_old_refresh_if_not_rotated(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "access_token": "at_refreshed",
                "expires_in": 3600,
            }
        ),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c, auth = _token_conn(lambda req: httpx.Response(404))
    auth.authenticate(c)
    assert auth.access_token == "at_refreshed"
    assert auth.refresh_token == "rt_initial"  # unchanged


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_calls_on_token_refresh_callback(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "access_token": "at_new",
                "refresh_token": "rt_new",
                "expires_in": 3600,
            }
        ),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    callback_data = {}

    def on_refresh(tokens):
        callback_data.update(tokens)

    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_old",
        refresh_token="rt_old",
        token_endpoint=f"{BASE}/token",
        client_id="test-client",
        on_token_refresh=on_refresh,
    )
    auth.login(c)
    auth.authenticate(c)
    assert callback_data["access_token"] == "at_new"
    assert callback_data["refresh_token"] == "rt_new"


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_400_raises_account_error(mock_post):
    mock_resp = MagicMock(status_code=400)
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "bad request", request=MagicMock(), response=mock_resp
    )
    mock_resp.response = mock_resp
    mock_post.return_value = mock_resp

    c, auth = _token_conn(lambda req: httpx.Response(404))
    with pytest.raises(errors.AccountError, match="Refresh token expired"):
        auth.authenticate(c)


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_500_raises_http_error(mock_post):
    mock_resp = MagicMock(status_code=500)
    mock_resp.raise_for_status.side_effect = httpx.HTTPStatusError(
        "server error", request=MagicMock(), response=mock_resp
    )
    mock_resp.response = mock_resp
    mock_post.return_value = mock_resp

    c, auth = _token_conn(lambda req: httpx.Response(404))
    with pytest.raises(httpx.HTTPStatusError):
        auth.authenticate(c)


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_sends_client_secret(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(
            return_value={
                "access_token": "at_new",
                "expires_in": 3600,
            }
        ),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_old",
        refresh_token="rt_old",
        token_endpoint=f"{BASE}/token",
        client_id="web-client",
        client_secret="s3cret",
    )
    auth.login(c)
    auth.authenticate(c)
    mock_post.assert_called_once_with(
        f"{BASE}/token",
        data={
            "grant_type": "refresh_token",
            "refresh_token": "rt_old",
            "client_id": "web-client",
            "client_secret": "s3cret",
        },
        timeout=15,
        verify=True,
    )


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_omits_client_secret_when_empty(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"access_token": "at_new", "expires_in": 3600}),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_old",
        refresh_token="rt_old",
        token_endpoint=f"{BASE}/token",
        client_id="native-client",
    )
    auth.login(c)
    auth.authenticate(c)
    called_data = mock_post.call_args.kwargs.get("data") or mock_post.call_args[1].get("data")
    assert "client_secret" not in called_data


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_missing_access_token_raises_account_error(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"token_type": "Bearer", "expires_in": 3600}),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c, auth = _token_conn(lambda req: httpx.Response(404))
    with pytest.raises(errors.AccountError, match="No access token"):
        auth.authenticate(c)


@patch("docuware.auth.httpx.post")
def test_token_auth_authenticate_passes_verify_false(mock_post):
    mock_post.return_value = MagicMock(
        status_code=200,
        json=MagicMock(return_value={"access_token": "at_new", "expires_in": 3600}),
    )
    mock_post.return_value.raise_for_status = MagicMock()

    c = Connection(BASE)
    c.session = httpx.Client()
    auth = TokenAuthenticator(
        access_token="at_old",
        refresh_token="rt_old",
        token_endpoint=f"{BASE}/token",
        client_id="test-client",
        verify=False,
    )
    auth.login(c)
    auth.authenticate(c)
    assert mock_post.call_args.kwargs.get("verify") is False
    assert mock_post.call_args.kwargs.get("timeout") == 15


def test_token_auth_exported_from_top_level():
    import docuware

    assert docuware.TokenAuthenticator is TokenAuthenticator
