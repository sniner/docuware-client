from __future__ import annotations

import logging
import os
import pathlib
from typing import Any, Callable, Dict, Iterator, Optional, Type, Union

from docuware import auth, conn, errors, organization, persistence, structs, types

log = logging.getLogger(__name__)


_METHOD_REGISTRY: Dict[str, Type[auth.Authenticator]] = {
    "password":           auth.PasswordGrantAuthenticator,
    "client_credentials": auth.ClientCredentialsAuthenticator,
    "pkce":               auth.PkceAuthenticator,
    "token":              auth.TokenAuthenticator,
}


def _authenticator_from_bundle(bundle: Dict[str, Any]) -> auth.Authenticator:
    method = bundle.get("method", "password")
    cls = _METHOD_REGISTRY.get(method)
    if cls is None:
        raise errors.AccountError(f"Unknown auth method in credential bundle: {method!r}")
    return cls.from_bundle(bundle)


def _save_bundle(
    store: Optional[persistence.CredentialStore],
    bundle: Dict[str, Any],
    existing: Optional[Dict[str, Any]],
) -> None:
    """Save bundle to store iff it differs from existing. OSError → warning."""
    if store is None or existing == bundle:
        return
    try:
        store.save(bundle)
    except OSError as exc:
        log.warning("Failed to save credentials: %s", exc)


class DocuwareClient(types.DocuwareClientP):
    def __init__(
        self,
        url: str,
        verify_certificate: bool = True,
        timeout: Optional[float] = None,
        authenticator: Optional[types.AuthenticatorP] = None,
    ):
        self.conn = conn.Connection(
            url,
            case_insensitive=True,
            verify_certificate=verify_certificate,
            authenticator=authenticator,
            timeout=timeout,
        )
        self.endpoints: structs.Endpoints = structs.EMPTY_ENDPOINT_TABLE
        self.resources: structs.Resources = structs.EMPTY_RESOURCE_TABLE
        self.version: Optional[str] = None

    @property
    def organizations(self) -> Iterator[types.OrganizationP]:
        result = self.conn.get_json(self.endpoints["organizations"])
        return (organization.Organization(org, self) for org in result.get("Organization", []))

    def organization(
        self, key: str, *, required: bool = False
    ) -> Optional[types.OrganizationP]:
        """Access organization by id or name."""
        return structs.first_item_by_id_or_name(self.organizations, key, required=required)

    def login(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        organization: Optional[str] = None,
    ) -> DocuwareClient:
        """Run the configured authenticator's login flow and init the platform.

        Use this when you've built the authenticator yourself (custom refresh
        callback, custom browser opener, alternative :class:`Connection`) and
        want to drive the login step explicitly. :func:`connect` is the
        high-level wrapper that covers the common cases.

        Backwards-compat fallback: if no authenticator was passed to the
        constructor, the ``username`` / ``password`` / ``organization`` kwargs
        build a :class:`PasswordGrantAuthenticator` on the fly.
        """
        if not self.conn.authenticator:
            self.conn.authenticator = auth.PasswordGrantAuthenticator(
                username=username,
                password=password,
                organization=organization,
            )
        self.conn.authenticator.login(self.conn)
        self._init_platform()
        return self

    def _init_platform(self) -> None:
        res = self.conn.get_json("/DocuWare/Platform")
        self.endpoints = structs.Endpoints(res)
        self.resources = structs.Resources(res)
        self.version = res.get("Version")

    def logoff(self) -> None:
        if self.conn.authenticator:
            self.conn.authenticator.logoff(self.conn)

    def close(self) -> None:
        self.logoff()
        self.conn.close()

    def __enter__(self) -> DocuwareClient:
        return self

    def __exit__(self, *exc: object) -> None:
        self.close()


def connect(
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    organization: Optional[str] = None,
    *,
    authenticator: Optional[auth.Authenticator] = None,
    credential_store: Optional[persistence.CredentialStore] = None,
    credentials_file: Optional[Union[str, pathlib.Path]] = None,
    verify_certificate: bool = True,
    timeout: Optional[float] = None,
) -> DocuwareClient:
    """Connect to DocuWare using one of four supported auth flows.

    Resolution order:

    1. **Explicit ``authenticator=``** — used directly. URL is resolved from
       ``url`` arg, ``DW_URL`` env, or the ``url`` field of an existing store
       bundle. After login the resulting bundle is saved to ``credential_store``
       (if given). Token-rotating authenticators are auto-wired so rotated
       tokens persist on every refresh.
    2. **Populated ``credential_store=``** (non-password method) — the
       authenticator is reconstructed via ``method`` discriminator, then
       login() proceeds as above.
    3. **Legacy password flow** — ``url``/``username``/``password``/
       ``organization`` resolved via Arg > Env > Store. URL is required.
       After login, the ``.credentials``-style bundle is saved if changed.

    Args:
        authenticator:    Optional pre-built :class:`Authenticator`. Wins over
                          store-based reconstruction. Use this for PKCE or
                          client_credentials first-time setup.
        credential_store: Optional :class:`CredentialStore` adapter for
                          loading initial state and persisting rotated tokens.
        credentials_file: Legacy shortcut — lifted internally to a
                          :class:`JsonFileCredentialStore` at that path.
                          Mutually exclusive with ``credential_store``.
        timeout:          Request timeout in seconds. Defaults to ``DW_TIMEOUT``
                          env var, or 30 s.
    """
    if credentials_file is not None and credential_store is not None:
        raise ValueError("credentials_file and credential_store are mutually exclusive")
    if credentials_file is not None:
        credential_store = persistence.JsonFileCredentialStore(credentials_file)

    file_creds = credential_store.load() if credential_store is not None else None

    # --- Path 1: explicit authenticator ---
    if authenticator is not None:
        resolved_url = url or os.environ.get("DW_URL") or (file_creds or {}).get("url")
        if not resolved_url:
            raise errors.AccountError(
                "URL is required (arg, env DW_URL, or credential_store containing 'url')"
            )
        if credential_store is not None:
            authenticator.add_store(credential_store, url=resolved_url)
        client = DocuwareClient(
            resolved_url,
            verify_certificate=verify_certificate,
            timeout=timeout,
            authenticator=authenticator,
        ).login()
        if credential_store is not None:
            _save_bundle(
                credential_store,
                {**authenticator.to_bundle(), "url": resolved_url},
                file_creds,
            )
        return client

    # --- Path 2: rebuild non-password authenticator from store ---
    if file_creds and file_creds.get("method") and file_creds["method"] != "password":
        rebuilt = _authenticator_from_bundle(file_creds)
        resolved_url = url or os.environ.get("DW_URL") or file_creds.get("url")
        if not resolved_url:
            raise errors.AccountError("URL is required (arg, env DW_URL, or 'url' in store)")
        assert credential_store is not None  # narrowed by `file_creds` truthiness
        rebuilt.add_store(credential_store, url=resolved_url)
        client = DocuwareClient(
            resolved_url,
            verify_certificate=verify_certificate,
            timeout=timeout,
            authenticator=rebuilt,
        ).login()
        _save_bundle(
            credential_store,
            {**rebuilt.to_bundle(), "url": resolved_url},
            file_creds,
        )
        return client

    # --- Path 3: legacy password flow (Arg > Env > Store) ---
    resolved_url = url or os.environ.get("DW_URL") or (file_creds or {}).get("url")
    user = username or os.environ.get("DW_USERNAME") or (file_creds or {}).get("username")
    passwd = password or os.environ.get("DW_PASSWORD") or (file_creds or {}).get("password")
    org = organization or os.environ.get("DW_ORG") or (file_creds or {}).get("organization")

    if not resolved_url:
        raise errors.AccountError(
            "URL is required (arg, env DW_URL, or .credentials file)"
        )

    client = DocuwareClient(
        resolved_url, verify_certificate=verify_certificate, timeout=timeout,
    )
    client.login(username=user, password=passwd, organization=org)

    if credential_store is not None and user and passwd:
        new_bundle: Dict[str, Any] = {
            "method": "password",
            "url": resolved_url,
            "username": user,
            "password": passwd,
        }
        if org:
            new_bundle["organization"] = org
        _save_bundle(credential_store, new_bundle, file_creds)

    return client


def connect_with_tokens(
    url: str,
    access_token: str = "",
    refresh_token: str = "",
    token_endpoint: str = "",
    client_id: str = "",
    *,
    client_secret: str = "",
    token_store: Optional[persistence.CredentialStore] = None,
    on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None,
    verify_certificate: bool = True,
    timeout: Optional[float] = None,
) -> DocuwareClient:
    """Connect to DocuWare using an existing OAuth2 access+refresh token pair.

    .. deprecated:: 0.8.0
       Prefer ``connect(authenticator=TokenAuthenticator(...), credential_store=...)``
       which works the same way and is consistent with the other auth flows.

    Intended for applications that handle the OAuth2 login flow themselves
    (e.g. PKCE in a non-localhost setting) and obtain tokens externally. The
    client refreshes automatically on 401/403 using the refresh token.

    DocuWare rotates refresh tokens (RFC 6749 §10.4) and revokes the entire
    token family on reuse. Production callers should pass a ``token_store``
    so rotated tokens are persisted across restarts.

    Args:
        token_store:      Optional :class:`CredentialStore`. If populated,
                          its tokens override the explicit args; if empty,
                          the explicit args bootstrap it. Mutually exclusive
                          with ``on_token_refresh``.
        on_token_refresh: Mutually exclusive with ``token_store``.
    """
    if token_store is not None and on_token_refresh is not None:
        raise ValueError(
            "token_store and on_token_refresh are mutually exclusive — "
            "the store's save() is used as the refresh callback"
        )

    if token_store is not None:
        bundle = token_store.load()
        if bundle:
            stored_access = bundle.get("access_token", "")
            stored_refresh = bundle.get("refresh_token", "")
            if not (stored_access and stored_refresh):
                raise errors.AccountError(
                    "token_store returned an incomplete bundle "
                    "(missing access_token or refresh_token)"
                )
            if (access_token and access_token != stored_access) or (
                refresh_token and refresh_token != stored_refresh
            ):
                log.info(
                    "token_store contains tokens; ignoring explicit access_token/refresh_token"
                )
            access_token = stored_access
            refresh_token = stored_refresh
            # Recover static config from the bundle when the caller omitted it.
            token_endpoint = token_endpoint or bundle.get("token_endpoint", "")
            client_id = client_id or bundle.get("client_id", "")
            client_secret = client_secret or bundle.get("client_secret", "")
        elif not (access_token and refresh_token):
            raise errors.AccountError(
                "token_store is empty and no explicit access_token/refresh_token "
                "given — run the PKCE login first to seed the store"
            )

    if not access_token or not refresh_token:
        raise errors.AccountError(
            "access_token and refresh_token are required "
            "(or supply a populated token_store)"
        )
    if not token_endpoint or not client_id:
        raise errors.AccountError("token_endpoint and client_id are required")

    authenticator = auth.TokenAuthenticator(
        access_token=access_token,
        refresh_token=refresh_token,
        token_endpoint=token_endpoint,
        client_id=client_id,
        client_secret=client_secret,
        verify=verify_certificate,
        on_token_refresh=on_token_refresh,
    )
    return connect(
        url=url,
        authenticator=authenticator,
        credential_store=token_store,
        verify_certificate=verify_certificate,
        timeout=timeout,
    )
