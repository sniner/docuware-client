from __future__ import annotations

import os
import pathlib
import random
import re
from datetime import date, datetime
from typing import Any, Optional, Union

from docuware import errors

DATE_PATTERN = re.compile(r"/Date\((\d+)\)/")


def quote_value(s: str, chars: frozenset) -> str:
    """Idempotently escape special characters in a DocuWare search value.

    Already-escaped sequences (backslash followed by any character) are passed
    through unchanged, so calling this function on an already-escaped string is
    safe and produces the same result.

    :param s: The value string to escape.
    :param chars: Set of characters to escape with a backslash.
    :return: The escaped string.
    """
    if not chars:
        return s
    result = []
    i = 0
    while i < len(s):
        ch = s[i]
        if ch == "\\" and i + 1 < len(s):
            # Already-escaped sequence: pass both characters through unchanged
            result.append(ch)
            result.append(s[i + 1])
            i += 2
        elif ch in chars:
            result.append("\\")
            result.append(ch)
            i += 1
        else:
            result.append(ch)
            i += 1
    return "".join(result)


def safe_str(value: Any) -> str:
    """Generate a string whose value contains only printable characters.
    This means that control characters, among others, are removed."""
    return "".join(ch for ch in str(value) if ch.isprintable())


def datetime_from_string(
    value: Optional[str], auto_date: bool = False
) -> Union[date, datetime, None]:
    """
    NB: Dates earlier than 1970 and later than 2038 break the code, and not just
    for the document with the incorrect date entry, but also for all remaining
    documents in that search dialog. By returning None, we can easily identify
    those corrupted documents and inform the owner so they can be fixed. For
    example: 3023-01-01
    """
    if value:
        if m := DATE_PATTERN.match(str(value)):
            msec = int(m[1])
            if msec > 0:
                unix_timestamp = msec / 1000
                try:
                    dt = datetime.fromtimestamp(unix_timestamp)
                except (OverflowError, OSError, ValueError):
                    return None
                if auto_date:
                    if (
                        dt.hour == 0
                        and dt.minute == 0
                        and dt.second == 0
                        and dt.microsecond == 0
                    ):
                        return date(dt.year, dt.month, dt.day)
                return dt
            else:
                # DocuWare sometimes returns negative timestamps (pre-1970 dates); treat as missing
                return None
        raise errors.DataError(f"Value must be formatted like '/Date(...)/', found '{value}'")
    else:
        return None


def date_from_string(value: str) -> Optional[date]:
    """
    NB: Dates earlier than 1970 and later than 2038 break the code, and not just
    for the document with the incorrect date entry, but also for all remaining
    documents in that search dialog. By returning None, we can easily identify
    those corrupted documents and inform the owner so they can be fixed. For
    example: 3023-01-01
    """
    if value:
        if m := DATE_PATTERN.match(str(value)):
            msec = int(m[1])
            if msec > 0:
                unix_timestamp = msec / 1000
                try:
                    dt = date.fromtimestamp(unix_timestamp)
                except (OverflowError, OSError, ValueError):
                    dt = None
                return dt
            else:
                return None
        raise errors.DataError(f"Value must be formatted like '/Date(...)/', found '{value}'")
    else:
        return None


def datetime_to_string(value: datetime) -> str:
    return f"/Date({int(value.timestamp()) * 1000})/"


def date_to_string(value: date) -> str:
    return datetime_to_string(datetime(value.year, value.month, value.day))


def unique_filename(path: Union[str, pathlib.Path]) -> pathlib.Path:
    """
    Make a filename unique. If the file already exists, a "(1)" will be appended to the
    filename. If that file already exists, a "(2)" will be appended instead. And so on,
    until the filename is unique. There is a hard limit of 1000 checks, after that an
    InternalError exception will be raised.
    """
    path = pathlib.Path(path)
    stem = path.parent / path.stem
    suffix = path.suffix
    n = 0
    candidate = path
    while candidate.exists():
        n += 1
        if n > 1000:
            raise errors.InternalError(f"Unable to create file {path}: too many duplicates")
        candidate = pathlib.Path(f"{stem}({n}){suffix}")
    return candidate


def default_credentials_file() -> pathlib.Path:
    default_path = pathlib.Path(".credentials")
    if default_path.exists():
        return default_path
    conf_dir = os.environ.get("XDG_CONFIG_HOME")
    if conf_dir:
        return pathlib.Path(conf_dir) / "docuware-client" / default_path.name
    return pathlib.Path.home() / ".docuware-client.cred"


def write_binary_file(blob: bytes, path: Union[str, pathlib.Path]) -> pathlib.Path:
    path = unique_filename(path)
    with open(path, "wb") as f:
        f.write(blob)
    return path


def random_password(length: int = 16) -> str:
    return "".join(
        random.choices(
            "0123456789abcdefghijklmnopqrstuvwxyzABCDEFGHIJKLMNOPQRSTUVWXYZ.,;:-_/+=",
            k=length,
        )
    )
