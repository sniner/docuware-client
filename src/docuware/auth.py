from __future__ import annotations

import logging
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, Callable, Dict, Optional

import httpx

from docuware import cijson, errors, types
from docuware.const import ACCEPT_JSON, BASE_HEADERS

log = logging.getLogger(__name__)

__all__ = ["BearerAuth", "Authenticator", "OAuth2Authenticator", "TokenAuthenticator"]


class BearerAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class Authenticator(ABC, types.AuthenticatorP):
    @abstractmethod
    def authenticate(self, conn: types.ConnectionP) -> httpx.Client: ...

    @abstractmethod
    def login(self, conn: types.ConnectionP) -> None: ...

    @abstractmethod
    def logoff(self, conn: types.ConnectionP) -> None: ...

    def _get(self, conn: types.ConnectionP, path: str) -> Dict:
        url = conn.make_url(path)
        resp = conn.session.get(url, headers={**BASE_HEADERS, **ACCEPT_JSON})
        if resp.status_code == 200:
            return cijson.loads(resp.text)
        raise errors.ResourceError(
            "Failed to get resource", url=url, status_code=resp.status_code
        )

    def _post(
        self,
        conn: types.ConnectionP,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
    ) -> Dict:
        url = conn.make_url(path)
        headers = {**BASE_HEADERS, **(headers or {}), **ACCEPT_JSON}
        resp = conn.session.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            return cijson.loads(resp.text)
        raise errors.ResourceError(
            "Failed to post to resource", url=url, status_code=resp.status_code
        )


class OAuth2Authenticator(Authenticator):
    def __init__(
        self,
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
    ):
        self.password = password
        self.username = username
        self.organization = organization
        self.token: Optional[str] = None

    def _apply_access_token(self, conn: types.ConnectionP, token: Optional[str]) -> None:
        conn.session.auth = BearerAuth(token) if token else None  # type: ignore[assignment]

    def _get_access_token(self, conn: types.ConnectionP) -> str:
        log.debug("Requesting access token")
        # According to https://support.docuware.com/en-us/knowledgebase/article/KBA-37505:
        # Step 1: Get responsible Identity Service
        res = self._get(conn, "/DocuWare/Platform/Home/IdentityServiceInfo")

        # Step 2: Get Identity Service Configuration
        path = (
            f"{res.get('IdentityServiceUrl', '').rstrip('/')}/.well-known/openid-configuration"
        )
        res = self._get(conn, path)

        # Step 3: Obtain an Access Token
        path = res.get("token_endpoint") or "/DocuWare/Identity/connect/token"
        data = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": "docuware.platform.net.client",
            "scope": "docuware.platform",
        }
        try:
            result = self._post(conn, path, data=data)
        except errors.ResourceError as exc:
            if exc.status_code == 400:
                raise errors.AccountError("Login failed: invalid username or password") from exc
            raise
        token = result.get("access_token")
        if not token:
            raise errors.AccountError("No access token received")
        return token

    def authenticate(self, conn: types.ConnectionP) -> httpx.Client:
        self._apply_access_token(conn, None)  # clear stale token before re-authenticating
        self.token = self._get_access_token(conn)
        self._apply_access_token(conn, self.token)
        return conn.session

    def login(self, conn: types.ConnectionP) -> None:
        conn.session = self.authenticate(conn)

    def logoff(self, conn: types.ConnectionP) -> None:
        if self.token:
            # DocuWare Identity Server does not expose a standard revocation endpoint,
            # so we can only discard the token locally.
            self.token = None
            self._apply_access_token(conn, None)


class TokenAuthenticator(Authenticator):
    """Authenticator for an existing OAuth2 access+refresh token pair (e.g. from PKCE flow).

    login()        — sets the Bearer header; no network call needed.
    authenticate() — called automatically on 401/403; does a refresh_token grant.

    Args:
        access_token:     Initial OAuth2 access token.
        refresh_token:    OAuth2 refresh token used to obtain new access tokens.
        token_endpoint:   Full URL of the OAuth2 token endpoint.
        client_id:        OAuth2 client ID (public client / native app).
        client_secret:    OAuth2 client secret — required for confidential clients
                          (web apps), empty for public/native clients.
        verify:           Whether to verify TLS certificates on the refresh request
                          (default True).  Set to False for on-prem self-signed certs.
        on_token_refresh: Optional callback invoked after a successful refresh with
                          the raw token response dict.  Use it to persist the new tokens.
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str,
        token_endpoint: str,
        client_id: str,
        client_secret: str = "",
        verify: bool = True,
        on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_endpoint = token_endpoint
        self.client_id = client_id
        self.client_secret = client_secret
        self.verify = verify
        self.on_token_refresh = on_token_refresh

    def _apply(self, conn: types.ConnectionP) -> None:
        conn.session.auth = BearerAuth(self.access_token)

    def login(self, conn: types.ConnectionP) -> None:
        self._apply(conn)

    def authenticate(self, conn: types.ConnectionP) -> httpx.Client:
        """Refresh the access token and re-apply it to the session."""
        try:
            data = {
                "grant_type": "refresh_token",
                "refresh_token": self.refresh_token,
                "client_id": self.client_id,
            }
            if self.client_secret:
                data["client_secret"] = self.client_secret
            resp = httpx.post(self.token_endpoint, data=data, timeout=15, verify=self.verify)
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 400:
                raise errors.AccountError(
                    "Refresh token expired or revoked — re-authentication required"
                ) from exc
            raise
        tokens = resp.json()
        token = tokens.get("access_token")
        if not token:
            raise errors.AccountError("No access token in refresh response")
        self.access_token = token
        if "refresh_token" in tokens:
            self.refresh_token = tokens["refresh_token"]
        self._apply(conn)
        if self.on_token_refresh:
            self.on_token_refresh(tokens)
        return conn.session

    def logoff(self, conn: types.ConnectionP) -> None:
        conn.session.auth = None  # type: ignore[assignment]
