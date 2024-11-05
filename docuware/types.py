from __future__ import annotations

from typing import Protocol, Generator, List, Optional, TypeVar, Union


class Nothing:
    _instance = None

    def __new__(cls):
        if cls._instance is None:
            cls._instance = super().__new__(cls)
        return cls._instance

    def __repr__(self):
        return "<nothing>"


NOTHING = Nothing()

T = TypeVar("T")


class DocuwareClientP(Protocol):
    @property
    def organizations(self) -> Generator[OrganizationP, None, None]:
        ...

    def organization(self, key: str, default: Union[OrganizationP, None, Nothing] = NOTHING) -> Optional[OrganizationP]:
        ...

    def login(self, username: str, password: str, organization: Optional[str] = None, saved_session: Optional[dict] = None) -> dict:
        ...

    def logoff(self):
        ...


class OrganizationP(Protocol):
    @property
    def conn(self) -> conn.Connection:
        ...


class FileCabinetP(Protocol):
    def dialogs(self) -> List[DialogP]:
        ...

    def dialog(self, key: str, default: Union[DialogP, None, Nothing] = NOTHING) -> DialogP:
        ...

    def search_dialog(self, key: Optional[str] = None, default: Union[DialogP, None, Nothing] = NOTHING) -> DialogP:
        ...


class DialogP(Protocol):
    @staticmethod
    def from_config(config: dict, file_cabinet: FileCabinetP) -> DialogP:
        ...


class MyTasksP(Protocol):
    ...

# vim: set et sw=4 ts=4:
