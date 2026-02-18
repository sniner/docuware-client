from __future__ import annotations

import logging
from typing import Any, Dict, List, Literal, Optional, Union, overload

from docuware import dialogs, document, structs, types

log = logging.getLogger(__name__)


class FileCabinet:
    def __init__(self, config: Dict, organization: types.OrganizationP):
        self.organization = organization
        self.name = config.get("Name", "")
        self.id = config.get("Id", "")
        self.endpoints = structs.Endpoints(config)
        self._dialogs: Optional[List[types.DialogP]] = None

    @property
    def dialogs(self) -> List[types.DialogP]:
        if self._dialogs is None:
            result = self.organization.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                dialogs.Dialog.from_config(dlg, self)
                for dlg in result.get("Dialog", [])
                if dlg.get("$type") == "DialogInfo" and ("_" not in dlg.get("Id"))
                # and (dlg.get("IsDefault") or dlg.get("IsForMobile"))
            ]
        return self._dialogs or []

    @overload
    def dialog(self, key: str, *, required: Literal[True]) -> types.DialogP: ...

    @overload
    def dialog(
        self, key: str, *, required: Literal[False] = False
    ) -> Optional[types.DialogP]: ...

    def dialog(self, key: str, *, required: bool = False) -> Optional[types.DialogP]:
        return structs.first_item_by_id_or_name(self.dialogs, key, required=required)

    @overload
    @overload
    def search_dialog(
        self, key: Optional[str] = None, *, required: Literal[True]
    ) -> types.SearchDialogP: ...

    @overload
    def search_dialog(
        self, key: Optional[str] = None, *, required: Literal[False] = False
    ) -> Optional[types.SearchDialogP]: ...

    def search_dialog(
        self, key: Optional[str] = None, *, required: bool = False
    ) -> Optional[types.SearchDialogP]:
        # TODO: Is there a default search dialog?
        search_dlgs = (dlg for dlg in self.dialogs if isinstance(dlg, dialogs.SearchDialog))
        if key:
            return structs.first_item_by_id_or_name(
                search_dlgs,
                key,
                required=required,
            )
        else:
            return structs.first_item_by_class(
                search_dlgs, dialogs.SearchDialog, required=required
            )

    def create_document(
        self,
        fields: Optional[Dict[str, Any]] = None,
    ) -> document.Document:
        endpoint = self.endpoints["documents"]

        # Create data record (no file)
        json_fields = []
        if fields:
            for key, value in fields.items():
                type_name = "String"
                if isinstance(value, bool):
                    type_name = "Bool"
                elif isinstance(value, int):
                    type_name = "Int"
                elif isinstance(value, float):
                    type_name = "Decimal"
                elif hasattr(value, "isoformat"):  # datetime or date
                    type_name = "DateTime"
                    value = value.isoformat()

                json_fields.append(
                    {"FieldName": key, "Item": value, "ItemElementName": type_name}
                )
        data = {"Fields": json_fields}

        resp = self.organization.client.conn.post_json(endpoint, json=data)
        # Response should comprise the created document
        return document.Document(resp, self)

    def get_document(self, doc_id: Union[str, int]) -> document.Document:
        url = f"{self.endpoints['documents']}/{doc_id}"
        data = self.organization.client.conn.get_json(url)
        return document.Document(data, self)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"
