from __future__ import annotations
import logging
from typing import Dict, Generator, Optional, Union

import re
import requests

from . import errors, types, structs, utils


log = logging.getLogger(__name__)



class User:
    def __init__(
            self,
            name: Optional[str] = None,
            first_name: Optional[str] = None,
            last_name: Optional[str] = None,
            salutation: Optional[str] = None,
            email: Optional[str] = None,
            db_name: Optional[str] = None,
        ):
        self.first_name = first_name
        self.last_name = last_name
        self.name = name
        self.salutation = salutation
        self.email = email
        self.db_name = db_name
        self.organization = None
        self.id = None
        self._active = None
        self.endpoints = None

    @property
    def name(self) -> str:
        if self._full_name:
            return self._full_name
        else:
            return " ".join([n for n in [self._first_name, self._last_name] if n])

    @name.setter
    def name(self, name: str):
        if name:
            self._full_name = name
            parts = name.split(", ", 1)
            if len(parts) > 1:
                self._last_name = parts[0]
                self._first_name = parts[1]
            else:
                parts = name.split(" ", 1)
                if len(parts) > 1:
                    self._first_name = parts[0]
                    self._last_name = parts[1]
                else:
                    self._first_name = None
                    self._last_name = name
        else:
            self._full_name = None

    @property
    def first_name(self) -> str:
        return self._first_name

    @first_name.setter
    def first_name(self, first_name: str):
        self._first_name = first_name
        self._full_name = None

    @property
    def last_name(self) -> str:
        return self._last_name

    @last_name.setter
    def last_name(self, last_name: str):
        self._last_name = last_name
        self._full_name = None

    @property
    def groups(self) -> Generator[Group, None, None]:
        result = self.organization.client.conn.get_json(self.endpoints["groups"])
        return (Group.from_response(g, self.organization) for g in result.get("Item", []))

    def make_db_name(self) -> str:
        n = "".join([n for n in [self._last_name, self._first_name] if n]) or self.name
        n = re.sub(r"[^A-Za-z0-9]", "", n) or str(id(self))
        return n[0:8].upper()

    @staticmethod
    def from_response(response: dict, organization: types.OrganizationP) -> User:
        u = User(
            salutation=response.get("Salutation"),
            email=response.get("EMail"),
        )
        u._full_name = response.get("Name")
        u._first_name = response.get("FirstName")
        u._last_name = response.get("LastName")
        u.id = response.get("Id")
        u.db_name = response.get("DBName")
        u._active = response.get("Active")
        u.endpoints = structs.Endpoints(response)
        u.organization = organization
        return u

    def as_dict(self, overrides: Optional[Dict[str, str]] = None) -> Dict[str, str]:
        d = {
            item[0]: item[1] for item in [
                ("Name", self.name),
                ("FirstName", self.first_name),
                ("LastName", self.last_name),
                ("Salutation", self.salutation),
                ("EMail", self.email),
                ("Id", self.id),
                ("DBName", self.db_name),
                ("Active", self.active),
            ] if item[1]
        }
        if overrides:
            return {**d, **overrides}
        else:
            return d

    @property
    def active(self) -> bool:
        return True if self._active else False

    @active.setter
    def active(self, state: bool):
        if self.active != state:
            if not self.id:
                raise errors.UserOrGroupError(f"Not a registered user: {self}")
            body = self.as_dict(overrides={"Active": state})
            try:
                result = self.organization.conn.post_json(self.organization.endpoints["userInfo"], json=body)
            except requests.RequestException as exc:
                raise errors.UserOrGroupError(f"Unable to set activation status of user {self}: {exc}")
            else:
                self._active = state

    def add_to_group(self, group: Group) -> bool:
        return group.add_user(self)

    def remove_from_group(self, group: Group) -> bool:
        return group.remove_user(self)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', id='{self.id}')"


class Users:
    def __init__(self, organization: types.OrganizationP):
        self.organization = organization

    def __iter__(self) -> Generator[User, None, None]:
        result = self.organization.conn.get_json(self.organization.endpoints["users"])
        return (User.from_response(user, self.organization) for user in result.get("User", []))

    def __getitem__(self, key: str) -> User:
        return structs.first_item_by_id_or_name(self, key)

    def get(self, key: str, default: Optional[User] = None) -> Optional[User]:
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def add(self, user: User, password: Optional[str] = None) -> Optional[User]:
        headers = {
            "Content-Type": "application/vnd.docuware.platform.createorganizationuser+json"
        }
        try:
            body = user.as_dict()
            if "DBName" not in body:
                body["DBName"] = body.make_db_name()
            body["Password"] = password or utils.random_password()
            result = self.organization.conn.post_json(
                self.organization.endpoints["userInfo"],
                headers=headers,
                json=body,
            )
        except Exception as exc:
            log.debug("Unable to create user %s: %s", user, exc)
            return None
        # FIXME: Check result instead of this hack:
        for item in self:
            if item.db_name == body.db_name:
                return item
        return None


class Group:
    def __init__(self, name: str):
        self.name = name
        self.id = None
        self.organization = None
        self.endpoints = None

    @staticmethod
    def from_response(response: dict, organization: types.OrganizationP):
        g = Group(
            name=response.get("Name")
        )
        g.id = response.get("Id")
        g.endpoints = structs.Endpoints(response)
        g.organization = organization
        return g

    @property
    def users(self) -> Generator[User, None, None]:
        result = self.organization.client.conn.get_json(self.endpoints["users"])
        return (User.from_response(u, self.organization) for u in result.get("User", []))

    # FIXME: Testing needed, the endpoint looks very suspicious
    def _set_user_membership(self, user: User, include: bool):
        if not self.id:
            # FIXME: raise a better suited exception
            raise ValueError("Not a registered group")
        if not user.id:
            # FIXME: raise a better suited exception
            raise ValueError("Not a registered user")

        headers = {
            "Accept": "application/json",
            "Content-Type": "application/json"
        }

        body = {
            "Ids": [
                self.id
            ],
            "OperationType": "Add" if include else "Remove"
        }

        try:
            result = self.organization.conn.put(
                "/DocuWare/Platform/Organization/UserGroups",
                headers=headers,
                params={"UserId": user.id},
                json=body,
            )
            # FIXME: check result
        except Exception as exc:
            log.debug("Changing group membership of user %s failed: %s", user, exc)
            return False
        return True

    def add_user(self, user: User) -> bool:
        return self._set_user_membership(user, include=True)

    def remove_user(self, user: User) -> bool:
        return self._set_user_membership(user, include=False)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"

    def __repr__(self) -> str:
        return f"{self.__class__.__name__}(name='{self.name}', id='{self.id}')"


class Groups:
    def __init__(self, organization: types.OrganizationP):
        self.organization = organization

    def __iter__(self):
        result = self.organization.client.conn.get_json(self.organization.endpoints["groups"])
        return (Group.from_response(group, self.organization) for group in result.get("Item", []))

    def __getitem__(self, key: str) -> Group:
        return structs.first_item_by_id_or_name(self, key)

    def get(self, key: str, default: Optional[Group] = None) -> Optional[Group]:
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

# vim: set et sw=4 ts=4:
