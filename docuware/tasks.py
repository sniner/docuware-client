from __future__ import annotations
import logging

from docuware import conn, structs, types, utils, organization

log = logging.getLogger(__name__)


class MyTasks(types.MyTasksP):
    """Not working!"""

    def __init__(self, config: dict, organization: types.OrganizationP):
        self.organization = organization
        self.endpoints = structs.Endpoints(config)
        self._tasks = None
        self.count = 0
        self.timestamp = None
        self.refresh()

    def refresh(self):
        result = self.organization.client.conn.get_json(self.endpoints["myTasks"])
        self._tasks = iter(result.get("Task", []))
        self.count = result.get("Count", 0)
        self.timestamp = utils.datetime_from_string(result.get("TimeStamp"))

    def __iter__(self):
        return self

    def __next__(self):
        if self._tasks:
            return next(self._tasks)
        else:
            raise StopIteration

# vim: set et sw=4 ts=4:
