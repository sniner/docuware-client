"""Shared test helpers for docuware-client tests."""
from __future__ import annotations

import httpx
import pytest

from docuware import DocuwareClient

BASE_URL = "https://example.com"

_AUTH_ROUTES: dict = {
    "/DocuWare/Platform/Home/IdentityServiceInfo": {
        "IdentityServiceUrl": f"{BASE_URL}/DocuWare/Identity"
    },
    "/DocuWare/Identity/.well-known/openid-configuration": {
        "token_endpoint": "/DocuWare/Identity/connect/token"
    },
    "/DocuWare/Identity/connect/token": {"access_token": "test_token"},
    "/DocuWare/Platform": {"Version": "7.10", "Links": [], "Resources": []},
}


def make_handler(*extras):
    """Build an httpx.MockTransport handler with standard auth routes.

    extras: dicts mapping path -> json_response (or httpx.Response),
            or callables(request) -> Response | None.
    """
    def handler(request: httpx.Request):
        path = request.url.path
        if path in _AUTH_ROUTES:
            return httpx.Response(200, json=_AUTH_ROUTES[path])
        for extra in extras:
            if callable(extra):
                resp = extra(request)
                if resp is not None:
                    return resp
            elif isinstance(extra, dict) and path in extra:
                data = extra[path]
                if isinstance(data, httpx.Response):
                    return data
                return httpx.Response(200, json=data)
        return httpx.Response(404)
    return handler


def make_client(*extras):
    """Create a logged-in DocuwareClient backed by a mock transport."""
    client = DocuwareClient(BASE_URL)
    client.conn.session = httpx.Client(transport=httpx.MockTransport(make_handler(*extras)))
    client.login("user", "pass")
    return client


@pytest.fixture
def logged_in_client():
    return make_client()
