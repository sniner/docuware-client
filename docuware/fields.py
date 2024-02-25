from __future__ import annotations
import logging
from typing import Any, Iterator, Union, List, Tuple, Dict

from docuware import cidict, errors, utils

log = logging.getLogger(__name__)


class FieldValue:
    TYPE_TABLE = {}

    def __init__(self, config: dict):
        self.name = config.get("FieldLabel")
        self.id = config.get("FieldName")
        self.content_type = config.get("ItemElementName")
        self.read_only = config.get("ReadOnly", True)
        self.internal = config.get("SystemField", False)
        self.value = config.get("Item")

    @staticmethod
    def from_config(config: dict):
        content_type = config.get("ItemElementName")
        return FieldValue.TYPE_TABLE.get(content_type, FieldValue)(config)

    def __str__(self):
        return f"Value '{self.name}' [{self.id}, {self.content_type}] = '{self.value}'"


class StringFieldValue(FieldValue):
    def __init__(self, config: dict):
        super().__init__(config)
        self.value = str(self.value) if self.value else None

    def __str__(self):
        return f"Text '{self.name}' [{self.id}] = '{self.value}'"


class KeywordsFieldValue(FieldValue):
    def __init__(self, config: dict):
        super().__init__(config)
        values = config.get("Item", {}).get("Keyword", [])
        self.value = values if values else None

    def __str__(self):
        return f"Keywords '{self.name}' [{self.id}] = {', '.join(self.value if self.value else [])}"


class IntFieldValue(FieldValue):
    def __init__(self, config: dict):
        super().__init__(config)
        try:
            self.value = None if self.value is None else int(self.value)
        except ValueError:
            raise errors.DataError(
                f"Value of field '{self.id}' is expected to be of type integer, found '{self.value}'")

    def __str__(self):
        return f"Integer '{self.name}' [{self.id}] = {self.value}"


class DecimalFieldValue(FieldValue):
    def __init__(self, config: dict):
        super().__init__(config)
        try:
            self.value = None if self.value is None else float(self.value)
        except ValueError:
            raise errors.DataError(f"Value of field '{self.id}' is expected to be of type float, found '{self.value}'")

    def __str__(self):
        return f"Decimal '{self.name}' [{self.id}] = {self.value}"


class DateTimeFieldValue(FieldValue):

    def __init__(self, config: dict):
        super().__init__(config)
        if self.content_type == "Date":
            self.value = utils.date_from_string(self.value)
        else:
            self.value = utils.datetime_from_string(self.value)

    def __str__(self):
        return f"{self.content_type} '{self.name}' [{self.id}] = {self.value}"


FieldValue.TYPE_TABLE = cidict.CaseInsensitiveDict({
    "Date": DateTimeFieldValue,
    "DateTime": DateTimeFieldValue,
    "Int": IntFieldValue,
    "Decimal": DecimalFieldValue,
    "String": StringFieldValue,
    "Keywords": KeywordsFieldValue,
})
