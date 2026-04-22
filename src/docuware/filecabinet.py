from __future__ import annotations

import logging
from typing import Any, Dict, Iterable, List, Literal, Mapping, Optional, Sequence, Union, overload

from docuware import dialogs, document, errors, structs, types

log = logging.getLogger(__name__)


# Accepted shapes for documents to transfer.  A document may be given as a
# Document instance, as a bare id (str/int), or as a mapping containing at
# least an "id" key and optional "fields" (index value overrides for the
# destination cabinet):
#     {"id": 42, "fields": {"COMPANY": "ACME"}}
TransferDocT = Union[
    "document.Document",
    str,
    int,
    Mapping[str, Any],
]


class FileCabinet:
    def __init__(self, config: Dict, organization: types.OrganizationP):
        self.organization = organization
        self.name = config.get("Name", "")
        self.id = config.get("Id", "")
        self.is_basket: bool = bool(config.get("IsBasket", False))
        self.endpoints = structs.Endpoints(config)
        self._dialogs: Optional[List[types.DialogP]] = None

    @property
    def dialogs(self) -> List[types.DialogP]:
        if self._dialogs is None:
            result = self.organization.client.conn.get_json(self.endpoints["dialogs"])
            self._dialogs = [
                dialogs.Dialog.from_config(dlg, self)
                for dlg in result.get("Dialog", [])
                # Only DialogInfo entries are user-facing dialogs. IDs containing "_"
                # are mobile-specific or internal system copies; skip them.
                if dlg.get("$type") == "DialogInfo" and "_" not in dlg.get("Id", "")
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
        search_dlgs = [dlg for dlg in self.dialogs if isinstance(dlg, dialogs.SearchDialog)]
        if key:
            return structs.first_item_by_id_or_name(search_dlgs, key, required=required)
        # Prefer the dialog marked IsDefault; fall back to the first available one
        result = next((dlg for dlg in search_dlgs if dlg.is_default), None) or (
            search_dlgs[0] if search_dlgs else None
        )
        if result is None and required:
            raise KeyError("SearchDialog")
        return result

    def create_document(
        self,
        fields: Optional[Dict[str, Any]] = None,
    ) -> document.Document:
        endpoint = self.endpoints["documents"]

        # Create data record (no file)
        json_fields = []
        if fields:
            for key, value in fields.items():
                type_name, value = structs.python_to_dw_field(value)
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

    def _transfer_endpoint(self) -> str:
        """Resolve the "transfer" relation URL of this cabinet."""
        if "transfer" in self.endpoints:
            return self.endpoints["transfer"]
        # Fallback: build from the cabinet id. DocuWare exposes the transfer
        # relation under /DocuWare/Platform/FileCabinets/{id}/Transfer.
        if "self" in self.endpoints:
            return self.endpoints["self"].rstrip("/") + "/Transfer"
        if "documents" in self.endpoints:
            return self.endpoints["documents"].rsplit("/", 1)[0] + "/Transfer"
        raise errors.InternalError(
            f"FileCabinet {self.id!r} has no 'transfer' relation and no base URL to derive it"
        )

    def transfer(
        self,
        source: Union[types.FileCabinetP, str],
        documents: Iterable[TransferDocT],
        *,
        keep_source: bool = False,
        fill_intellix: bool = False,
        use_default_dialog: bool = False,
    ) -> Sequence["document.Document"]:
        """Transfer documents from ``source`` (a basket or file cabinet) into this cabinet.

        This is the generic, batch-friendly form. It posts to the ``transfer``
        relation on the destination cabinet. See :meth:`document.Document.archive`
        for a simpler single-document helper.

        Args:
            source: The source :class:`FileCabinet`/:class:`Basket`, or its id.
            documents: An iterable of documents to transfer. Each item may be:

                * a :class:`docuware.document.Document`,
                * a document id (``str``/``int``),
                * a mapping ``{"id": ..., "fields": {...}}`` — the ``fields`` map
                  contains destination index values that override what the source
                  document provides. This is the canonical way to supply the
                  mandatory index fields required by the destination store dialog.

            keep_source: If ``True``, documents remain in the source (copy).
                If ``False`` (default), they are removed from the source (move).
                This is the DocuWare ``KeepSource`` flag.
            fill_intellix: If ``True``, Intellix index-data suggestions are
                applied to the transferred documents using the intellix map of
                the default assigned dialog. Defaults to ``False``.
            use_default_dialog: If ``True`` and a default store dialog is
                assigned to the user, it is used (which may drive default
                values and validation). Defaults to ``False``.

        Returns:
            A list of :class:`docuware.document.Document` objects representing
            the newly stored documents in the destination cabinet.

        Raises:
            docuware.errors.DataError: if ``documents`` is empty.
            docuware.errors.ResourceError: if the server rejects the transfer
                (for example, because a mandatory index field is missing).

        Notes on mandatory fields (server-side validation):
            The destination cabinet's store dialog and field settings
            determine which index fields are required. Fields with
            ``NotEmpty = True`` must have a value — either provided via
            ``fields`` in the per-document mapping, or already present on the
            source document. Additional constraints (``Mask`` regex,
            ``Length``, select-list-only values, dialog-level mandatory rules
            added in 7.1+) are enforced server-side. Use
            :meth:`docuware.dialogs.StoreDialog.validate_fields` for a
            best-effort client-side pre-check.
        """
        src_id = source.id if not isinstance(source, str) else source
        if not src_id:
            raise errors.DataError("transfer: source must have a non-empty id")

        # Normalise documents. We build two parallel forms so we can pick the
        # most appropriate request body:
        #   - `id_only`: all items are plain ids → use FileCabinetTransferInfo
        #     (the simpler variant, preserves source index data as-is).
        #   - otherwise: some items carry field overrides → use
        #     DocumentsTransferInfo with explicit per-document Field lists.
        normalised: List[Dict[str, Any]] = []
        id_only = True
        for item in documents:
            if isinstance(item, document.Document):
                if item.id is None:
                    raise errors.DataError("transfer: document has no id")
                normalised.append({"id": item.id, "fields": None})
            elif isinstance(item, (str, int)):
                normalised.append({"id": item, "fields": None})
            elif isinstance(item, Mapping):
                if "id" not in item and "Id" not in item:
                    raise errors.DataError("transfer: document mapping needs an 'id' key")
                fields = item.get("fields") if "fields" in item else item.get("Fields")
                doc_id = item.get("id") if "id" in item else item.get("Id")
                normalised.append({"id": doc_id, "fields": fields or None})
                if fields:
                    id_only = False
            else:
                raise errors.DataError(
                    f"transfer: unsupported document item type: {type(item).__name__}"
                )

        if not normalised:
            raise errors.DataError("transfer: at least one document must be given")

        if id_only:
            body: Dict[str, Any] = {
                "SourceDocId": [_coerce_doc_id(n["id"]) for n in normalised],
                "SourceFileCabinetId": src_id,
                "KeepSource": bool(keep_source),
                "FillIntellix": bool(fill_intellix),
                "UseDefaultDialog": bool(use_default_dialog),
            }
        else:
            body = {
                "SourceFileCabinetId": src_id,
                "Documents": [_to_document_payload(n) for n in normalised],
                "KeepSource": bool(keep_source),
                "FillIntellix": bool(fill_intellix),
                "UseDefaultDialog": bool(use_default_dialog),
            }

        endpoint = self._transfer_endpoint()
        result = self.organization.client.conn.post_json(endpoint, json=body)
        return [document.Document(d, self) for d in result.get("Items", []) or []]

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.name}' [{self.id}]"


class Basket(FileCabinet):
    """A DocuWare basket. Thin subclass of FileCabinet for type distinction."""


def _coerce_doc_id(value: Any) -> Union[int, str]:
    """Coerce a document id to ``int`` if numeric; keep as string otherwise.

    DocuWare's ``FileCabinetTransferInfo.SourceDocId`` is an array of ``int`` on
    the server side, so we prefer integers whenever possible.
    """
    if isinstance(value, bool):
        raise errors.DataError("document id must not be bool")
    if isinstance(value, int):
        return value
    s = str(value).strip()
    try:
        return int(s)
    except ValueError:
        return s


def _to_document_payload(item: Dict[str, Any]) -> Dict[str, Any]:
    """Build the per-document payload for DocumentsTransferInfo.Documents[]."""
    payload: Dict[str, Any] = {"Id": _coerce_doc_id(item["id"])}
    fields = item.get("fields")
    if fields:
        json_fields = []
        for key, value in fields.items():
            type_name, serialised = structs.python_to_dw_field(value)
            json_fields.append(
                {"FieldName": key, "Item": serialised, "ItemElementName": type_name}
            )
        payload["Fields"] = json_fields
    return payload
