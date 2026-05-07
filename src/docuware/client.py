from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Any, Callable, Dict, Iterator, Optional, Union

from docuware import auth, conn, errors, organization, persistence, structs, types, utils

log = logging.getLogger(__name__)


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
        if not self.conn.authenticator:
            self.conn.authenticator = auth.OAuth2Authenticator(
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
    verify_certificate: bool = True,
    credentials_file: Optional[Union[str, pathlib.Path]] = None,
    timeout: Optional[float] = None,
) -> DocuwareClient:
    """
    Connect to DocuWare server using credentials from arguments, environment, or file.

    Priority:
    1. Arguments
    2. Environment variables (DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG)
    3. Saves a credentials file

    Args:
        timeout: Request timeout in seconds.  Defaults to the value of the
                 ``DW_TIMEOUT`` environment variable, or 30 s if not set.
    """
    credentials_file = pathlib.Path(credentials_file) if credentials_file else None

    # Load from file if exists
    file_creds = {}
    if credentials_file and credentials_file.exists():
        try:
            with open(credentials_file, encoding="utf-8-sig") as f:
                file_creds = json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load credentials from %s: %s", credentials_file, exc)

    # Resolve values (Arg > Env > File)
    url = url or os.environ.get("DW_URL") or file_creds.get("url")
    user = username or os.environ.get("DW_USERNAME") or file_creds.get("username")
    passwd = password or os.environ.get("DW_PASSWORD") or file_creds.get("password")
    org = organization or os.environ.get("DW_ORG") or file_creds.get("organization")

    if not url:
        raise errors.AccountError("URL is required (arg, env DW_URL, or .credentials file)")

    client = DocuwareClient(url, verify_certificate=verify_certificate, timeout=timeout)
    client.login(username=user, password=passwd, organization=org)

    # Save credentials if requested
    if credentials_file and user and passwd:
        new_creds = {
            "url": url,
            "username": user,
            "password": passwd,
        }
        if org:
            new_creds["organization"] = org

        if file_creds != new_creds:
            try:
                utils.atomic_json_write(credentials_file, new_creds, indent=4)
            except OSError as exc:
                log.warning("Failed to save credentials to %s: %s", credentials_file, exc)

    return client


def connect_with_tokens(
    url: str,
    access_token: str = "",
    refresh_token: str = "",
    token_endpoint: str = "",
    client_id: str = "",
    *,
    client_secret: str = "",
    token_store: Optional[persistence.TokenStore] = None,
    on_token_refresh: Optional[Callable[[Dict[str, Any]], None]] = None,
    verify_certificate: bool = True,
    timeout: Optional[float] = None,
) -> DocuwareClient:
    """Connect to DocuWare using an existing OAuth2 access+refresh token pair.

    Intended for applications that handle the OAuth2 login flow themselves
    (e.g. PKCE) and obtain tokens externally.  The client will automatically
    refresh the access token on 401/403 using the refresh token.

    Note: this function does *not* call :func:`~docuware.oauth.discover_oauth_endpoints`
    — the caller must resolve the token_endpoint beforehand.

    DocuWare rotates refresh tokens (RFC 6749 §10.4) and revokes the entire
    token family on reuse. Production callers should pass a ``token_store``
    so the rotated tokens are persisted across process restarts; otherwise
    the next start will fail with ``invalid_grant`` and force a fresh PKCE
    login.

    Args:
        url:              DocuWare Platform base URL.
        access_token:     OAuth2 access token. Optional when ``token_store``
                          already contains tokens; required otherwise.
        refresh_token:    OAuth2 refresh token. Optional when ``token_store``
                          already contains tokens; required otherwise.
        token_endpoint:   Token endpoint URL (from OpenID Connect discovery).
        client_id:        OAuth2 client ID.
        client_secret:    OAuth2 client secret — required for confidential clients
                          (web apps), empty for public/native clients (default).
        token_store:      Optional :class:`~docuware.TokenStore` adapter.  If
                          set, ``load()`` is consulted for the initial tokens
                          (falling back to the explicit ``access_token`` /
                          ``refresh_token`` arguments as a bootstrap seed),
                          and ``save()`` is wired in as the rotation callback.
                          Mutually exclusive with ``on_token_refresh``.
        on_token_refresh: Optional callback(tokens: dict) called after each
                          successful token refresh — use it to persist new tokens.
                          Mutually exclusive with ``token_store``.
        verify_certificate: Whether to verify TLS certificates (default True).
        timeout:          Request timeout in seconds.  Defaults to the value of
                          the ``DW_TIMEOUT`` environment variable, or 30 s if not set.

    Returns:
        Connected DocuwareClient instance.
    """
    if token_store is not None:
        if on_token_refresh is not None:
            raise ValueError(
                "token_store and on_token_refresh are mutually exclusive — "
                "the store's save() is used as the refresh callback"
            )
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
        elif access_token and refresh_token:
            # Bootstrap: seed the empty store with the supplied tokens so a
            # crash before the first refresh does not lose them.
            token_store.save({"access_token": access_token, "refresh_token": refresh_token})
        else:
            raise errors.AccountError(
                "token_store is empty and no explicit access_token/refresh_token "
                "given — run the PKCE login first to seed the store"
            )
        on_token_refresh = token_store.save

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
    return DocuwareClient(
        url,
        verify_certificate=verify_certificate,
        timeout=timeout,
        authenticator=authenticator,
    ).login()
