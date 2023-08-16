import pathlib
import re

from datetime import datetime, date
from typing import Union

from docuware import errors, cidict


DATE_PATTERN = re.compile(r"/Date\((\d+)\)/")


def datetime_from_string(value:str, auto_date:bool=False) -> Union[date,datetime,None]:
    """
    Dates earlier than 1970 and later than 2038 are breaks the code
    and not just for the document which has inccorect date entry but also
    all remaining documents in that search dialog. By returning None we
    easly identify those currepted documents and inform the owner so they
    can be fixed.
    For example: 3023-01-01
    """    
    if value:
        if m := DATE_PATTERN.match(str(value)):
            msec = int(m[1])
            if msec>0:
                unix_timestamp = msec/1000
                try:
                    dt = datetime.fromtimestamp(unix_timestamp)
                except:
                    dt = None
                if auto_date:
                    if dt.hour==0 and dt.minute==0 and dt.second==0 and dt.microsecond==0:
                        return date(dt.year, dt.month, dt.day)
                return dt
            else:
                # WTF: negative timestamps ... ?!
                return None
        raise errors.DataError(f"Value must be formatted like '/Date(...)/', found '{value}'")
    else:
        return None


def date_from_string(value:str) -> Union[date,None]:
    """
    Dates earlier than 1970 and later than 2038 are breaks the code
    and not just for the document which has inccorect date entry but also
    all remaining documents in that search dialog. By returning None we
    easly identify those currepted documents and inform the owner so they
    can be fixed.
    For example: 3023-01-01
    """
    if value:
        if m := DATE_PATTERN.match(str(value)):
            msec = int(m[1])
            if msec>0:
                unix_timestamp = msec/1000
                try:
                    dt = date.fromtimestamp(unix_timestamp)
                except:
                    dt = None
                return dt
            else:
                return None
        raise errors.DataError(f"Value must be formatted like '/Date(...)/', found '{value}'")
    else:
        return None


def datetime_to_string(value:datetime) -> str:
    return f"/Date({int(value.timestamp())*1000})/"


def date_to_string(value:date) -> str:
    return datetime_to_string(datetime(value.year, value.month, value.day))


def unique_filename(path:Union[str,pathlib.Path]) -> pathlib.Path:
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


def write_binary_file(blob:bytes, path:Union[str,pathlib.Path]):
    path = unique_filename(path)
    with open(path, "wb") as f:
        f.write(blob)


# vim: set et sw=4 ts=4: