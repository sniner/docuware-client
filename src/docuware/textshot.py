from __future__ import annotations

import logging
from collections.abc import Mapping
from typing import Any, Dict, Iterator, List, Optional, Union

log = logging.getLogger(__name__)

TextShotConfigT = Dict[str, Any]


def _as_list(value: Any) -> List[Any]:
    if value is None:
        return []
    if isinstance(value, list):
        return value
    return [value]


class Word:
    def __init__(self, config: TextShotConfigT):
        self.value: str = str(config.get("Value") or "")
        # Coordinates are in twips (1/1440 inch) relative to the page.
        self.left: int = int(config.get("L") or 0)
        self.top: int = int(config.get("T") or 0)
        self.width: int = int(config.get("W") or 0)
        self.height: int = int(config.get("H") or 0)
        self.bold: bool = bool(config.get("bold", False))
        font_size = config.get("fontSize")
        self.font_size: Optional[int] = int(font_size) if font_size is not None else None

    def __str__(self) -> str:
        return self.value


class TextLine:
    def __init__(self, config: TextShotConfigT):
        self.words: List[Word] = [
            Word(item)
            for item in _as_list(config.get("Items"))
            if item.get("$type") == "Word"
        ]

    @property
    def text(self) -> str:
        return " ".join(w.value for w in self.words if w.value)

    def __str__(self) -> str:
        return self.text


class TextZone:
    def __init__(self, config: TextShotConfigT):
        self.lines: List[TextLine] = [TextLine(ln) for ln in _as_list(config.get("Ln"))]

    @property
    def text(self) -> str:
        return "\n".join(ln.text for ln in self.lines)

    def words(self) -> Iterator[Word]:
        for line in self.lines:
            yield from line.words


class TableZone:
    """A zone laid out as a table. DocuWare emits these for content that the
    OCR detected as tabular (e.g. invoice line items). Each cell wraps a
    `TextZone`-shaped block of lines — we flatten them in reading order for
    the plain-text view.
    """

    def __init__(self, config: TextShotConfigT):
        self.cells: List[TextZone] = []
        for cell in _as_list(config.get("Cz")):
            # Note: DocuWare's CaseInsensitiveDict is a MutableMapping, not a dict,
            # so isinstance(cell, dict) would filter every real-connection cell out.
            if not isinstance(cell, Mapping):
                continue
            inner = cell.get("TextZone")
            if isinstance(inner, Mapping):
                self.cells.append(TextZone(inner))

    @property
    def text(self) -> str:
        return "\n".join(c.text for c in self.cells if c.text)

    def words(self) -> Iterator[Word]:
        for cell in self.cells:
            yield from cell.words()


class TextPage:
    _ZONE_TYPES = {"TextZone": TextZone, "TableZone": TableZone}

    def __init__(self, config: TextShotConfigT):
        self.language: Optional[str] = config.get("Lang")
        self.width: int = int(config.get("SizeX") or 0)
        self.height: int = int(config.get("SizeY") or 0)
        self.dpi_x: float = float(config.get("HorizontalDpi") or 0)
        self.dpi_y: float = float(config.get("VerticalDpi") or 0)
        self.skew_angle: float = float(config.get("SkewAngle") or 0.0)
        self.rotation: Optional[str] = config.get("Rotation")
        self.zones: List[Union[TextZone, TableZone]] = []
        for item in _as_list(config.get("Items")):
            zone_cls = self._ZONE_TYPES.get(item.get("$type"))
            if zone_cls is not None:
                self.zones.append(zone_cls(item))

    @property
    def text(self) -> str:
        return "\n".join(z.text for z in self.zones)

    def words(self) -> Iterator[Word]:
        for zone in self.zones:
            yield from zone.words()

    def __str__(self) -> str:
        return f"TextPage [{self.language}, {self.width}x{self.height}, {len(self.zones)} zone(s)]"


class TextShot:
    """OCR full-text content of a document section (`intellix:DocumentContent`).

    Returned by :meth:`DocumentAttachment.textshot`. Provides both a flat
    plain-text view via :attr:`text` and structured access to pages, zones,
    lines and words for callers that need coordinates or layout details.
    """

    def __init__(self, config: TextShotConfigT):
        self.pages: List[TextPage] = [TextPage(p) for p in _as_list(config.get("Pages"))]

    @property
    def text(self) -> str:
        # Form feed between pages mirrors how OCR pipelines typically delimit page breaks.
        return "\f".join(p.text for p in self.pages)

    def words(self) -> Iterator[Word]:
        for page in self.pages:
            yield from page.words()

    def __str__(self) -> str:
        return f"TextShot [{len(self.pages)} page(s), {len(self.text)} chars]"
