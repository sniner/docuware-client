from __future__ import annotations

import json
from typing import IO, Any

from docuware import cidict


class CIJSONEncoder(json.JSONEncoder):
    def default(self, o: object) -> Any:
        if isinstance(o, cidict.CaseInsensitiveDict):
            return dict(o.items())
        else:
            return super().default(o)


def case_insensitive_hook(obj: object) -> object:
    return cidict.CaseInsensitiveDict(obj)


def print_json(data: Any) -> None:
    print(dumps(data, indent=4))


def load(fp: IO[str], **kwargs: Any) -> Any:
    return json.load(fp, **kwargs, object_hook=case_insensitive_hook)


def loads(s: str, **kwargs: Any) -> Any:
    return json.loads(s, **kwargs, object_hook=case_insensitive_hook)


def dump(obj: Any, fp: IO[str], **kwargs: Any) -> None:
    json.dump(obj, fp, **kwargs, cls=CIJSONEncoder)


def dumps(obj: Any, **kwargs: Any) -> str:
    return json.dumps(obj, **kwargs, cls=CIJSONEncoder)
