from __future__ import annotations
import logging
from typing import Generator, List, Optional, TypeVar, Union

from docuware import cidict, conn, structs, types, users, filecabinet

log = logging.getLogger(__name__)

T = TypeVar("T")


class Organization(types.OrganizationP):
    def __init__(self, config: dict, client: types.DocuwareClientP):
        self.client = client
        self.name = config.get("Name")
        self.id = config.get("Id")
        self.endpoints = structs.Endpoints(config)
        self._info = None
        self._dialogs = None

    @property
    def conn(self) -> conn.Connection:
        return self.client.conn

    @property
    def file_cabinets(self) -> Generator[types.FileCabinetP, None, None]:
        result = self.client.conn.get_json(self.endpoints["filecabinets"])
        return (filecabinet.FileCabinet(fc, self) for fc in result.get("FileCabinet", []))

    def file_cabinet(self, key: str, default: Union[T, None, types.Nothing] = types.NOTHING) -> Optional[types.FileCabinetP]:
        return structs.first_item_by_id_or_name(self.file_cabinets, key, default=default)

    @property
    def my_tasks(self):
        # Sorry, but couldn't figure out how to get "My tasks" list.
        raise NotImplementedError
        # result = self.client.conn.get_json(self.endpoints["workflowRequests"])
        # return tasks.MyTasks(result, self)

    @property
    def dialogs(self) -> List[types.DialogP]:
        # It is unclear whether the dialogs here differ from those of FileCabinet or not.
        if self._dialogs is None:
            fc_by_id = {fc.id: fc for fc in self.file_cabinets}
            result = self.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                Dialog.from_config(dlg, fc_by_id[dlg.get("FileCabinetId")]) for dlg in result.get("Dialog", [])
                if dlg.get("$type") == "DialogInfo" and dlg.get("FileCabinetId") in fc_by_id
            ]
        return self._dialogs

    def dialog(self, key: str, default: Union[types.DialogP, None, types.Nothing] = types.NOTHING) -> Optional[types.DialogP]:
        return structs.first_item_by_id_or_name(self.dialogs, key, default=default)

    @property
    def info(self) -> cidict.CaseInsensitiveDict:
        if self._info is None:
            result = self.client.conn.get_json(self.endpoints["self"])
            self.endpoints = structs.Endpoints(result)
            self._info = cidict.CaseInsensitiveDict(result.get("AdditionalInfo", {}))
            # Remove empty lines
            self._info["CompanyNames"] = [line for line in self._info["CompanyNames"] if line] or [self.name]
            self._info["AddressLines"] = [line for line in self._info["AddressLines"] if line]
        return self._info

    @property
    def users(self) -> users.Users:
        return users.Users(self)

    @property
    def groups(self) -> users.Groups:
        return users.Groups(self)

    def __str__(self):
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"

# vim: set et sw=4 ts=4:
