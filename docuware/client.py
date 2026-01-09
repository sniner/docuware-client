from __future__ import annotations
import logging
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple, Type, Union

from docuware import conn, errors, structs, types, utils, organization

import requests

log = logging.getLogger(__name__)


class DocuwareClient(types.DocuwareClientP):
    def __init__(self, url: str, verify_certificate: bool = True):
        self.conn = conn.Connection(url, case_insensitive=True, verify_certificate=verify_certificate)
        self.endpoints: Dict[str, str] = {}
        self.resources: Dict[str, str] = {}
        self.version: Optional[str] = None

    @property
    def organizations(self) -> Generator[types.OrganizationP, None, None]:
        result = self.conn.get_json(self.endpoints["organizations"])
        return (organization.Organization(org, self) for org in result.get("Organization", []))

    def organization(self, key: str, *, required: bool = False) -> Optional[types.OrganizationP]:
        """Access organization by id or name."""
        return structs.first_item_by_id_or_name(self.organizations, key, required=required)

    def login(
        self,
        username: str,
        password: str,
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

# vim: set et sw=4 ts=4:
