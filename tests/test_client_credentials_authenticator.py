from __future__ import annotations


import httpx
import pytest

from docuware import errors
from docuware.auth import BearerAuth, ClientCredentialsAuthenticator
from docuware.conn import Connection

BASE = "https://dw.example.com"


def _conn(handler):
    c = Connection(BASE)
    c.session = httpx.Client(transport=httpx.MockTransport(handler))
    return c


def _token_handler(token_status: int = 200, token: str = "cc_access"):
    """Discovery + token endpoint for client_credentials grant."""
    captured: dict = {}

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(
                200, json={"IdentityServiceUrl": f"{BASE}/DocuWare/Identity"}
            )
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            captured["body"] = req.content.decode()
            if token_status == 200:
                return httpx.Response(200, json={"access_token": token})
            return httpx.Response(token_status, json={"error": "invalid_client"})
        return httpx.Response(404)

    handler.captured = captured  # type: ignore[attr-defined]
    return handler


def test_login_sets_bearer_and_token():
    handler = _token_handler()
    conn = _conn(handler)
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="sec")
    auth.login(conn)
    assert isinstance(conn.session.auth, BearerAuth)
    assert conn.session.auth.token == "cc_access"
    assert auth.access_token == "cc_access"


def test_login_sends_client_credentials_grant_with_scope():
    handler = _token_handler()
    conn = _conn(handler)
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="sec", scope="myscope")
    auth.login(conn)
    body = handler.captured["body"]  # type: ignore[attr-defined]
    assert "grant_type=client_credentials" in body
    assert "client_id=cid" in body
    assert "client_secret=sec" in body
    assert "scope=myscope" in body


def test_invalid_credentials_raise_account_error():
    handler = _token_handler(token_status=400)
    conn = _conn(handler)
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="wrong")
    with pytest.raises(errors.AccountError, match="invalid client_id or client_secret"):
        auth.login(conn)


def test_authenticate_reacquires_token_no_refresh_path():
    """Client Credentials has no refresh_token — authenticate() must re-request."""
    tokens = iter(["first", "second"])

    def handler(req: httpx.Request) -> httpx.Response:
        path = req.url.path
        if "/IdentityServiceInfo" in path:
            return httpx.Response(
                200, json={"IdentityServiceUrl": f"{BASE}/DocuWare/Identity"}
            )
        if "openid-configuration" in path:
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if "/connect/token" in path:
            return httpx.Response(200, json={"access_token": next(tokens)})
        return httpx.Response(404)

    conn = _conn(handler)
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="sec")
    auth.login(conn)
    assert auth.access_token == "first"
    auth.authenticate(conn)
    assert auth.access_token == "second"


def test_logoff_clears_token():
    handler = _token_handler()
    conn = _conn(handler)
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="sec")
    auth.login(conn)
    auth.logoff(conn)
    assert auth.access_token is None
    assert conn.session.auth is None


def test_to_bundle_shape():
    auth = ClientCredentialsAuthenticator(client_id="cid", client_secret="sec", scope="x")
    bundle = auth.to_bundle()
    assert bundle == {
        "method": "client_credentials",
        "client_id": "cid",
        "client_secret": "sec",
        "scope": "x",
    }


def test_from_bundle_roundtrip():
    bundle = {
        "method": "client_credentials",
        "client_id": "cid",
        "client_secret": "sec",
        "scope": "custom",
    }
    rebuilt = ClientCredentialsAuthenticator.from_bundle(bundle)
    assert rebuilt.client_id == "cid"
    assert rebuilt.client_secret == "sec"
    assert rebuilt.scope == "custom"
    assert rebuilt.to_bundle() == bundle


def test_from_bundle_default_scope():
    bundle = {"method": "client_credentials", "client_id": "cid", "client_secret": "sec"}
    rebuilt = ClientCredentialsAuthenticator.from_bundle(bundle)
    assert rebuilt.scope == "docuware.platform"
