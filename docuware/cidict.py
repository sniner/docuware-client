"""
Case-insensitive dictionary.
"""

from __future__ import annotations
from collections.abc import MutableMapping, ItemsView, KeysView, ValuesView
from typing import Any, Dict, Generator, Generic, Iterator, Optional, Tuple, TypeVar

VT = TypeVar('VT')

class CaseInsensitiveDict(MutableMapping[str, VT], Generic[VT]):
    def __init__(self, initial_values: Any = None, **kwargs: VT) -> None:
        self._items: Dict[str, Tuple[str, VT]] = dict()
        if initial_values is not None:
            if isinstance(initial_values, (dict, CaseInsensitiveDict)):
                for key, value in initial_values.items():
                    self.__setitem__(key, value)
            elif isinstance(initial_values, (list, tuple)):
                for (key, value) in initial_values:
                    self.__setitem__(key, value)
            else:
                raise TypeError("Unsupported type for initial_values")
        for key, value in kwargs.items():
            self.__setitem__(key, value)

    @staticmethod
    def _strip_case(key: Any) -> str:
        return str(key).casefold()

    def __contains__(self, key: Any) -> bool:
        return self._items.__contains__(self._strip_case(key))

    def __getitem__(self, key: str) -> VT:
        try:
            return self._items[self._strip_case(key)][1]
        except KeyError:
            raise KeyError(key)

    def __setitem__(self, key: str, value: VT) -> None:
        self._items[self._strip_case(key)] = (key, value)

    def __iter__(self) -> Generator[str, None, None]:
        return (item[0] for item in self._items.values())

    def __delitem__(self, key: str) -> None:
        del self._items[self._strip_case(key)]

    def __len__(self) -> int:
        return len(self._items)

    def __eq__(self, other: Any) -> bool:
        if not isinstance(other, CaseInsensitiveDict):
            return NotImplemented
        return dict(self.case_insensitive_items()) == dict(other.case_insensitive_items())

    def get(self, key: str, default: Optional[VT] = None) -> Optional[VT]:
        try:
            return self.__getitem__(key)
        except KeyError:
            return default

    def items(self) -> ItemsView[str, VT]:
        return ItemsView(self)

    def keys(self) -> KeysView[str]:
        return KeysView(self)

    def values(self) -> ValuesView[VT]:
        return ValuesView(self)

    def case_insensitive_items(self) -> Generator[Tuple[str, VT], None, None]:
        return ((k, v[1]) for (k, v) in self._items.items())

    def copy(self) -> CaseInsensitiveDict[VT]:
        return CaseInsensitiveDict(list(self._items.values()))

    def __repr__(self) -> str:
        return str(dict(self.items()))

# vim: set et sw=4 ts=4:
