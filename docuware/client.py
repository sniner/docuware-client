from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Dict, Generator, Optional, Union

from docuware import conn, organization, structs, types

log = logging.getLogger(__name__)


class DocuwareClient(types.DocuwareClientP):
    def __init__(self, url: str, verify_certificate: bool = True):
        self.conn = conn.Connection(
            url,
            case_insensitive=True,
            verify_certificate=verify_certificate,
        )
        self.endpoints: structs.Endpoints = structs.EMPTY_ENDPOINT_TABLE
        self.resources: structs.Resources = structs.EMPTY_RESOURCE_TABLE
        self.version: Optional[str] = None

    @property
    def organizations(self) -> Generator[types.OrganizationP, None, None]:
        result = self.conn.get_json(self.endpoints["organizations"])
        return (organization.Organization(org, self) for org in result.get("Organization", []))

    def organization(
        self, key: str, *, required: bool = False
    ) -> Optional[types.OrganizationP]:
        """Access organization by id or name."""
        return structs.first_item_by_id_or_name(self.organizations, key, required=required)

    def login(
        self,
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
        saved_session: Optional[Dict] = None,
        oauth2: Optional[bool] = None,
    ) -> Dict:
        if oauth2 is None:
            oauth2 = "access_token" in saved_session if saved_session else True

        if oauth2:
            auth = conn.OAuth2Authenticator(
                username=username,
                password=password,
                organization=organization,
                saved_state=saved_session,
            )
            self.conn.authenticator = auth
            state = auth.login(self.conn)
        else:
            auth = conn.CookieAuthenticator(
                username=username,
                password=password,
                organization=organization,
                saved_state=saved_session,
            )
            self.conn.authenticator = auth if saved_session else None
            state = auth.login(self.conn)
            self.conn.authenticator = auth

        res = self.conn.get_json("/DocuWare/Platform")
        self.endpoints = structs.Endpoints(res)
        self.resources = structs.Resources(res)
        self.version = res.get("Version")
        return state or {}

    def logoff(self) -> None:
        if self.conn.authenticator:
            self.conn.authenticator.logoff(self.conn)


def connect(
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    organization: Optional[str] = None,
    *,
    verify_certificate: Optional[bool] = None,
    oauth2: bool = True,
    config_dir: Union[str, pathlib.Path] = ".",
) -> DocuwareClient:
    """
    Connect to DocuWare server using credentials from arguments, environment, or file.

    Priority:
    1. Arguments
    2. Environment variables (DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG)
    3. .credentials file in config_dir
    """
    config_dir = pathlib.Path(config_dir)
    cred_file = config_dir / ".credentials"
    session_file = config_dir / ".session"

    # Load from file if exists
    file_creds = {}
    if cred_file.exists():
        try:
            with open(cred_file, encoding="utf-8-sig") as f:
                file_creds = json.load(f)
        except Exception:
            log.warning(f"Failed to load credentials from {cred_file}")

    # Resolve values (Arg > Env > File)
    url = url or os.environ.get("DW_URL") or file_creds.get("url")
    username = username or os.environ.get("DW_USERNAME") or file_creds.get("username")
    password = password or os.environ.get("DW_PASSWORD") or file_creds.get("password")
    organization = organization or os.environ.get("DW_ORG") or file_creds.get("organization")

    # Default verify_certificate to True if not provided
    if verify_certificate is None:
        verify_certificate = True

    if not url:
        raise ValueError("URL is required (arg, env DW_URL, or .credentials file)")

    # Initialize client
    client = DocuwareClient(url, verify_certificate=verify_certificate)

    # Load session if available
    saved_session = None
    if session_file.exists():
        try:
            with open(session_file, encoding="utf-8-sig") as f:
                saved_session = json.load(f)
        except Exception:
            log.warning(f"Failed to load session from {session_file}")

    # Login
    new_session = client.login(
        username=username,
        password=password,
        organization=organization,
        saved_session=saved_session,
        oauth2=oauth2,
    )

    # Save session
    try:
        with open(session_file, "w", encoding="utf-8") as f:
            json.dump(new_session, f)
    except Exception:
        log.warning(f"Failed to save session to {session_file}")

    # Save credentials if we have full credentials provided
    # Only save if we have at least username and password to make it a valid credential set
    if username and password:
        new_creds = {
            "url": url,
            "username": username,
            "password": password,
        }
        if organization:
            new_creds["organization"] = organization

        if file_creds != new_creds:
            try:
                with open(cred_file, "w", encoding="utf-8") as f:
                    json.dump(new_creds, f, indent=4)
            except Exception:
                log.warning(f"Failed to save credentials to {cred_file}")

    return client
