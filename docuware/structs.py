from __future__ import annotations
import re
from typing import (
    Dict,
    Iterable,
    List,
    Literal,
    Optional,
    Type,
    TypeVar,
    Union,
    overload,
)

from docuware import cidict, errors, types


# ConfigItemT = List[Dict[str, str]]
# ConfigT = Union[Dict[str, ConfigItemT], cidict.CaseInsensitiveDict[ConfigItemT]]


class Endpoints(cidict.CaseInsensitiveDict[str]):
    def __init__(self, config: types.ConfigT):
        super().__init__()
        for link in config.get("Links") or []:
            self[link["rel"]] = link["href"]


class ResourcePattern:
    def __init__(self, config: Union[Dict[str, str], cidict.CaseInsensitiveDict[str]]):
        self.name = config.get("Name") or "UndefinedResourcePattern"
        self.pattern = config.get("UriPattern") or ""
        self._fields = None

    @property
    def fields(self) -> List[str]:
        if self._fields is None:
            self._fields = re.findall(r"\{(\w+)\}", self.pattern)
        return self._fields

    def apply(self, data: Union[Dict[str, str], cidict.CaseInsensitiveDict[str]], strict: bool = False) -> str:
        s = self.pattern
        for name, value in data.items():
            s, n = re.subn("\\{" + name + "\\}", value, s, flags=re.IGNORECASE)
            if strict and n <= 0:
                raise errors.InternalError(f"Key '{name}' not found in pattern '{self.pattern}'")
        if strict:
            f = re.findall(r"\{(\w+)\}", s)
            if f:
                raise errors.InternalError(f"Pattern '{self.pattern}' incomplete, missing fields: {', '.join(f)}")
        return s

    def __lt__(self, other: object):
        if isinstance(other, ResourcePattern):
            return self.name < other.name
        return NotImplemented

    def __str__(self) -> str:
        return f"Resource {self.name} = '{self.pattern}'"


class Resources(cidict.CaseInsensitiveDict[ResourcePattern]):
    def __init__(self, config: Union[Dict, cidict.CaseInsensitiveDict]):
        super().__init__()
        for rc in config.get("Resources") or []:
            r = ResourcePattern(rc)
            self[r.name] = r


@overload
def first_item_by_id_or_name(
    items: Iterable[types.IdNameT],
    key: str,
    *,
    default: types.IdNameT,
    required: bool = False,
) -> types.IdNameT: ...

@overload
def first_item_by_id_or_name(
    items: Iterable[types.IdNameT],
    key: str,
    *,
    default: None = None,
    required: bool = True,
) -> types.IdNameT: ...

def first_item_by_id_or_name(
    items: Iterable[types.IdNameT],
    key: str,
    *,
    default: Optional[types.IdNameT] = None,
    required: bool = False,
) -> Optional[types.IdNameT]:
    name = key.casefold()
    for item in items:
        if item.id == key or item.name.casefold() == name:
            return item
    if required:
        raise KeyError(key)
    else:
        return default


@overload
def first_item_by_class(
    items: Iterable[types.IdNameT],
    cls: Type,
    *,
    default: types.IdNameT,
    required: bool = False,
) -> types.IdNameT: ...

@overload
def first_item_by_class(
    items: Iterable[types.IdNameT],
    cls: Type,
    *,
    default: None = None,
    required: bool = True,
) -> types.IdNameT: ...

def first_item_by_class(
    items: Iterable[types.IdNameT],
    cls: Type,
    *,
    default: Optional[types.IdNameT] = None,
    required: bool = False,
) -> Optional[types.IdNameT]:
    for item in items:
        if isinstance(item, cls):
            return item
    if required:
        raise KeyError(cls.__name__)
    else:
        return default

# vim: set et sw=4 ts=4:
