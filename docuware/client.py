from __future__ import annotations
import logging
from typing import Any, Dict, Generator, Iterator, List, Optional, Tuple, Type, Union

from docuware import conn, errors, structs, types, utils, organization

log = logging.getLogger(__name__)


class DocuwareClient(types.DocuwareClientP):
    def __init__(self, url: str):
        self.conn = conn.Connection(url, case_insensitive=True)
        self.endpoints = {}
        self.resources = {}
        self.version = None

    @property
    def organizations(self) -> Generator[types.OrganizationP, None, None]:
        result = self.conn.get_json(self.endpoints["organizations"])
        return (organization.Organization(org, self) for org in result.get("Organization", []))

    def organization(self, key: str, default: Union[types.OrganizationP, None, types.Nothing] = types.NOTHING) -> Optional[types.OrganizationP]:
        """Access organization by id or name."""
        return structs.first_item_by_id_or_name(self.organizations, key, default=default)

    def login(self, username: str, password: str, organization: Optional[str] = None, cookiejar: Optional[dict] = None) -> dict:
        endpoint = "/DocuWare/Platform/Account/Logon"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {
            "LoginType": "DocuWare",
            "RedirectToMyselfInCaseOfError": "false",
            "RememberMe": "false",
            "Password": password,
            "UserName": username,
        }
        if organization:
            data["Organization"] = organization

        self.conn.cookiejar = cookiejar

        try:
            result = self.conn.post_json(endpoint, headers=headers, data=data)
            self.endpoints = structs.Endpoints(result)
            self.resources = structs.Resources(result)
            # for res in sorted(self.resources.values()):
            #     print(res)
            self.version = result.get("Version")
            return self.conn.cookiejar
        except errors.ResourceError as exc:
            raise errors.AccountError(f"Log in failed with code {exc.status_code}")

    def logoff(self):
        url = self.conn.make_url("/DocuWare/Platform/Account/Logoff")
        self.conn._get(url)

# vim: set et sw=4 ts=4:
