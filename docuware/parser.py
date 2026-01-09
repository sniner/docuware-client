from __future__ import annotations
import collections
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

    def ungetch(self, char: Optional[str]):
        if char is not None:
            self._unget_buffer.append(char)

    def peekch(self) -> Optional[str]:
        ch = self.getch()
        self.ungetch(ch)
        return ch

    def __repr__(self) -> str:
        return f"CharReader({repr(self.text)})"


def parse_content_disposition(text: str, case_insensitive: bool = True) -> Union[Dict[str, str], cidict.CaseInsensitiveDict]:
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

    state = 0
    key = ""
    value = ""
    reader = CharReader(text)

    while True:
        ch = reader.getch()
        # print(state, ch)
        if state == 0:  # type identifier
            if ch is None:
                break
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                value = ""
                state = 1
        elif state == 1:
            if ch == ";":
                fields["type"] = value.rstrip()
                state = 10
            elif ch is None:
                fields["type"] = value.rstrip()
                break
            else:
                value += ch
        elif state == 10:  # key/value pair
            if ch is None:
                break
            if ch.isspace() or ch == ";":
                pass
            elif ch.isalnum():
                reader.ungetch(ch)
                key = ""
                value = ""
                state = 11
            else:
                raise ValueError
        elif state == 11:  # key of key/value pair
            if ch is None or ch == "=":
                key = key.rstrip()
                state = 20
            elif ch.isalnum():
                key += ch
            else:
                raise ValueError
        elif state == 20:  # value of key/value pair
            if ch is None or ch == ";":
                fields[key] = value
                state = 10
            elif ch == '"':
                state = 25
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                state = 21
        elif state == 21:  # plain value
            if ch is None or ch.isspace() or ch == ";":
                fields[key] = value
                state = 10
            else:
                value += ch
        elif state == 25:  # value in quotation marks
            if ch is None:
                # unexpected, but ...
                fields[key] = value
                break
            elif ch == '"':
                fields[key] = value
                state = 26
            else:
                value += ch
        elif state == 26:  # expecting semicolon
            if ch is None:
                break
            elif ch == ";":
                state = 10
            elif ch.isspace():
                pass
            else:
                raise ValueError

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

    state = 0
    value = ""
    fieldname = ""
    keywords = []
    reader = CharReader(text or "")

    while True:
        ch = reader.getch()
        # print(state, ch)
        if state == 0:  # before fieldname
            if ch is None:
                break
            elif ch.isspace():
                pass
            else:
                reader.ungetch(ch)
                value = ""
                state = 1
        elif state == 1:  # fieldname
            if ch is None:
                fieldname = value
                break
            elif ch == "=" or ch.isspace():
                reader.ungetch(ch)
                fieldname = value
                state = 2
            else:
                value += ch
        elif state == 2:  # after fieldname
            if ch is None:
                break
            elif ch.isspace():
                pass
            elif ch == "=":
                state = 10
            else:
                raise ValueError(f"Unexpected character found: '{ch}'")
        elif state == 10:  # before keyword
            value = ""
            if ch is None:
                break
            elif ch.isspace():
                pass
            elif ch == "\"":
                state = 20
            elif ch == "\\":
                state = 11
            else:
                reader.ungetch(ch)
                state = 11
        elif state == 11:  # keyword
            if ch is None or ch == ",":
                value = value.rstrip()
                state = 30
            else:
                value += ch
        elif state == 20:  # "keyword"
            if ch is None or ch == "\"":
                # unexpected end
                state = 30
            elif ch == "\\":
                value += reader.getch() or ""
            else:
                value += ch
        elif state == 30:  # after keyword
            if value:
                keywords.append(value)
            if ch is None:
                break
            else:
                reader.ungetch(ch)
                state = 10

    return fieldname, keywords

# vim: set et sw=4 ts=4:
