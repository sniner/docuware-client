from __future__ import annotations

from typing import (
    Any,
    Callable,
    Dict,
    Generator,
    Iterator,
    List,
    Literal,
    Optional,
    Protocol,
    Sequence,
    Tuple,
    TypeVar,
    Union,
    overload,
)

from httpx import Client, Response

class IdP(Protocol):
    @property
    def id(self) -> str: ...
    @id.setter
    def id(self, value: str) -> None: ...


class IdNameP(IdP, Protocol):
    @property
    def name(self) -> str: ...
    @name.setter
    def name(self, value: str) -> None: ...


IdNameT = TypeVar("IdNameT", bound="IdNameP")


class AuthenticatorP(Protocol):
    def authenticate(self, conn: ConnectionP) -> Client: ...

    def login(self, conn: ConnectionP) -> Dict: ...

    def logoff(self, conn: ConnectionP) -> None: ...


class ConnectionP(Protocol):
    authenticator: Optional[AuthenticatorP]
    session: Client
    _json_object_hook: Optional[Callable[[object], object]]

    def make_path(self, path: str, query: Dict[str, str]) -> str: ...

    def make_url(self, path: str, query: Optional[Dict[str, str]] = None) -> str: ...

    def post(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Response: ...

    def post_json(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Any: ...

    def post_text(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> str: ...

    def put(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Any] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Response: ...

    def put_json(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Any] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None,
    ) -> Any: ...

    def get(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
    ) -> Response: ...

    def get_json(self, path: str, headers: Optional[Dict[str, str]] = None) -> Any: ...

    def get_text(self, path: str, headers: Optional[Dict[str, str]] = None) -> str: ...

    def delete(
        self, path: str, headers: Optional[Dict[str, str]] = None
    ) -> Response: ...

    def get_bytes(
        self, path: str, mime_type: Optional[str] = None, data: Optional[Any] = None
    ) -> Tuple[bytes, str, str]: ...


class DocuwareClientP(Protocol):
    conn: ConnectionP

    @property
    def organizations(self) -> Generator[OrganizationP, None, None]: ...

    def organization(
        self,
        key: str,
        *,
        required: bool = False,
    ) -> Optional[OrganizationP]: ...

    def login(
        self,
        username: str,
        password: str,
        organization: Optional[str] = None,
        saved_session: Optional[Dict] = None,
    ) -> Dict: ...

    def logoff(self) -> None: ...


ConfigItemT = List[Dict[str, str]]
ConfigT = Union[Dict[str, ConfigItemT], cidict.CaseInsensitiveDict[ConfigItemT]]


class EndpointsP(Protocol):
    def __init__(self, config: ConfigT) -> None: ...

    def __getitem__(self, key: str) -> str: ...

    def __setitem__(self, key: str, value: str) -> None: ...

    def __delitem__(self, key: str) -> None: ...

    def __iter__(self) -> Iterator[str]: ...

    def __len__(self) -> int: ...


class UserP(IdNameP, Protocol):
    @property
    def active(self) -> bool: ...

    @active.setter
    def active(self, state: bool) -> None: ...

    def as_dict(self, overrides: Optional[Dict[str, Any]] = None) -> Dict[str, str]: ...

    def make_db_name(self) -> str: ...

    def add_to_group(self, group: GroupP) -> bool: ...

    def remove_from_group(self, group: GroupP) -> bool: ...


class UsersP(Protocol):
    def __init__(self, organization: OrganizationP): ...

    def __iter__(self) -> Generator[UserP, None, None]: ...

    def __getitem__(self, key: str) -> UserP: ...

    def get(self, key: str, default: Optional[UserP] = None) -> Optional[UserP]: ...

    def add(self, user: UserP, password: Optional[str] = None) -> Optional[UserP]: ...


class GroupP(IdNameP, Protocol):
    @staticmethod
    def from_response(response: Dict, organization: OrganizationP) -> GroupP: ...

    @property
    def users(self) -> Generator[UserP, None, None]: ...

    def add_user(self, user: UserP) -> bool: ...

    def remove_user(self, user: UserP) -> bool: ...


class GroupsP(Protocol):
    def __init__(self, organization: OrganizationP): ...

    def __iter__(self) -> Generator[GroupP, None, None]: ...

    def __getitem__(self, key: str) -> GroupP: ...

    def get(self, key: str, default: Optional[GroupP] = None) -> Optional[GroupP]: ...


class OrganizationP(IdNameP, Protocol):
    @property
    def client(self) -> DocuwareClientP: ...
    @property
    def endpoints(self) -> EndpointsP: ...

    @property
    def conn(self) -> ConnectionP: ...

    @property
    def file_cabinets(self) -> Generator[FileCabinetP, None, None]: ...

    @overload
    def file_cabinet(
        self, key: str, *, required: Literal[True]
    ) -> FileCabinetP: ...

    @overload
    def file_cabinet(
        self, key: str, *, required: Literal[False]
    ) -> Optional[FileCabinetP]: ...

    def file_cabinet(
        self,
        key: str,
        *,
        required: bool = False,
    ) -> Optional[FileCabinetP]: ...

    @property
    def info(self) -> cidict.CaseInsensitiveDict: ...

    @property
    def my_tasks(self) -> Sequence: ...

    @property
    def users(self) -> UsersP: ...

    @property
    def groups(self) -> GroupsP: ...


class FileCabinetP(IdNameP, Protocol):
    @property
    def organization(self) -> OrganizationP: ...

    @property
    def dialogs(self) -> Sequence[DialogP]: ...

    @overload
    def dialog(self, key: str, *, required: Literal[True]) -> DialogP: ...

    @overload
    def dialog(self, key: str, *, required: Literal[False]) -> Optional[DialogP]: ...

    def dialog(self, key: str, *, required: bool = False) -> Optional[DialogP]: ...

    @overload
    def search_dialog(
        self, key: Optional[str] = None, *, required: Literal[True]
    ) -> SearchDialogP: ...

    @overload
    def search_dialog(
        self, key: Optional[str] = None, *, required: Literal[False]
    ) -> Optional[SearchDialogP]: ...

    def search_dialog(
        self, key: Optional[str] = None, *, required: bool = False
    ) -> Optional[SearchDialogP]: ...


class SearchFieldP(IdNameP, Protocol):
    @property
    def dialog(self) -> DialogP: ...
    length: int
    type: Optional[str]

    def values(self) -> List[Any]: ...


class DialogP(IdNameP, Protocol):
    client: DocuwareClientP

    @staticmethod
    def from_config(config: Dict, file_cabinet: FileCabinetP) -> DialogP: ...

    @property
    def fields(self) -> Dict[str, SearchFieldP]: ...


SearchConditionsT = Union[str, List[str], Tuple[str], Dict[str, Union[str, List[str]]]]


class SearchDialogP(DialogP, Protocol):
    @property
    def fields(self) -> Dict[str, SearchFieldP]: ...

    def search(
        self, conditions: SearchConditionsT, operation: Optional[str] = None
    ) -> SearchResultP: ...


class SearchResultP(Protocol):
    count: int

    def __iter__(self) -> Iterator[SearchResultItemP]: ...


class SearchResultItemP(Protocol):
    def thumbnail(self) -> Tuple[bytes, str, str]: ...

    @property
    def document(self) -> DocumentP: ...


class DocumentP(Protocol):
    @property
    def id(self) -> Optional[str]: ...
    @id.setter
    def id(self, value: Optional[str]) -> None: ...


class FieldValueP(IdNameP, Protocol): ...


class MyTasksP(Protocol): ...


# vim: set et sw=4 ts=4:
