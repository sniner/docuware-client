from __future__ import annotations
import json

from docuware import cidict


class CIJSONEncoder(json.JSONEncoder):
    def default(self, obj: object):
        if isinstance(obj, cidict.CaseInsensitiveDict):
            return dict(obj.items())
        else:
            return super().default(obj)


def case_insensitive_hook(obj: object) -> object:
    return cidict.CaseInsensitiveDict(obj)


def print_json(data):
    print(dumps(data, indent=4))


def load(*args, **kwargs):
    return json.load(*args, **kwargs, object_hook=case_insensitive_hook)


def loads(*args, **kwargs):
    return json.loads(*args, **kwargs, object_hook=case_insensitive_hook)


def dump(*args, **kwargs):
    return json.dump(*args, **kwargs, cls=CIJSONEncoder)


def dumps(*args, **kwargs):
    return json.dumps(*args, **kwargs, cls=CIJSONEncoder)

# vim: set et sw=4 ts=4:
