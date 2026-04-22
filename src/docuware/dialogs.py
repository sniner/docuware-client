from __future__ import annotations

import enum
import logging
import re
from datetime import date
from typing import Any, Dict, Iterator, List, Optional, Sequence, Tuple, Union

from docuware import document, errors, fields, parser, structs, types, utils

log = logging.getLogger(__name__)

class Operation(enum.Enum):
    """Logical operator that combines multiple search conditions."""

    AND = "And"
    """All conditions must match (default)."""

    OR = "Or"
    """At least one condition must match."""


class QuoteMode(enum.Enum):
    """Controls automatic escaping of DocuWare search metacharacters in field values.

    When using the dict form of :meth:`SearchDialog.search`, field values may
    contain characters that DocuWare interprets as query operators (e.g. ``(``,
    ``)``, ``*``, ``?``).  ``QuoteMode`` selects which characters are
    automatically escaped with a backslash before the query is sent to the API.

    The escaping is **idempotent**: values that already contain backslash-escaped
    sequences (e.g. ``\\(`` from an earlier workaround) are left unchanged.
    """

    NONE = "none"
    """No automatic escaping."""

    PARTIAL = "partial"
    """Escape ``(`` and ``)`` only.  Wildcard characters ``*`` and ``?`` are
    preserved so they can still be used for pattern matching.  This is the
    default."""

    ALL = "all"
    """Escape ``(``, ``)``, ``*``, and ``?``.  Use this when wildcard
    characters must be treated as literals."""


_QUOTE_CHARS: Dict[QuoteMode, frozenset] = {
    QuoteMode.NONE: frozenset(),
    QuoteMode.PARTIAL: frozenset("()"),
    QuoteMode.ALL: frozenset("()?*"),
}


class Dialog:
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        self.file_cabinet = file_cabinet
        self.client = file_cabinet.organization.client
        # DisplayName is optional in the XSD; fall back to Id so name is never empty
        self.name = config.get("DisplayName") or config.get("Id", "")
        self.type = config.get("Type")
        self.id = config.get("Id", "")
        self.is_default: bool = bool(config.get("IsDefault", False))
        self.associated_dialog_id: str = config.get("AssignedDialogId", "")
        self.endpoints = structs.Endpoints(config)
        self._fields: Optional[Dict[str, types.SearchFieldP]] = None

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
        elif dlg_type == "InfoDialog":
            return InfoDialog(config, file_cabinet)
        elif dlg_type == "ResultTree":
            return ResultTree(config, file_cabinet)
        return Dialog(config, file_cabinet)

    def _load(self) -> None:
        """Fetch the full dialog config and populate fields. Results are cached."""
        if self._fields is not None:
            return
        config = self.client.conn.get_json(self.endpoints["self"])
        self._fields = {
            f.id: f for f in [SearchField(fld, self) for fld in config.get("Fields", [])]
        }
        self._on_loaded(config)

    def _on_loaded(self, config: Dict) -> None:
        """Hook called after _load() populates fields. Override in subclasses."""

    @property
    def associated_dialog(self) -> Optional[types.DialogP]:
        if not self.associated_dialog_id:
            return None
        return self.file_cabinet.dialog(self.associated_dialog_id)

    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        return {}

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class StoreDialog(Dialog):
    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        self._load()
        return self._fields or {}

    @property
    def required_fields(self) -> Dict[str, types.SearchFieldP]:
        """Fields with ``NotEmpty=True`` — must be provided when archiving/storing.

        Note: the server is the authoritative source for validation (including
        dialog-level mandatory rules and conditional logic added in 7.1+).
        This helper reflects the field-level ``NotEmpty`` flag only and is
        intended as a best-effort client-side hint.
        """
        return {fid: f for fid, f in self.fields.items() if getattr(f, "not_empty", False)}

    def validate_fields(self, values: Dict[str, Any]) -> List[str]:
        """Return a list of missing required field ids/labels given ``values``.

        Only checks the field-level ``NotEmpty`` flag. Empty strings and ``None``
        count as missing. Use this as a client-side pre-flight before an archive
        call to avoid a round-trip that the server would otherwise reject.
        """
        missing: List[str] = []
        # Match by id (DBFieldName) or by label (DlgLabel), case-insensitive
        provided = {str(k).casefold() for k, v in values.items() if v not in (None, "")}
        for fid, f in self.required_fields.items():
            if fid.casefold() in provided:
                continue
            if getattr(f, "name", "").casefold() in provided:
                continue
            missing.append(fid)
        return missing


class ResultListDialog(Dialog):
    pass


class InfoDialog(Dialog):
    pass


class ResultTree(Dialog):
    pass


class TaskListDialog(Dialog):
    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        self._load()
        return self._fields or {}


class SearchDialog(Dialog):
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        super().__init__(config, file_cabinet)
        self._query: Optional[SearchQuery] = None

    def _on_loaded(self, config: Dict) -> None:
        query_config = config.get("Query", {})
        q_endpoints = structs.Endpoints(query_config)
        if "dialogExpressionLink" not in q_endpoints:
            # WTF: This endpoint is needed but not included in the response, instead there is
            # a 'dialogExpression' endpoint that can be forged to:
            #     /DocuWare/Platform/FileCabinets/<FC_ID>/Query/DialogExpressionLink?dialogId=<DLG_ID>
            # Looks like a bug in DocuWare's API.
            if "dialogExpression" in q_endpoints:
                query_config.setdefault("Links", []).append(
                    {
                        "rel": "dialogExpressionLink",
                        "href": re.sub(
                            r"/DialogExpression\b",
                            "/DialogExpressionLink",
                            q_endpoints["dialogExpression"],
                            flags=re.IGNORECASE,
                        ),
                    }
                )
            else:
                raise errors.InternalError("Endpoint 'dialogExpression' missing")
        # NB: SearchQuery depends on self.fields being populated first
        self._query = SearchQuery(query_config, self)

    @property
    def fields(self) -> Dict[str, types.SearchFieldP]:
        self._load()
        return self._fields or {}

    def search(
        self,
        conditions: types.SearchConditionsT,
        operation: Optional[Union[str, Operation]] = None,
        quote: QuoteMode = QuoteMode.PARTIAL,
    ) -> SearchResult:
        self._load()
        assert self._query is not None
        return self._query.search(conditions=conditions, operation=operation, quote=quote)


class SearchField:
    def __init__(self, config: Dict, dialog: Dialog):
        self.dialog = dialog
        self.id: str = config.get("DBFieldName", "")
        self.name: str = config.get("DlgLabel", self.id)
        self.length: int = config.get("Length", -1)
        self.type: Optional[str] = config.get("DWFieldType")
        # DocuWare marks required store-dialog fields via the NotEmpty attribute:
        # "Determines whether the field can be empty, considering NotEmpty in Field
        # settings and Field may be empty right." (see DialogFieldBase in the SDK).
        # Note: this reflects field-level settings, not the dialog-level mandatory
        # rules introduced in 7.1 — those are evaluated server-side on store/transfer.
        self.not_empty: bool = bool(config.get("NotEmpty", False))
        self.read_only: bool = bool(config.get("ReadOnly", False))
        self.locked: bool = bool(config.get("Locked", False))
        self.mask: Optional[str] = config.get("Mask") or None
        self.mask_error_text: Optional[str] = config.get("MaskErrorText") or None
        self.select_list_only: bool = bool(config.get("SelectListOnly", False))
        self.endpoints = structs.Endpoints(config)

    @property
    def required(self) -> bool:
        """Alias for ``not_empty``. True if the field must be filled on store/transfer."""
        return self.not_empty

    def values(self) -> List[Any]:
        if "simpleSelectList" in self.endpoints:
            result = self.dialog.client.conn.get_json(self.endpoints["simpleSelectList"])
            return result.get("Value", [])
        return []

    def __str__(self) -> str:
        flags = []
        if self.not_empty:
            flags.append("required")
        if self.read_only:
            flags.append("readonly")
        suffix = f" ({', '.join(flags)})" if flags else ""
        if self.length > 0:
            return f"Field '{self.name}' [{self.id}, {self.type}({self.length})]{suffix}"
        else:
            return f"Field '{self.name}' [{self.id}, {self.type}]{suffix}"


class ConditionParser:
    def __init__(self, dialog: SearchDialog):
        self.fields_by_name: Dict[str, types.SearchFieldP] = {}
        self.fields_by_id: Dict[str, types.SearchFieldP] = {}
        for field in dialog.fields.values():
            self.fields_by_name[field.name.casefold()] = field
            self.fields_by_id[field.id.casefold()] = field

    @staticmethod
    def convert_field_value(value: Any, quote: QuoteMode = QuoteMode.NONE) -> str:
        if value is None:
            return "EMPTY()"
        if isinstance(value, date):
            return value.isoformat()
        return utils.quote_value(str(value), _QUOTE_CHARS[quote])

    def field_by_name(self, name: str) -> types.SearchFieldP:
        iname = name.casefold()
        if iname in self.fields_by_id:
            field = self.fields_by_id[iname]
        elif iname in self.fields_by_name:
            field = self.fields_by_name[iname]
        else:
            raise errors.SearchConditionError(f"Unknown field: {name}")
        return field

    def _term(
        self, name: str, value: Union[str, Sequence[Optional[str]]], quote: QuoteMode = QuoteMode.NONE
    ) -> Tuple[str, List[Optional[str]]]:
        field = self.field_by_name(name)
        converted: List[Optional[str]]
        if isinstance(value, list):
            if len(value) == 2 and (value[0] is None or value[1] is None):
                # Open-ended range: keep None as None so JSON serialises it
                # as null (DocuWare expects null for open range bounds).
                converted = [
                    self.convert_field_value(v, quote) if v is not None else None
                    for v in value
                ]
            else:
                converted = [self.convert_field_value(v, quote) for v in value]
        else:
            converted = [self.convert_field_value(value, quote)]
        return field.id, converted

    def parse_list(
        self, conditions: Union[List[str], Tuple[str]]
    ) -> List[Tuple[str, List[Optional[str]]]]:
        return [self._term(*parser.parse_search_condition(c)) for c in conditions]

    def parse_dict(
        self, conditions: Dict[str, Union[str, List[Optional[str]]]], quote: QuoteMode = QuoteMode.PARTIAL
    ) -> List[Tuple[str, List[Optional[str]]]]:
        return [self._term(k, v, quote) for k, v in conditions.items()]

    def parse(
        self, conditions: types.SearchConditionsT, quote: QuoteMode = QuoteMode.PARTIAL
    ) -> List[Tuple[str, List[Optional[str]]]]:
        if isinstance(conditions, str):
            return self.parse_list([conditions])
        elif isinstance(conditions, (list, tuple)):
            return self.parse_list(conditions)
        else:
            return self.parse_dict(conditions, quote)


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

    @property
    def conn(self) -> types.ConnectionP:
        return self.dialog.client.conn

    def search(
        self,
        conditions: types.SearchConditionsT,
        operation: Optional[Union[str, Operation]] = None,
        sort_field: Optional[str] = None,
        sort_order: Optional[str] = None,
        quote: QuoteMode = QuoteMode.PARTIAL,
    ) -> SearchResult:
        terms = self.cond_parser.parse(conditions, quote=quote)
        query = {"fields": ",".join([t[0] for t in terms])}
        if sort_field:
            query["sortOrder"] = (
                f"{self.cond_parser.field_by_name(sort_field).id} {sort_order if sort_order else 'Asc'}"
            )
        path = self.conn.make_path(self.endpoints["dialogExpressionLink"], query=query)
        op = operation.value if isinstance(operation, Operation) else (operation or Operation.AND.value)
        data = {
            "Condition": [{"DBName": k, "Value": v} for k, v in terms],
            "Operation": op,
        }
        result_url = self.conn.post_text(path, json=data).split("\n", 1)[0]
        result = self.conn.get_json(result_url)
        return SearchResult(result, self)

    def __str__(self) -> str:
        return f"{self.__class__.__name__} [{self.dialog.id}]"


class SearchResult:
    """Paginated search result iterator.

    Note: SearchResult is a single-use iterator. Once exhausted it cannot be
    restarted. This is intentional: the result pages are fetched lazily from
    the server and re-iteration would require a new search request.
    """

    def __init__(self, config: Dict, query: SearchQuery):
        self.query = query
        self.count = config.get("Count", {}).get("Value", 0)
        self.endpoints = structs.Endpoints(config)
        self.items = self._items(config)

    def _items(self, config: Dict) -> Iterator[SearchResultItem]:
        return (SearchResultItem(item, self) for item in config.get("Items", []))

    def __iter__(self) -> Iterator[SearchResultItem]:
        return self

    def __next__(self) -> SearchResultItem:
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
