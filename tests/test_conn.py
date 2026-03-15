from __future__ import annotations

import pytest
import httpx

from docuware import errors
from docuware.conn import BearerAuth, Connection, OAuth2Authenticator

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
            return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
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


# --- Connection._request: 401 retry ---

def test_request_retries_on_401():
    protected_calls = {"n": 0}

    def handler(req):
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(200, json={"IdentityServiceUrl": f"{BASE}/DocuWare/Identity"})
        if "openid-configuration" in path:
            return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
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
        return httpx.Response(200, content=b"data", headers={"Content-Type": "application/octet-stream"})
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
