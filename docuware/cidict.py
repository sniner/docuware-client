"""
Case-insensitive dictionary.

Almost identical to CaseInsensitiveDict() of requests (https://github.com/psf/requests)
"""

from __future__ import annotations
from collections.abc import MutableMapping
from typing import Any, Generator, Optional, Tuple


class CaseInsensitiveDict(MutableMapping):
    def __init__(self, initial_values: Any = None, **kwargs: Any):
        self._items = dict()
        if initial_values is not None:
            if isinstance(initial_values, (dict, CaseInsensitiveDict)):
                for key, value in initial_values.items():
                    self.__setitem__(key, value)
            elif isinstance(initial_values, (list, tuple)):
                for (key, value) in initial_values:
                    self.__setitem__(key, value)
            else:
                raise TypeError
        for key, value in kwargs.items():
            self.__setitem__(key, value)

    @staticmethod
    def _strip_case(string: str) -> str:
        return string.casefold()

    def __contains__(self, key: str) -> Any:
        return self._items.__contains__(self._strip_case(key))

    def __getitem__(self, key: str) -> Any:
        try:
            return self._items[self._strip_case(key)][1]
        except KeyError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: Any):
        self._items[self._strip_case(key)] = (key, value)

    def __iter__(self) -> Generator[Tuple[str, Any], None, None]:
        return (k for k, v in self._items.values())

    def __delitem__(self, key):
        del self._items[self._strip_case(key)]

    def __len__(self):
        return len(self._items)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CaseInsensitiveDict):
            return NotImplemented
        return dict(self.case_insensitive_items()) == dict(other.case_insensitive_items())

    def get(self, key: str, default: Any = None) -> Optional[Any]:
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def items(self) -> Generator[Tuple[str, Any], None, None]:
        for v in self._items.values():
            yield v

    def keys(self) -> Generator[str, None, None]:
        for v in self._items.values():
            yield v[0]

    def values(self) -> Generator[Any, None, None]:
        for v in self._items.values():
            yield v[1]

    def case_insensitive_items(self) -> Generator[Tuple[str, Any], None, None]:
        return ((k, v[1]) for (k, v) in self._items.items())

    def copy(self):
        return CaseInsensitiveDict(self._items.values())

    def __repr__(self):
        return str(dict(self.items()))

# vim: set et sw=4 ts=4:
