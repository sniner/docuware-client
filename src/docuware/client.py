from __future__ import annotations

import json
import logging
import os
import pathlib
from typing import Iterator, Optional, Union

from docuware import conn, errors, organization, structs, types

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
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
    ) -> None:
        auth = conn.OAuth2Authenticator(
            username=username,
            password=password,
            organization=organization,
        )
        self.conn.authenticator = auth
        auth.login(self.conn)
        res = self.conn.get_json("/DocuWare/Platform")
        self.endpoints = structs.Endpoints(res)
        self.resources = structs.Resources(res)
        self.version = res.get("Version")

    def logoff(self) -> None:
        if self.conn.authenticator:
            self.conn.authenticator.logoff(self.conn)


def connect(
    url: Optional[str] = None,
    username: Optional[str] = None,
    password: Optional[str] = None,
    organization: Optional[str] = None,
    *,
    verify_certificate: bool = True,
    credentials_file: Optional[Union[str, pathlib.Path]] = None,
) -> DocuwareClient:
    """
    Connect to DocuWare server using credentials from arguments, environment, or file.

    Priority:
    1. Arguments
    2. Environment variables (DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG)
    3. Saves a credentials file
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

    client = DocuwareClient(url, verify_certificate=verify_certificate)
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
                credentials_file.parent.mkdir(exist_ok=True, parents=True)
                with open(credentials_file, "w", encoding="utf-8") as f:
                    json.dump(new_creds, f, indent=4)
                os.chmod(credentials_file, 0o600)
            except OSError as exc:
                log.warning("Failed to save credentials to %s: %s", credentials_file, exc)

    return client
