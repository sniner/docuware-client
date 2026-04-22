"""Tests for the DocuWare basket-to-cabinet transfer (archive) feature.

The DocuWare REST API exposes a ``transfer`` relation on the destination
FileCabinet (``POST /DocuWare/Platform/FileCabinets/{id}/Transfer``) with
two body schemas:

* ``FileCabinetTransferInfo`` — transfer-by-id, preserves source index data.
  Fields: ``SourceDocId``, ``SourceFileCabinetId``, ``KeepSource``,
  ``FillIntellix``, ``UseDefaultDialog``.
* ``DocumentsTransferInfo`` — transfer with per-document index overrides.
  Fields: ``SourceFileCabinetId``, ``Documents[]`` (each with ``Id`` and
  optional ``Fields``), ``KeepSource``, ``FillIntellix``, ``UseDefaultDialog``.

These tests exercise both variants through httpx.MockTransport and verify the
exact body the client sends.
"""
from __future__ import annotations

import json
import unittest
from typing import Any, Dict, List
from unittest.mock import MagicMock

import httpx

from docuware import DocuwareClient, errors
from docuware.dialogs import Dialog, SearchField, StoreDialog
from docuware.document import Document
from docuware.filecabinet import Basket, FileCabinet, _coerce_doc_id, _to_document_payload
from docuware.types import OrganizationP


def _make_client_with_handler(handler) -> DocuwareClient:
    client = DocuwareClient("https://example.com")

    def full_handler(request: httpx.Request):
        path = request.url.path
        if path == "/DocuWare/Platform/Home/IdentityServiceInfo":
            return httpx.Response(
                200,
                json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"},
            )
        if path == "/DocuWare/Identity/.well-known/openid-configuration":
            return httpx.Response(
                200, json={"token_endpoint": "/DocuWare/Identity/connect/token"}
            )
        if path == "/DocuWare/Identity/connect/token":
            return httpx.Response(200, json={"access_token": "mock_token"})
        if path == "/DocuWare/Platform":
            return httpx.Response(
                200, json={"Links": [], "Resources": [], "Version": "7.13"}
            )
        return handler(request)

    client.conn.session = httpx.Client(transport=httpx.MockTransport(full_handler))
    client.login("user", "pass")
    return client


def _make_fc(client: DocuwareClient, fc_id: str, *, is_basket: bool = False) -> FileCabinet:
    mock_org = MagicMock(spec=OrganizationP)
    mock_org.client = client
    cls = Basket if is_basket else FileCabinet
    return cls(
        {
            "Id": fc_id,
            "Name": fc_id,
            "IsBasket": is_basket,
            "Links": [
                {"rel": "self", "href": f"/DocuWare/Platform/FileCabinets/{fc_id}"},
                {"rel": "documents", "href": f"/DocuWare/Platform/FileCabinets/{fc_id}/Documents"},
                {"rel": "transfer", "href": f"/DocuWare/Platform/FileCabinets/{fc_id}/Transfer"},
            ],
        },
        mock_org,
    )


def _doc(fc: FileCabinet, doc_id: str) -> Document:
    return Document(
        {
            "Id": doc_id,
            "Title": f"Doc {doc_id}",
            "Links": [
                {
                    "rel": "self",
                    "href": f"/DocuWare/Platform/FileCabinets/{fc.id}/Documents/{doc_id}",
                }
            ],
        },
        fc,
    )


class TestTransferInfoBodyShape(unittest.TestCase):
    """Verify the exact request body the client sends."""

    def setUp(self):
        self.captured: List[Dict[str, Any]] = []

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform/FileCabinets/archive1/Transfer":
                body = json.loads(request.content.decode())
                self.captured.append(body)
                return httpx.Response(
                    200,
                    json={
                        "Count": {"Value": len(body.get("SourceDocId") or body.get("Documents") or [])},
                        "Items": [
                            {
                                "Id": "new-1",
                                "Title": "Archived",
                                "Links": [
                                    {
                                        "rel": "self",
                                        "href": "/DocuWare/Platform/FileCabinets/archive1/Documents/new-1",
                                    }
                                ],
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        self.client = _make_client_with_handler(handler)
        self.basket = _make_fc(self.client, "basket1", is_basket=True)
        self.archive = _make_fc(self.client, "archive1")

    def test_by_id_uses_filecabinettransferinfo(self):
        """Passing plain ids → FileCabinetTransferInfo body."""
        docs = self.archive.transfer(self.basket, [101, 102])
        self.assertEqual(len(docs), 1)
        body = self.captured[0]
        self.assertEqual(body["SourceDocId"], [101, 102])
        self.assertEqual(body["SourceFileCabinetId"], "basket1")
        self.assertIs(body["KeepSource"], False)
        self.assertIs(body["FillIntellix"], False)
        self.assertIs(body["UseDefaultDialog"], False)
        # The "by id" form does NOT include a Documents array
        self.assertNotIn("Documents", body)

    def test_by_document_coerces_ids(self):
        """Passing Document objects extracts & coerces numeric ids to int."""
        d1 = _doc(self.basket, "55")
        d2 = _doc(self.basket, "77")
        self.archive.transfer(self.basket, [d1, d2])
        body = self.captured[0]
        self.assertEqual(body["SourceDocId"], [55, 77])

    def test_non_numeric_id_preserved_as_string(self):
        """GUID-like ids are left as strings — DocuWare accepts both."""
        self.archive.transfer(self.basket, ["abc-123"])
        body = self.captured[0]
        self.assertEqual(body["SourceDocId"], ["abc-123"])

    def test_with_field_overrides_uses_documentstransferinfo(self):
        """Any item with 'fields' → DocumentsTransferInfo body."""
        self.archive.transfer(
            self.basket,
            [
                {"id": 101, "fields": {"COMPANY": "ACME", "YEAR": 2026}},
                {"id": 102},  # no overrides on this one
            ],
        )
        body = self.captured[0]
        self.assertNotIn("SourceDocId", body)
        self.assertEqual(body["SourceFileCabinetId"], "basket1")
        self.assertEqual(len(body["Documents"]), 2)
        self.assertEqual(body["Documents"][0]["Id"], 101)
        fields = {f["FieldName"]: f for f in body["Documents"][0]["Fields"]}
        self.assertEqual(fields["COMPANY"]["Item"], "ACME")
        self.assertEqual(fields["COMPANY"]["ItemElementName"], "String")
        self.assertEqual(fields["YEAR"]["Item"], 2026)
        self.assertEqual(fields["YEAR"]["ItemElementName"], "Int")
        # Second doc has no Fields key
        self.assertNotIn("Fields", body["Documents"][1])

    def test_keep_source_and_other_flags_passed_through(self):
        self.archive.transfer(
            self.basket,
            [1],
            keep_source=True,
            fill_intellix=True,
            use_default_dialog=True,
        )
        body = self.captured[0]
        self.assertIs(body["KeepSource"], True)
        self.assertIs(body["FillIntellix"], True)
        self.assertIs(body["UseDefaultDialog"], True)

    def test_source_as_id_string(self):
        """source may be given as a plain id string too."""
        self.archive.transfer("some-other-fc", [1])
        body = self.captured[0]
        self.assertEqual(body["SourceFileCabinetId"], "some-other-fc")

    def test_empty_documents_raises(self):
        with self.assertRaises(errors.DataError):
            self.archive.transfer(self.basket, [])

    def test_unsupported_item_type_raises(self):
        with self.assertRaises(errors.DataError):
            self.archive.transfer(self.basket, [object()])  # type: ignore[list-item]

    def test_mapping_without_id_raises(self):
        with self.assertRaises(errors.DataError):
            self.archive.transfer(self.basket, [{"fields": {"X": 1}}])

    def test_mapping_with_capitalised_keys_works(self):
        """Mapping variant accepts both {id,fields} and {Id,Fields}."""
        self.archive.transfer(
            self.basket, [{"Id": 5, "Fields": {"X": "y"}}]
        )
        body = self.captured[0]
        self.assertEqual(body["Documents"][0]["Id"], 5)
        self.assertEqual(body["Documents"][0]["Fields"][0]["FieldName"], "X")


class TestArchiveConvenience(unittest.TestCase):
    """Document.archive() — the single-document convenience wrapper."""

    def setUp(self):
        self.captured: List[Dict[str, Any]] = []

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform/FileCabinets/archive1/Transfer":
                body = json.loads(request.content.decode())
                self.captured.append(body)
                return httpx.Response(
                    200,
                    json={
                        "Count": {"Value": 1},
                        "Items": [
                            {
                                "Id": "archived-42",
                                "Title": "Archived",
                                "Links": [],
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        self.client = _make_client_with_handler(handler)
        self.basket = _make_fc(self.client, "basket1", is_basket=True)
        self.archive = _make_fc(self.client, "archive1")

    def test_archive_default_moves_document(self):
        doc = _doc(self.basket, "42")
        archived = doc.archive(self.archive)
        self.assertEqual(archived.id, "archived-42")
        # Source document must be marked deleted after a move
        self.assertTrue(doc._deleted)
        body = self.captured[0]
        self.assertEqual(body["SourceDocId"], [42])
        self.assertEqual(body["SourceFileCabinetId"], "basket1")
        self.assertIs(body["KeepSource"], False)

    def test_archive_with_keep_source_true_preserves_document(self):
        doc = _doc(self.basket, "42")
        doc.archive(self.archive, keep_source=True)
        # Copy, not move — source still alive
        self.assertFalse(doc._deleted)
        self.assertIs(self.captured[0]["KeepSource"], True)

    def test_archive_with_fields_uses_documentstransferinfo(self):
        doc = _doc(self.basket, "42")
        doc.archive(
            self.archive,
            fields={"DOCTYPE": "Invoice", "DOCDATE": "2026-04-22"},
        )
        body = self.captured[0]
        self.assertEqual(body["Documents"][0]["Id"], 42)
        field_map = {f["FieldName"]: f for f in body["Documents"][0]["Fields"]}
        self.assertIn("DOCTYPE", field_map)
        self.assertEqual(field_map["DOCTYPE"]["Item"], "Invoice")
        self.assertEqual(field_map["DOCDATE"]["Item"], "2026-04-22")

    def test_archive_on_deleted_doc_raises(self):
        doc = _doc(self.basket, "42")
        doc._deleted = True
        with self.assertRaises(errors.DataError):
            doc.archive(self.archive)

    def test_archive_on_doc_without_id_raises(self):
        doc = _doc(self.basket, "42")
        doc.id = None
        with self.assertRaises(errors.DataError):
            doc.archive(self.archive)


class TestTransferEndpointResolution(unittest.TestCase):
    """The client prefers the explicit 'transfer' link but can fall back."""

    def _make_archive_with_links(self, client: DocuwareClient, links: list) -> FileCabinet:
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = client
        return FileCabinet({"Id": "archive1", "Links": links}, mock_org)

    def test_uses_transfer_link_when_present(self):
        captured = []

        def handler(request: httpx.Request):
            if request.url.path == "/custom/transfer/path":
                captured.append(str(request.url))
                return httpx.Response(200, json={"Items": []})
            return httpx.Response(404)

        client = _make_client_with_handler(handler)
        fc = self._make_archive_with_links(
            client, [{"rel": "transfer", "href": "/custom/transfer/path"}]
        )
        basket = _make_fc(client, "basket1", is_basket=True)
        fc.transfer(basket, [1])
        self.assertEqual(len(captured), 1)

    def test_falls_back_to_self_plus_transfer(self):
        captured = []

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform/FileCabinets/archive1/Transfer":
                captured.append(str(request.url))
                return httpx.Response(200, json={"Items": []})
            return httpx.Response(404)

        client = _make_client_with_handler(handler)
        fc = self._make_archive_with_links(
            client,
            [{"rel": "self", "href": "/DocuWare/Platform/FileCabinets/archive1"}],
        )
        basket = _make_fc(client, "basket1", is_basket=True)
        fc.transfer(basket, [1])
        self.assertEqual(len(captured), 1)

    def test_no_endpoint_raises_internal_error(self):
        client = _make_client_with_handler(lambda r: httpx.Response(404))
        fc = self._make_archive_with_links(client, [])
        basket = _make_fc(client, "basket1", is_basket=True)
        with self.assertRaises(errors.InternalError):
            fc.transfer(basket, [1])


class TestFieldValidationHints(unittest.TestCase):
    """SearchField exposes NotEmpty / ReadOnly / Mask as first-class attributes
    and StoreDialog offers a client-side required-field pre-check."""

    def _store_dialog(self, fields_config) -> StoreDialog:
        mock_org = MagicMock(spec=OrganizationP)
        mock_client = MagicMock()
        mock_conn = MagicMock()
        mock_client.conn = mock_conn
        mock_org.client = mock_client
        mock_conn.get_json.return_value = {"Fields": fields_config}
        fc = FileCabinet({"Id": "fc1", "Links": []}, mock_org)
        dlg = Dialog.from_config(
            {
                "$type": "DialogInfo",
                "Id": "StoreA",
                "Type": "Store",
                "Links": [{"rel": "self", "href": "/dialogs/StoreA"}],
            },
            fc,
        )
        assert isinstance(dlg, StoreDialog)
        return dlg

    def test_search_field_exposes_not_empty(self):
        f = SearchField(
            {
                "DBFieldName": "COMPANY",
                "DlgLabel": "Company",
                "DWFieldType": "String",
                "NotEmpty": True,
            },
            MagicMock(),
        )
        self.assertTrue(f.not_empty)
        self.assertTrue(f.required)
        self.assertIn("required", str(f))

    def test_search_field_exposes_mask_and_length(self):
        f = SearchField(
            {
                "DBFieldName": "IBAN",
                "DWFieldType": "String",
                "Length": 34,
                "Mask": "^[A-Z]{2}[0-9]{2}.*$",
                "MaskErrorText": "IBAN must start with two letters and two digits",
            },
            MagicMock(),
        )
        self.assertEqual(f.length, 34)
        self.assertEqual(f.mask, "^[A-Z]{2}[0-9]{2}.*$")
        assert f.mask_error_text is not None
        self.assertTrue(f.mask_error_text.startswith("IBAN"))
        self.assertFalse(f.not_empty)

    def test_store_dialog_required_fields(self):
        dlg = self._store_dialog([
            {"DBFieldName": "COMPANY", "DlgLabel": "Company", "DWFieldType": "String", "NotEmpty": True},
            {"DBFieldName": "DATE", "DlgLabel": "Date", "DWFieldType": "Date", "NotEmpty": True},
            {"DBFieldName": "NOTE", "DlgLabel": "Note", "DWFieldType": "Memo", "NotEmpty": False},
        ])
        self.assertEqual(set(dlg.required_fields.keys()), {"COMPANY", "DATE"})

    def test_validate_fields_flags_missing(self):
        dlg = self._store_dialog([
            {"DBFieldName": "COMPANY", "DlgLabel": "Company", "DWFieldType": "String", "NotEmpty": True},
            {"DBFieldName": "DATE",    "DlgLabel": "Date",    "DWFieldType": "Date",   "NotEmpty": True},
        ])
        # Everything missing
        self.assertEqual(set(dlg.validate_fields({})), {"COMPANY", "DATE"})
        # By db name
        self.assertEqual(dlg.validate_fields({"COMPANY": "ACME", "DATE": "2026-01-01"}), [])
        # By label (case-insensitive)
        self.assertEqual(dlg.validate_fields({"company": "ACME", "Date": "2026-01-01"}), [])
        # Empty string counts as missing
        self.assertEqual(dlg.validate_fields({"COMPANY": "", "DATE": None}),
                         ["COMPANY", "DATE"])


class TestCoerceHelpers(unittest.TestCase):
    def test_coerce_doc_id_numeric_string(self):
        self.assertEqual(_coerce_doc_id("123"), 123)

    def test_coerce_doc_id_int(self):
        self.assertEqual(_coerce_doc_id(42), 42)

    def test_coerce_doc_id_non_numeric(self):
        self.assertEqual(_coerce_doc_id("guid-like"), "guid-like")

    def test_coerce_doc_id_rejects_bool(self):
        with self.assertRaises(errors.DataError):
            _coerce_doc_id(True)

    def test_to_document_payload_without_fields(self):
        self.assertEqual(_to_document_payload({"id": 9}), {"Id": 9})

    def test_to_document_payload_with_date(self):
        from datetime import date
        payload = _to_document_payload({"id": 9, "fields": {"DOCDATE": date(2026, 4, 22)}})
        self.assertEqual(payload["Fields"][0]["ItemElementName"], "DateTime")
        self.assertEqual(payload["Fields"][0]["Item"], "2026-04-22")


if __name__ == "__main__":
    unittest.main()
