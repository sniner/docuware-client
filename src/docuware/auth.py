from __future__ import annotations

import http.server
import logging
import secrets
import time
import urllib.parse
import warnings
import webbrowser
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, Callable, ClassVar, Dict, Optional, Union

import httpx

from docuware import cijson, errors, persistence, types
from docuware.conn import _server_message
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

    #: Optional callback invoked by token-rotating subclasses (Pkce, Token)
    #: after a successful refresh, with the full bundle (see :meth:`to_bundle`).
    #: Defined here so callers can wire it polymorphically; non-rotating
    #: subclasses simply never invoke it.
    on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None

    @abstractmethod
    def authenticate(self, conn: types.ConnectionP) -> httpx.Client: ...

    def add_store(
        self,
        store: persistence.CredentialStore,
        **options: Any,
    ) -> None:
        """Wire on_token_refresh to persist rotated bundles to ``store``.

        Keyword args in ``options`` are merged into the bundle on every save —
        typically ``url=...`` so the persisted file is self-contained and can
        be reloaded by :func:`docuware.connect` without an explicit URL arg.
        On key collision, ``options`` win over bundle fields.

        No-op for non-rotating authenticators (the callback simply never fires).
        User-supplied callbacks are left untouched — the user wins.
        """
        if self.on_token_refresh is not None:
            return

        def _callback(bundle: Dict[str, Any]) -> None:
            try:
                store.save({**bundle, **options})
            except OSError as exc:
                log.warning("Failed to save rotated credentials: %s", exc)

        self.on_token_refresh = _callback

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
        if resp.is_success:
            return cijson.loads(resp.text)
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"GET {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
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
        if resp.is_success:
            return cijson.loads(resp.text)
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"POST {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )

    def _request_token(
        self,
        conn: types.ConnectionP,
        data: Dict[str, Any],
        invalid_credentials_msg: str,
    ) -> str:
        """Discover the token endpoint and run a token grant against it.

        Shared by the password and client_credentials grants: resolves the
        Identity Service via KBA-37505 (IdentityServiceInfo → OIDC discovery
        → token endpoint), posts the grant, and extracts the access token.
        A 400 response is translated to ``invalid_credentials_msg``.
        """
        log.debug("Requesting access token (%s grant)", data.get("grant_type"))
        res = self._get(conn, "/DocuWare/Platform/Home/IdentityServiceInfo")
        path = (
            f"{res.get('IdentityServiceUrl', '').rstrip('/')}/.well-known/openid-configuration"
        )
        res = self._get(conn, path)
        path = res.get("token_endpoint") or "/DocuWare/Identity/connect/token"
        try:
            result = self._post(conn, path, data=data)
        except errors.ResourceError as exc:
            if exc.status_code == 400:
                raise errors.AccountError(invalid_credentials_msg) from exc
            raise
        token = result.get("access_token")
        if not token:
            raise errors.AccountError("No access token received")
        return token


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
        return self._request_token(
            conn,
            {
                "grant_type": "password",
                "username": self.username,
                "password": self.password,
                "client_id": "docuware.platform.net.client",
                "scope": "docuware.platform",
            },
            "Login failed: invalid username or password",
        )

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

    ``verify`` is accepted for signature symmetry with the other
    authenticators but has no effect here: all requests run through the
    Connection's session, which already carries the TLS settings from
    ``verify_certificate``.
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
        return self._request_token(
            conn,
            {
                "grant_type": "client_credentials",
                "client_id": self.client_id,
                "client_secret": self.client_secret,
                "scope": self.scope,
            },
            "Client credentials login failed: invalid client_id or client_secret",
        )

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


def _run_refresh_grant(
    auth: Union[PkceAuthenticator, TokenAuthenticator],
    conn: types.ConnectionP,
) -> httpx.Client:
    """Run the refresh_token grant shared by Pkce and Token authenticators.

    Rotates ``auth.access_token`` (and ``auth.refresh_token`` if the server
    rotates it), re-applies the bearer auth to the session, and forwards the
    full bundle to ``on_token_refresh`` so consumers (e.g.
    ``CredentialStore.save``) get a self-contained shape they can reload on
    the next process start.
    """
    data: Dict[str, Any] = {
        "grant_type": "refresh_token",
        "refresh_token": auth.refresh_token,
        "client_id": auth.client_id,
    }
    if auth.client_secret:
        data["client_secret"] = auth.client_secret
    resp = httpx.post(auth.token_endpoint or "", data=data, timeout=15, verify=auth.verify)
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
    auth.access_token = token
    if "refresh_token" in tokens:
        auth.refresh_token = tokens["refresh_token"]
    auth._apply(conn)
    if auth.on_token_refresh:
        auth.on_token_refresh(auth.to_bundle())
    return conn.session


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

    def _run_pkce_flow(self, conn: types.ConnectionP) -> None:
        # late import to avoid circular dependency at module load time
        from docuware import oauth

        endpoints = oauth.discover_oauth_endpoints(conn.base_url, verify=self.verify)
        self.token_endpoint = endpoints.token_endpoint

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

        # Bind directly (port 0 = ephemeral) and read the actual port from the
        # bound socket — probing for a free port beforehand would be racy.
        server = http.server.HTTPServer((self.redirect_host, self.redirect_port), _Handler)
        try:
            port = server.server_address[1]
            redirect_uri = f"http://{self.redirect_host}:{port}{self.callback_path}"
            verifier, challenge = oauth.generate_pkce()
            state = secrets.token_urlsafe(32)
            auth_url = oauth.build_authorization_url(
                endpoints.authorization_endpoint, self.client_id, redirect_uri, challenge, state,
            )
            opener = self.on_browser_open or webbrowser.open
            opener(auth_url)

            deadline = time.monotonic() + self.callback_timeout
            while _Handler.code is None and _Handler.error is None:
                remaining = deadline - time.monotonic()
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
        return _run_refresh_grant(self, conn)

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
                          with the credential bundle (see :meth:`to_bundle`).
                          Use it to persist tokens.
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
        return _run_refresh_grant(self, conn)

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
