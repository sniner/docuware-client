from __future__ import annotations

import collections
import enum
from typing import Dict, List, Optional, Tuple, Union

from docuware import cidict


class CharReader:
    def __init__(self, text: str):
        self.text = text
        self._itext = iter(text)
        self._unget_buffer = collections.deque()

    def getch(self) -> Optional[str]:
        if self._unget_buffer:
            return self._unget_buffer.popleft()
        else:
            return next(self._itext, None)

    def ungetch(self, char: Optional[str]) -> None:
        if char is not None:
            self._unget_buffer.append(char)

    def peekch(self) -> Optional[str]:
        ch = self.getch()
        self.ungetch(ch)
        return ch

    def __repr__(self) -> str:
        return f"CharReader({repr(self.text)})"


class _CDState(enum.IntEnum):
    TYPE_START = 0
    TYPE = 1
    PARAM_START = 10
    PARAM_KEY = 11
    PARAM_VALUE_START = 20
    PARAM_VALUE = 21
    QUOTED_VALUE = 25
    AFTER_QUOTE = 26


class _SCState(enum.IntEnum):
    FIELD_START = 0
    FIELD = 1
    AFTER_FIELD = 2
    VALUE_START = 10
    VALUE = 11
    QUOTED_VALUE = 20
    AFTER_VALUE = 30


def parse_content_disposition(
    text: Optional[str], case_insensitive: bool = True
) -> Union[Dict[str, str], cidict.CaseInsensitiveDict]:
    """
    Parser for HTTP Content-Disposition header values. For example 'attachment; filename="filename.jpg"' will
    return { type: "attachment", filename: "filename.jpg" }.

    :param text: The text that follows "Content-Disposition:".
    :param case_insensitive: Determines whether a standard dict or a case-insensitive dict will be returned.
    :return: A dict-like object.
    """
    fields = cidict.CaseInsensitiveDict() if case_insensitive else dict()
    if text is None:
        return fields

    state = _CDState.TYPE_START
    key = ""
    value = ""
    reader = CharReader(text)

    while True:
        ch = reader.getch()
        if state == _CDState.TYPE_START:
            if ch is None:
                break
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                value = ""
                state = _CDState.TYPE
        elif state == _CDState.TYPE:
            if ch == ";":
                fields["type"] = value.rstrip()
                state = _CDState.PARAM_START
            elif ch is None:
                fields["type"] = value.rstrip()
                break
            else:
                value += ch
        elif state == _CDState.PARAM_START:
            if ch is None:
                break
            if ch.isspace() or ch == ";":
                pass
            elif ch.isalnum() or ch == "*":  # Allow * for extended parameters (RFC 5987)
                reader.ungetch(ch)
                key = ""
                value = ""
                state = _CDState.PARAM_KEY
            else:
                # Invalid char: skip for robustness
                pass
        elif state == _CDState.PARAM_KEY:
            if ch is None or ch == "=":
                key = key.rstrip()
                state = _CDState.PARAM_VALUE_START
            elif ch.isalnum() or ch in "-_*":  # items allowed in param name
                key += ch
            else:
                pass  # ignore invalid chars in key
        elif state == _CDState.PARAM_VALUE_START:
            if ch is None or ch == ";":
                fields[key] = value
                state = _CDState.PARAM_START
            elif ch == '"':
                state = _CDState.QUOTED_VALUE
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                state = _CDState.PARAM_VALUE
        elif state == _CDState.PARAM_VALUE:
            if ch is None or ch.isspace() or ch == ";":
                fields[key] = value
                state = _CDState.PARAM_START
            else:
                value += ch
        elif state == _CDState.QUOTED_VALUE:
            if ch is None:
                # unexpected end of string
                fields[key] = value
                break
            elif ch == '"':
                fields[key] = value
                state = _CDState.AFTER_QUOTE
            else:
                value += ch
        elif state == _CDState.AFTER_QUOTE:
            if ch is None:
                break
            elif ch == ";":
                state = _CDState.PARAM_START
            elif ch.isspace():
                pass
            else:
                pass  # garbage after closing quote, ignore

    return fields


def parse_search_condition(text: str) -> Tuple[str, List[str]]:
    """
    Parser for search conditions. Examples:
        fieldname=keyword
        fieldname=keyword1,keyword2
        fieldname="keyword"
        fieldname="keyword 1","keyword 2"
    :param text: Search condition text.
    :return: Tuple of fieldname and list of keywords.
    """

    state = _SCState.FIELD_START
    value = ""
    fieldname = ""
    keywords = []
    reader = CharReader(text or "")

    while True:
        ch = reader.getch()
        if state == _SCState.FIELD_START:
            if ch is None:
                break
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                value = ""
                state = _SCState.FIELD
        elif state == _SCState.FIELD:
            if ch is None:
                fieldname = value
                break
            elif ch == "=" or ch.isspace():
                reader.ungetch(ch)
                fieldname = value
                state = _SCState.AFTER_FIELD
            else:
                value += ch
        elif state == _SCState.AFTER_FIELD:
            if ch is None:
                break
            elif ch.isspace():
                pass
            elif ch == "=":
                state = _SCState.VALUE_START
            else:
                raise ValueError(f"Unexpected character found: '{ch}'")
        elif state == _SCState.VALUE_START:
            value = ""
            if ch is None:
                break
            elif ch.isspace():
                pass
            elif ch == '"':
                state = _SCState.QUOTED_VALUE
            elif ch == "\\":
                state = _SCState.VALUE
            else:
                reader.ungetch(ch)
                state = _SCState.VALUE
        elif state == _SCState.VALUE:
            if ch is None or ch == ",":
                value = value.rstrip()
                state = _SCState.AFTER_VALUE
            else:
                value += ch
        elif state == _SCState.QUOTED_VALUE:
            if ch is None or ch == '"':
                # unexpected end or closing quote
                state = _SCState.AFTER_VALUE
            elif ch == "\\":
                value += reader.getch() or ""
            else:
                value += ch
        elif state == _SCState.AFTER_VALUE:
            if value:
                keywords.append(value)
            if ch is None:
                break
            else:
                reader.ungetch(ch)
                state = _SCState.VALUE_START

    return fieldname, keywords
