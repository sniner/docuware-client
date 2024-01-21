from __future__ import annotations
import re
from typing import Iterable, List, Optional, Type, TypeVar, Union

from docuware import cidict, errors, types

T = TypeVar("T")


class Endpoints(cidict.CaseInsensitiveDict):
    def __init__(self, config: Union[dict, cidict.CaseInsensitiveDict]):
        super().__init__()
        for link in config.get("Links", []):
            self[link["rel"]] = link["href"]


class Resources(cidict.CaseInsensitiveDict):
    def __init__(self, config: Union[dict, cidict.CaseInsensitiveDict]):
        super().__init__()
        for rc in config.get("Resources", []):
            r = ResourcePattern(rc)
            self[r.name] = r


class ResourcePattern:
    def __init__(self, config: Union[dict, cidict.CaseInsensitiveDict]):
        self.name = config.get("Name")
        self.pattern = config.get("UriPattern")
        self._fields = None

    @property
    def fields(self) -> List[str]:
        if self._fields is None:
            self._fields = re.findall(r"\{(\w+)\}", self.pattern)
        return self._fields

    def apply(self, data: Union[dict, cidict.CaseInsensitiveDict], strict: bool = False) -> str:
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

    def __str__(self):
        return f"Resource {self.name} = '{self.pattern}'"


def first_item_by_id_or_name(items: Iterable[T], key: str, default: Union[T, None, types.Nothing] = types.NOTHING) -> Optional[T]:
    name = key.casefold()
    for item in items:
        if item.id == key or item.name.casefold() == name:
            return item
    if default is types.NOTHING:
        raise KeyError(key)
    else:
        return default


def first_item_by_class(items: Iterable[T], cls: Type, default: Union[T, None, types.Nothing] = types.NOTHING) -> Optional[T]:
    for item in items:
        if isinstance(item, cls):
            return item
    if default is types.NOTHING:
        raise KeyError(cls.__name__)
    else:
        return default

# vim: set et sw=4 ts=4:
