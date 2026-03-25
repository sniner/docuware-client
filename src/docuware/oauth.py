"""OAuth2 utilities for DocuWare PKCE flows.

Provides building blocks that any application can use to implement
an Authorization Code + PKCE login flow against DocuWare:

    endpoints = discover_oauth_endpoints(url)
    tokens = exchange_pkce_code(code, verifier, redirect_uri,
                                endpoints.token_endpoint, client_id)

The interactive parts (opening a browser, running a local callback server,
prompting the user) are intentionally left to the application layer.
See the examples/oauth2_login.py script for a complete reference implementation.
"""

from __future__ import annotations

from typing import Any, Dict, NamedTuple

import httpx

from docuware import errors

__all__ = [
    "OAuthEndpoints",
    "discover_oauth_endpoints",
    "exchange_pkce_code",
    "normalize_docuware_url",
]


class OAuthEndpoints(NamedTuple):
    """Result of OAuth2 endpoint discovery."""

    authorization_endpoint: str
    token_endpoint: str
    identity_service_url: str


def normalize_docuware_url(value: str) -> str:
    """Expand a bare hostname or short tenant name to a full DocuWare Platform URL.

    If the input contains no dots it is assumed to be a DocuWare Cloud tenant
    name and ``.docuware.cloud`` is appended automatically.

    Examples::

        normalize_docuware_url("acme")
        # → "https://acme.docuware.cloud/DocuWare/Platform"

        normalize_docuware_url("dw.example.com")
        # → "https://dw.example.com/DocuWare/Platform"

        normalize_docuware_url("https://dw.example.com/DocuWare/Platform")
        # → "https://dw.example.com/DocuWare/Platform"  (unchanged)
    """
    v = value.strip()
    if not v:
        return v
    if "/DocuWare/" in v:
        return v
    if not v.startswith("http://") and not v.startswith("https://"):
        if "." not in v:
            v = v + ".docuware.cloud"
        v = "https://" + v
    return v.rstrip("/") + "/DocuWare/Platform"


def discover_oauth_endpoints(
    docuware_url: str,
    *,
    verify: bool = True,
) -> OAuthEndpoints:
    """Discover the OAuth2 authorization and token endpoints for a DocuWare instance.

    Works for both DocuWare Cloud (where the Identity Service lives on a
    separate host like ``login-emea.docuware.cloud``) and Self-Hosted
    instances (where identity is on the same host).

    Performs two HTTP requests:
      1. ``GET <docuware_url>/Home/IdentityServiceInfo`` — DocuWare-specific endpoint
         that returns the Identity Service base URL (requested as JSON).
      2. ``GET <identity_url>/.well-known/openid-configuration`` — standard OpenID
         Connect discovery document.

    Args:
        docuware_url: DocuWare server URL.  Accepts any of:

                      - Full Platform URL: ``https://acme.docuware.cloud/DocuWare/Platform``
                      - Base server URL: ``https://acme.docuware.cloud``
                      - Bare hostname: ``acme.docuware.cloud``
                      - Short tenant name: ``acme`` (expands to ``acme.docuware.cloud``)
        verify:       Whether to verify TLS certificates (default ``True``).
                      Set to ``False`` for on-prem instances with self-signed certs.

    Returns:
        An :class:`OAuthEndpoints` named tuple with ``authorization_endpoint``,
        ``token_endpoint``, and ``identity_service_url``.

    Raises:
        RuntimeError: If either request fails or the expected fields are absent.
    """
    platform_url = normalize_docuware_url(docuware_url)
    info_url = platform_url.rstrip("/") + "/Home/IdentityServiceInfo"
    try:
        resp = httpx.get(
            info_url,
            headers={"Accept": "application/json"},
            timeout=10,
            follow_redirects=True,
            verify=verify,
        )
        resp.raise_for_status()
    except Exception as exc:
        raise RuntimeError(f"DocuWare not reachable ({info_url}): {exc}") from exc

    try:
        info = resp.json()
        identity_url = (info.get("IdentityServiceUrl") or "").strip()
    except Exception as exc:
        raise RuntimeError(f"Could not parse IdentityServiceInfo: {exc}") from exc

    if not identity_url:
        raise RuntimeError("IdentityServiceUrl missing in DocuWare response.")

    discovery_url = identity_url.rstrip("/") + "/.well-known/openid-configuration"
    try:
        resp2 = httpx.get(discovery_url, timeout=10, verify=verify)
        resp2.raise_for_status()
        oidc = resp2.json()
    except Exception as exc:
        raise RuntimeError(f"OpenID Connect discovery failed ({discovery_url}): {exc}") from exc

    auth_ep = oidc.get("authorization_endpoint", "")
    token_ep = oidc.get("token_endpoint", "")
    if not auth_ep or not token_ep:
        raise RuntimeError("Endpoints missing in OpenID Connect discovery response.")

    return OAuthEndpoints(auth_ep, token_ep, identity_url)


def exchange_pkce_code(
    code: str,
    code_verifier: str,
    redirect_uri: str,
    token_endpoint: str,
    client_id: str,
    *,
    client_secret: str = "",
    verify: bool = True,
) -> Dict[str, Any]:
    """Exchange an OAuth2 authorization code for tokens.

    Sends a ``grant_type=authorization_code`` POST to the token endpoint and
    returns the raw token response as a dict (contains ``access_token``,
    ``refresh_token``, ``expires_in``, etc.).

    Supports both public clients (native/SPA apps using PKCE) and confidential
    clients (web apps with a ``client_secret``).

    Args:
        code:           Authorization code received in the callback.
        code_verifier:  PKCE code verifier string (plain text, not hashed).
        redirect_uri:   Redirect URI used in the authorization request — must
                        match the value registered in the DocuWare App Registration
                        exactly, including the port number.
        token_endpoint: Token endpoint URL (from :func:`discover_oauth_endpoints`).
        client_id:      OAuth2 client ID from the DocuWare App Registration.
        client_secret:  OAuth2 client secret — required for confidential clients
                        (web apps), empty for public/native clients (default).
        verify:         Whether to verify TLS certificates (default ``True``).

    Returns:
        Token response dict with at least ``access_token`` and ``refresh_token``.

    Raises:
        errors.AccountError: If the token endpoint returns HTTP 400 (invalid/expired code).
        httpx.HTTPStatusError: If the token endpoint returns any other error response.
    """
    data = {
        "grant_type": "authorization_code",
        "code": code,
        "redirect_uri": redirect_uri,
        "client_id": client_id,
        "code_verifier": code_verifier,
    }
    if client_secret:
        data["client_secret"] = client_secret
    resp = httpx.post(
        token_endpoint,
        data=data,
        timeout=15,
        verify=verify,
    )
    try:
        resp.raise_for_status()
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code == 400:
            raise errors.AccountError(
                "Authorization code exchange failed — code may be invalid or expired"
            ) from exc
        raise
    return resp.json()
