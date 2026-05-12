from __future__ import annotations

import http.server
import logging
import secrets
import socket
import time
import urllib.parse
import warnings
import webbrowser
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, Callable, ClassVar, Dict, Optional

import httpx

from docuware import cijson, errors, types
from docuware.const import ACCEPT_JSON, BASE_HEADERS

log = logging.getLogger(__name__)

__all__ = [
    "BearerAuth",
    "Authenticator",
    "PasswordGrantAuthenticator",
    "ClientCredentialsAuthenticator",
    "PkceAuthenticator",
    "TokenAuthenticator",
    "OAuth2Authenticator",
]


class BearerAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class Authenticator(ABC, types.AuthenticatorP):
    """Base class for all auth strategies.

    Subclasses declare their OAuth2 grant type via :attr:`METHOD`, which doubles
    as the discriminator in persisted credential bundles. :meth:`to_bundle` and
    :meth:`from_bundle` round-trip the authenticator's persistent state through
    a :class:`~docuware.CredentialStore`.
    """

    METHOD: ClassVar[str] = ""

    @abstractmethod
    def authenticate(self, conn: types.ConnectionP) -> httpx.Client: ...

    @abstractmethod
    def login(self, conn: types.ConnectionP) -> None: ...

    @abstractmethod
    def logoff(self, conn: types.ConnectionP) -> None: ...

    def to_bundle(self) -> Dict[str, Any]:
        """Serialize persistent state to a credential bundle.

        Subclasses override to add auth-method-specific fields. The top-level
        ``method`` key is always included.
        """
        return {"method": self.METHOD}

    @classmethod
    def from_bundle(cls, bundle: Dict[str, Any]) -> "Authenticator":
        """Reconstruct an authenticator from a credential bundle.

        Default implementation rejects with NotImplementedError; subclasses
        that support persistence override.
        """
        raise NotImplementedError(
            f"{cls.__name__} does not support reconstruction from a credential bundle"
        )

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


# --- Password Grant (RFC 6749 §4.3) ---------------------------------------


class PasswordGrantAuthenticator(Authenticator):
    """RFC 6749 §4.3 — Resource Owner Password Credentials Grant.

    The classic "log in with username + password" flow. Persistence shape:
    ``{"method": "password", "username": ..., "password": ..., "organization": ...}``.
    """

    METHOD = "password"

    def __init__(
        self,
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
    ):
        self.username = username
        self.password = password
        self.organization = organization
        self.token: Optional[str] = None

    def _apply_access_token(self, conn: types.ConnectionP, token: Optional[str]) -> None:
        conn.session.auth = BearerAuth(token) if token else None  # type: ignore[assignment]

    def _get_access_token(self, conn: types.ConnectionP) -> str:
        log.debug("Requesting access token (password grant)")
        # KBA-37505: IdentityServiceInfo → OIDC discovery → token endpoint
        res = self._get(conn, "/DocuWare/Platform/Home/IdentityServiceInfo")
        path = (
            f"{res.get('IdentityServiceUrl', '').rstrip('/')}/.well-known/openid-configuration"
        )
        res = self._get(conn, path)
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
        self._apply_access_token(conn, None)
        self.token = self._get_access_token(conn)
        self._apply_access_token(conn, self.token)
        return conn.session

    def login(self, conn: types.ConnectionP) -> None:
        conn.session = self.authenticate(conn)

    def logoff(self, conn: types.ConnectionP) -> None:
        if self.token:
            self.token = None
            self._apply_access_token(conn, None)

    def to_bundle(self) -> Dict[str, Any]:
        bundle: Dict[str, Any] = {
            "method": self.METHOD,
            "username": self.username,
            "password": self.password,
        }
        if self.organization:
            bundle["organization"] = self.organization
        return bundle

    @classmethod
    def from_bundle(cls, bundle: Dict[str, Any]) -> "PasswordGrantAuthenticator":
        return cls(
            username=bundle.get("username"),
            password=bundle.get("password"),
            organization=bundle.get("organization"),
        )


class OAuth2Authenticator(PasswordGrantAuthenticator):
    """Deprecated alias for :class:`PasswordGrantAuthenticator`.

    The name "OAuth2Authenticator" was misleading — all four authenticators
    are OAuth2. The Password Grant flow specifically is now called
    ``PasswordGrantAuthenticator``.
    """

    def __init__(self, *args: Any, **kwargs: Any) -> None:
        warnings.warn(
            "OAuth2Authenticator is deprecated, use PasswordGrantAuthenticator",
            DeprecationWarning,
            stacklevel=2,
        )
        super().__init__(*args, **kwargs)


# --- Client Credentials (RFC 6749 §4.4) -----------------------------------


class ClientCredentialsAuthenticator(Authenticator):
    """RFC 6749 §4.4 — Client Credentials Grant.

    Service-to-service authentication: no user, no browser. The application
    authenticates itself via ``client_id`` + ``client_secret``. Suited for
    backend jobs, ETL pipelines, scheduled tasks, MCP servers — anywhere a
    *machine* talks to DocuWare, not a person on behalf of a machine.

    No refresh_token (RFC §4.4.3: "SHOULD NOT be included"). On 401/403 the
    library re-requests a fresh access_token from the stored client_secret;
    that re-acquisition is the substitute for refresh.
    """

    METHOD = "client_credentials"

    def __init__(
        self,
        client_id: str,
        client_secret: str,
        *,
        scope: str = "docuware.platform",
        verify: bool = True,
    ):
        self.client_id = client_id
        self.client_secret = client_secret
        self.scope = scope
        self.verify = verify
        self.access_token: Optional[str] = None

    def _get_access_token(self, conn: types.ConnectionP) -> str:
        log.debug("Requesting access token (client_credentials grant)")
        res = self._get(conn, "/DocuWare/Platform/Home/IdentityServiceInfo")
        path = (
            f"{res.get('IdentityServiceUrl', '').rstrip('/')}/.well-known/openid-configuration"
        )
        res = self._get(conn, path)
        path = res.get("token_endpoint") or "/DocuWare/Identity/connect/token"
        data = {
            "grant_type": "client_credentials",
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }
        try:
            result = self._post(conn, path, data=data)
        except errors.ResourceError as exc:
            if exc.status_code == 400:
                raise errors.AccountError(
                    "Client credentials login failed: invalid client_id or client_secret"
                ) from exc
            raise
        token = result.get("access_token")
        if not token:
            raise errors.AccountError("No access token received")
        return token

    def authenticate(self, conn: types.ConnectionP) -> httpx.Client:
        conn.session.auth = None  # type: ignore[assignment]
        self.access_token = self._get_access_token(conn)
        conn.session.auth = BearerAuth(self.access_token)
        return conn.session

    def login(self, conn: types.ConnectionP) -> None:
        conn.session = self.authenticate(conn)

    def logoff(self, conn: types.ConnectionP) -> None:
        if self.access_token:
            self.access_token = None
            conn.session.auth = None  # type: ignore[assignment]

    def to_bundle(self) -> Dict[str, Any]:
        return {
            "method": self.METHOD,
            "client_id": self.client_id,
            "client_secret": self.client_secret,
            "scope": self.scope,
        }

    @classmethod
    def from_bundle(cls, bundle: Dict[str, Any]) -> "ClientCredentialsAuthenticator":
        return cls(
            client_id=bundle["client_id"],
            client_secret=bundle["client_secret"],
            scope=bundle.get("scope", "docuware.platform"),
        )


# --- Authorization Code + PKCE (RFC 6749 §4.1 + RFC 7636) -----------------


class PkceAuthenticator(Authenticator):
    """RFC 6749 §4.1 + RFC 7636 — Authorization Code Grant with PKCE.

    Self-contained: starts a local callback HTTP server, opens the browser,
    handles state validation, performs the code exchange, refreshes access
    tokens on demand, and rotates persisted bundles via ``on_token_refresh``.

    For public clients (native apps), leave ``client_secret=None``. For
    confidential clients (web apps with a registered secret), set it.

    First call to :meth:`login` runs the PKCE flow if no stored tokens are
    present; subsequent calls reuse the stored tokens. On 401/403 the library
    calls :meth:`authenticate`, which performs the refresh_token grant.
    """

    METHOD = "pkce"

    def __init__(
        self,
        client_id: str,
        client_secret: Optional[str] = None,
        *,
        redirect_port: int = 0,
        redirect_host: str = "127.0.0.1",
        callback_path: str = "/callback",
        callback_timeout: float = 120.0,
        on_browser_open: Optional[Callable[[str], None]] = None,
        verify: bool = True,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        token_endpoint: Optional[str] = None,
        on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None,
    ):
        self.client_id = client_id
        self.client_secret = client_secret or ""
        self.redirect_port = redirect_port
        self.redirect_host = redirect_host
        self.callback_path = callback_path
        self.callback_timeout = callback_timeout
        self.on_browser_open = on_browser_open
        self.verify = verify
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.token_endpoint = token_endpoint
        self.on_token_refresh = on_token_refresh

    def _apply(self, conn: types.ConnectionP) -> None:
        conn.session.auth = BearerAuth(self.access_token or "")

    def login(self, conn: types.ConnectionP) -> None:
        if self.access_token and self.refresh_token:
            self._apply(conn)
            return
        self._run_pkce_flow(conn)
        self._apply(conn)

    def _pick_port(self) -> int:
        if self.redirect_port != 0:
            return self.redirect_port
        with socket.socket() as sock:
            sock.bind((self.redirect_host, 0))
            return sock.getsockname()[1]

    def _run_pkce_flow(self, conn: types.ConnectionP) -> None:
        # late import to avoid circular dependency at module load time
        from docuware import oauth

        endpoints = oauth.discover_oauth_endpoints(conn.base_url, verify=self.verify)
        self.token_endpoint = endpoints.token_endpoint

        port = self._pick_port()
        redirect_uri = f"http://{self.redirect_host}:{port}{self.callback_path}"
        verifier, challenge = oauth.generate_pkce()
        state = secrets.token_urlsafe(32)
        auth_url = oauth.build_authorization_url(
            endpoints.authorization_endpoint, self.client_id, redirect_uri, challenge, state,
        )

        callback_path_local = self.callback_path

        class _Handler(http.server.BaseHTTPRequestHandler):
            code: Optional[str] = None
            state: Optional[str] = None
            error: Optional[str] = None

            def do_GET(self) -> None:
                parsed = urllib.parse.urlparse(self.path)
                if parsed.path != callback_path_local:
                    self.send_response(404)
                    self.end_headers()
                    return
                params = urllib.parse.parse_qs(parsed.query)
                cls = type(self)
                cls.code = params.get("code", [None])[0]
                cls.state = params.get("state", [None])[0]
                cls.error = params.get("error", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(b"<h1>Login complete. You may close this window.</h1>")

            def log_message(self, format: str, *args: object) -> None:  # noqa: A002
                pass

        server = http.server.HTTPServer((self.redirect_host, port), _Handler)
        try:
            opener = self.on_browser_open or webbrowser.open
            opener(auth_url)

            deadline = time.time() + self.callback_timeout
            while _Handler.code is None and _Handler.error is None:
                remaining = deadline - time.time()
                if remaining <= 0:
                    raise errors.AccountError(
                        f"PKCE login timed out after {self.callback_timeout}s "
                        "— no callback received"
                    )
                server.timeout = remaining
                server.handle_request()
        finally:
            server.server_close()

        if _Handler.error:
            raise errors.AccountError(f"PKCE login failed: {_Handler.error}")
        if _Handler.state != state:
            raise errors.AccountError("PKCE state mismatch — possible CSRF, aborted")
        if not _Handler.code:
            raise errors.AccountError("PKCE callback returned no authorization code")

        tokens = oauth.exchange_pkce_code(
            code=_Handler.code,
            code_verifier=verifier,
            redirect_uri=redirect_uri,
            token_endpoint=self.token_endpoint,
            client_id=self.client_id,
            client_secret=self.client_secret,
            verify=self.verify,
        )
        self.access_token = tokens.get("access_token")
        self.refresh_token = tokens.get("refresh_token")
        if not self.access_token:
            raise errors.AccountError("No access token in PKCE exchange response")
        if self.on_token_refresh:
            self.on_token_refresh(self.to_bundle())

    def authenticate(self, conn: types.ConnectionP) -> httpx.Client:
        """Refresh the access token via the refresh_token grant."""
        if not self.refresh_token or not self.token_endpoint:
            raise errors.AccountError(
                "PkceAuthenticator cannot refresh: no refresh_token or token_endpoint stored"
            )
        data: Dict[str, Any] = {
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
            "client_id": self.client_id,
        }
        if self.client_secret:
            data["client_secret"] = self.client_secret
        resp = httpx.post(self.token_endpoint, data=data, timeout=15, verify=self.verify)
        try:
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
            self.on_token_refresh(self.to_bundle())
        return conn.session

    def logoff(self, conn: types.ConnectionP) -> None:
        # DocuWare's IdentityServer has no standard revocation endpoint;
        # we discard tokens locally.
        self.access_token = None
        self.refresh_token = None
        conn.session.auth = None  # type: ignore[assignment]

    def to_bundle(self) -> Dict[str, Any]:
        bundle: Dict[str, Any] = {
            "method": self.METHOD,
            "client_id": self.client_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_endpoint": self.token_endpoint,
        }
        if self.client_secret:
            bundle["client_secret"] = self.client_secret
        return bundle

    @classmethod
    def from_bundle(cls, bundle: Dict[str, Any]) -> "PkceAuthenticator":
        return cls(
            client_id=bundle["client_id"],
            client_secret=bundle.get("client_secret"),
            access_token=bundle.get("access_token"),
            refresh_token=bundle.get("refresh_token"),
            token_endpoint=bundle.get("token_endpoint"),
        )


# --- Bring-your-own-Token (no flow at all) --------------------------------


class TokenAuthenticator(Authenticator):
    """Bring-your-own OAuth2 tokens — no browser, no discovery.

    For applications that handle OAuth2 entirely outside this library (e.g.
    web servers with their own auth stack, externally injected tokens).
    The client refreshes automatically on 401/403 via the supplied
    refresh_token.

    Args:
        access_token:     Initial OAuth2 access token.
        refresh_token:    OAuth2 refresh token used to obtain new access tokens.
        token_endpoint:   Full URL of the OAuth2 token endpoint.
        client_id:        OAuth2 client ID (public client / native app).
        client_secret:    OAuth2 client secret — required for confidential clients
                          (web apps), empty for public/native clients.
        verify:           Whether to verify TLS certificates on the refresh request.
        on_token_refresh: Optional callback invoked after a successful refresh
                          with the raw token response dict. Use it to persist tokens.
    """

    METHOD = "token"

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
            # Forward the full bundle, not just the raw token response — this way
            # consumers (e.g. CredentialStore.save) get a self-contained shape
            # they can reload into a TokenAuthenticator on next process start.
            self.on_token_refresh(self.to_bundle())
        return conn.session

    def logoff(self, conn: types.ConnectionP) -> None:
        conn.session.auth = None  # type: ignore[assignment]

    def to_bundle(self) -> Dict[str, Any]:
        bundle: Dict[str, Any] = {
            "method": self.METHOD,
            "client_id": self.client_id,
            "access_token": self.access_token,
            "refresh_token": self.refresh_token,
            "token_endpoint": self.token_endpoint,
        }
        if self.client_secret:
            bundle["client_secret"] = self.client_secret
        return bundle

    @classmethod
    def from_bundle(cls, bundle: Dict[str, Any]) -> "TokenAuthenticator":
        return cls(
            access_token=bundle["access_token"],
            refresh_token=bundle["refresh_token"],
            token_endpoint=bundle["token_endpoint"],
            client_id=bundle["client_id"],
            client_secret=bundle.get("client_secret", ""),
        )
