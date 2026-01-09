from __future__ import annotations
import logging
from typing import Any, Dict, Type

from docuware import cidict, errors, types, utils

log = logging.getLogger(__name__)

FieldValueConfigT = Dict[str, Any]

class FieldValue(types.FieldValueP):
    TYPE_TABLE: cidict.CaseInsensitiveDict[Type[FieldValue]] = cidict.CaseInsensitiveDict()

    def __init__(self, config: FieldValueConfigT):
        self.name = config.get("FieldLabel", "")
        self.id = config.get("FieldName", "")
        self.content_type = config.get("ItemElementName")
        self.read_only = config.get("ReadOnly", True)
        self.internal = config.get("SystemField", False)
        self.value = config.get("Item")

    @staticmethod
    def from_config(config: FieldValueConfigT) -> FieldValue:
        content_type = config.get("ItemElementName")
        cls = FieldValue.TYPE_TABLE.get(content_type or "?")
        return cls(config) if cls else FieldValue(config)

    def __str__(self) -> str:
        return f"Value '{self.name}' [{self.id}, {self.content_type}] = '{self.value}'"


class StringFieldValue(FieldValue):
    def __init__(self, config: FieldValueConfigT):
        super().__init__(config)
        self.value = str(self.value) if self.value else None

    def __str__(self) -> str:
        return f"Text '{self.name}' [{self.id}] = '{self.value}'"


class KeywordsFieldValue(FieldValue):
    def __init__(self, config: FieldValueConfigT):
        super().__init__(config)
        values = config.get("Item", {}).get("Keyword", [])
        self.value = values if values else None

    def __str__(self) -> str:
        return f"Keywords '{self.name}' [{self.id}] = {', '.join(self.value if self.value else [])}"


class IntFieldValue(FieldValue):
    def __init__(self, config: FieldValueConfigT):
        super().__init__(config)
        try:
            self.value = None if self.value is None else int(self.value)
        except ValueError:
            raise errors.DataError(
                f"Value of field '{self.id}' is expected to be of type integer, found '{self.value}'")

    def __str__(self) -> str:
        return f"Integer '{self.name}' [{self.id}] = {self.value}"


class DecimalFieldValue(FieldValue):
    def __init__(self, config: FieldValueConfigT):
        super().__init__(config)
        try:
            self.value = None if self.value is None else float(self.value)
        except ValueError:
            raise errors.DataError(f"Value of field '{self.id}' is expected to be of type float, found '{self.value}'")

    def __str__(self) -> str:
        return f"Decimal '{self.name}' [{self.id}] = {self.value}"


class DateTimeFieldValue(FieldValue):

    def __init__(self, config: FieldValueConfigT):
        super().__init__(config)
        if self.value:
            if self.content_type == "Date":
                self.value = utils.date_from_string(str(self.value))
            else:
                self.value = utils.datetime_from_string(str(self.value))

    def __str__(self) -> str:
        return f"{self.content_type} '{self.name}' [{self.id}] = {self.value}"


FieldValue.TYPE_TABLE = cidict.CaseInsensitiveDict[Type[FieldValue]]({
    "Date": DateTimeFieldValue,
    "DateTime": DateTimeFieldValue,
    "Int": IntFieldValue,
    "Decimal": DecimalFieldValue,
    "String": StringFieldValue,
    "Keywords": KeywordsFieldValue,
})
