from __future__ import annotations
import logging
import re
from datetime import datetime, date
from typing import Any, Iterator, Mapping, Union, List, Optional, Tuple, Dict

from docuware import conn, errors, parser, structs, types, utils, document, fields

log = logging.getLogger(__name__)

AND = "And"
OR = "Or"


class Dialog(types.DialogP):
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        self.file_cabinet = file_cabinet
        self.client = file_cabinet.organization.client
        self.name = config.get("DisplayName", "")
        self.type = config.get("Type")
        self.id = config.get("Id", "")
        self.endpoints = structs.Endpoints(config)

    @staticmethod
    def from_config(config: Dict, file_cabinet: types.FileCabinetP) -> Dialog:
        dlg_type = config.get("Type")
        if dlg_type == "Search":
            return SearchDialog(config, file_cabinet)
        elif dlg_type == "Store":
            return StoreDialog(config, file_cabinet)
        elif dlg_type == "ResultList":
            return ResultListDialog(config, file_cabinet)
        elif dlg_type == "TaskList":
            return TaskListDialog(config, file_cabinet)
        return Dialog(config, file_cabinet)

    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        return {}

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class StoreDialog(Dialog):
    pass


class ResultListDialog(Dialog):
    pass


class TaskListDialog(Dialog):
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        super().__init__(config, file_cabinet)
        self._fields: Optional[Dict[str, types.SearchFieldP]] = None

    def _load(self):
        if self._fields is None:
            config = self.client.conn.get_json(self.endpoints["self"])
            self._fields = {
                f.id: f for f in
                [SearchField(fld, self) for fld in config.get("Fields", [])]
            }

    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        self._load()
        return self._fields or {}


class SearchDialog(Dialog):
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        super().__init__(config, file_cabinet)
        self._fields: Optional[Dict[str, types.SearchFieldP]] = None

    def _load(self):
        if self._fields is None:
            config = self.client.conn.get_json(self.endpoints["self"])
            self._fields = {
                f.id: f for f in
                [SearchField(fld, self) for fld in config.get("Fields", [])]
            }
            # NB: SearchQuery depends on self.fields
            self._query = SearchQuery(config.get("Query", {}), self)

    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        self._load()
        return self._fields or {}

    def search(self, conditions: types.SearchConditionsT, operation: Optional[str] = None) -> SearchResult:
        self._load()
        return self._query.search(conditions=conditions, operation=operation)


class SearchField(types.SearchFieldP):
    def __init__(self, config: Dict, dialog: Dialog):
        self.dialog = dialog
        self.id: str = config.get("DBFieldName", "")
        self.name: str = config.get("DlgLabel", self.id)
        self.length: int = config.get("Length", -1)
        self.type: Optional[str] = config.get("DWFieldType")
        self.endpoints = structs.Endpoints(config)

    def values(self) -> List[Any]:
        if "simpleSelectList" in self.endpoints:
            result = self.dialog.client.conn.get_json(self.endpoints["simpleSelectList"])
            return result.get("Value", [])
        return []

    def __str__(self) -> str:
        if self.length > 0:
            return f"Field '{self.name}' [{self.id}, {self.type}({self.length})]"
        else:
            return f"Field '{self.name}' [{self.id}, {self.type}]"


class ConditionParser:
    def __init__(self, dialog: SearchDialog):
        self.fields_by_name: Dict[str, types.SearchFieldP] = {}
        self.fields_by_id: Dict[str, types.SearchFieldP] = {}
        for field in dialog.fields.values():
            self.fields_by_name[field.name.casefold()] = field
            self.fields_by_id[field.id.casefold()] = field

    @staticmethod
    def convert_field_value(value: Any) -> str:
        if value is None:
            return "*"
        if isinstance(value, date):
            value = datetime(value.year, value.month, value.day)
        if isinstance(value, datetime):
            value = utils.datetime_to_string(value)
        return str(value)

    def field_by_name(self, name: str) -> types.SearchFieldP:
        iname = name.casefold()
        if iname in self.fields_by_id:
            field = self.fields_by_id[iname]
        elif iname in self.fields_by_name:
            field = self.fields_by_name[iname]
        else:
            raise errors.SearchConditionError(f"Unknown field: {name}")
        return field

    def _term(self, name: str, value: Union[str, List[str]]) -> Tuple[str, List[str]]:
        field = self.field_by_name(name)
        if isinstance(value, str):
            value = [value]
        else:
            try:
                value = [self.convert_field_value(i) for i in value]
            except TypeError:
                value = [str(value)]
        return field.id, value

    def parse_list(self, conditions: Union[List[str], Tuple[str]]) -> List[Tuple[str, List[str]]]:
        return [self._term(*parser.parse_search_condition(c)) for c in conditions]

    def parse_dict(self, conditions: Dict[str, Union[str, List[str]]]) -> List[Tuple[str, List[str]]]:
        return [self._term(k, v) for k, v in conditions.items()]

    def parse(self, conditions: types.SearchConditionsT) -> List[Tuple[str, List[str]]]:
        if isinstance(conditions, str):
            return self.parse_list([conditions])
        elif isinstance(conditions, (list, tuple)):
            return self.parse_list(conditions)
        else:
            return self.parse_dict(conditions)


class SearchQuery:
    def __init__(self, config: Dict, dialog: SearchDialog):
        self.dialog = dialog
        self.force_refresh = config.get("ForceRefresh", False)
        self.exclude_system_fields = config.get("ExcludeSystemFields", False)
        self.include_suggestions = config.get("IncludeSuggestions", False)
        self.expression = config.get("Expression", "")
        self.endpoints = structs.Endpoints(config)
        # self.fields = {f:dialog.fields.get(f) for f in config.get("Fields", [])}
        self.cond_parser = ConditionParser(self.dialog)
        if "dialogExpressionLink" not in self.endpoints:
            # WTF: This endpoint is needed but not included in the response, instead there is
            # a 'dialogExpression' endpoint that can be forged to:
            #     /DocuWare/Platform/FileCabinets/<FC_ID>/Query/DialogExpressionLink?dialogId=<DLG_ID>
            # Looks like a bug in DocuWare's API.
            if "dialogExpression" in self.endpoints:
                self.endpoints["dialogExpressionLink"] = re.sub(r"/DialogExpression\b",
                                                                "/DialogExpressionLink",
                                                                self.endpoints["dialogExpression"],
                                                                flags=re.IGNORECASE)
            else:
                raise errors.InternalError("Endpoint 'dialogExpression' missing")

    @property
    def conn(self) -> types.ConnectionP:
        return self.dialog.client.conn

    def search(
        self,
        conditions: types.SearchConditionsT,
        operation: Optional[str] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None
    ) -> SearchResult:
        terms = self.cond_parser.parse(conditions)
        query = {"fields": ",".join([t[0] for t in terms])}
        if sort_field:
            query[
                "sortOrder"] = f"{self.cond_parser.field_by_name(sort_field).id} {sort_order if sort_order else 'Asc'}"
        path = self.conn.make_path(self.endpoints["dialogExpressionLink"], query=query)
        data = {
            "Condition": [{"DBName": k, "Value": v} for k, v in terms],
            "Operation": operation or AND,
        }
        result_url = self.conn.post_text(path, json=data).split("\n", 1)[0]
        result = self.conn.get_json(result_url)
        return SearchResult(result, self)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [{self.dialog.id}]"


class SearchResult:
    def __init__(self, config: Dict, query: SearchQuery):
        self.query = query
        self.count = config.get("Count", {}).get("Value", 0)
        self.endpoints = structs.Endpoints(config)
        self.items = self._items(config)

    def _items(self, config: Dict) -> Iterator[SearchResultItem]:
        return (SearchResultItem(item, self) for item in config.get("Items", []))

    def __iter__(self):
        return self

    def __next__(self):
        while (item := next(self.items, None)) is None:
            if "next" in self.endpoints:
                result = self.query.dialog.client.conn.get_json(self.endpoints["next"])
                self.endpoints = structs.Endpoints(result)
                self.items = self._items(result)
            else:
                raise StopIteration
        return item

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [{self.count}]"


class SearchResultItem:
    def __init__(self, config: Dict, result: SearchResult):
        self.result = result
        self.fields = [fields.FieldValue.from_config(f) for f in config.get("Fields", [])]
        self.content_type = config.get("ContentType")
        self.title = config.get("Title")
        self.file_cabinet_id = config.get("FileCabinetId")
        self.endpoints = structs.Endpoints(config)
        self._document = None

    def thumbnail(self) -> Tuple[bytes, str, str]:
        dw = self.result.query.dialog.client
        return dw.conn.get_bytes(self.endpoints["thumbnail"])

    @property
    def document(self) -> document.Document:
        if self._document is None:
            dw = self.result.query.dialog.client
            config = dw.conn.get_json(self.endpoints["self"])
            self._document = document.Document(config, self.result.query.dialog.file_cabinet)
        return self._document

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.title}' [{self.content_type}]"

# vim: set et sw=4 ts=4:
