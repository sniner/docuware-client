from __future__ import annotations

import logging
import xml.etree.ElementTree as ET
from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Any, Dict, List, Optional

from docuware.utils import safe_str

log = logging.getLogger(__name__)


class FieldType(str, Enum):
    def __str__(self):
        return self.value

    TEXT = "Text"
    DATE = "Date"
    DATETIME = "DateTime"
    KEYWORD = "Keyword"
    MEMO = "Memo"
    NUMERIC = "Numeric"


@dataclass
class FieldItem:
    name: str
    kind: FieldType
    value: Any
    attrs: Dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> Dict[str, str]:
        d = {
            "dbName": safe_str(self.name),
            "type": self.kind.value,
            "value": safe_str(self.value),
        }
        d.update({k: safe_str(v) for k, v in self.attrs.items()})
        return d


class ControlFile:
    """
    Generates .dwcontrol XML files for DocuWare Document Import.
    Reference: KBA-34830, KBA-36502
    """

    def __init__(
        self,
        *,
        basket: Optional[str] = None,
        file_cabinet: Optional[str] = None,
    ):
        self.basket = basket
        self.file_cabinet = file_cabinet
        self.fields: List[FieldItem] = []

    def add_field(
        self,
        name: str,
        value: Any,
        *,
        field_type: Optional[FieldType] = None,
        culture: Optional[str] = None,
        format: Optional[str] = None,
        digits: Optional[int] = None,
    ):
        """Adds a field with automatic type detection if not specified."""
        field_value: Any = value
        field_attrs: Dict[str, Any] = {}
        if culture:
            field_attrs["culture"] = culture
        if format:
            field_attrs["format"] = format

        # Automatic type detection
        if field_type is None:
            if isinstance(value, datetime):
                field_type = FieldType.DATETIME
                field_value = value.strftime("%d.%m.%Y %H:%M")
                if "culture" not in field_attrs:
                    field_attrs["culture"] = "de-DE"
                if "format" not in field_attrs:
                    field_attrs["format"] = "dd.MM.yyyy H:mm"
            elif isinstance(value, date):
                field_type = FieldType.DATE
                field_value = value.strftime("%d.%m.%Y")
                if "culture" not in field_attrs:
                    field_attrs["culture"] = "de-DE"
                if "format" not in field_attrs:
                    field_attrs["format"] = "dd.MM.yyyy"
            elif isinstance(value, float):
                field_type = FieldType.NUMERIC
                field_attrs["digits"] = digits or 2
            elif isinstance(value, int):
                field_type = FieldType.NUMERIC
            else:
                field_type = FieldType.TEXT

        self.fields.append(
            FieldItem(
                name=name,
                kind=field_type,
                value=field_value,
                attrs=field_attrs,
            )
        )
        return self

    def to_xml(self) -> str:
        """Generates the pretty-printed XML string."""
        root = ET.Element(
            "ControlStatements",
            {
                "xmlns": "http://dev.docuware.com/Jobs/Control",
                "xmlns:xsi": "http://www.w3.org/2001/XMLSchema-instance",
            },
        )
        page = ET.SubElement(root, "Page")

        if self.basket:
            ET.SubElement(page, "Basket", {"name": self.basket})

        if self.file_cabinet:
            ET.SubElement(page, "FileCabinet", {"name": self.file_cabinet})

        for f in self.fields:
            ET.SubElement(page, "Field", f.to_dict())

        if hasattr(ET, "indent"):
            ET.indent(root, space="  ")

        return ET.tostring(root, encoding="unicode", xml_declaration=False)

    def __str__(self) -> str:
        return self.to_xml()
