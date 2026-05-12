import json as _json
import unittest

import httpx

from docuware import DocuwareClient
from docuware.errors import SearchConditionError


class TestSearchFlow(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")
        self.captured_bodies: list = []

        def handler(request: httpx.Request):
            path = request.url.path
            if path == "/DocuWare/Platform/Home/IdentityServiceInfo":
                return httpx.Response(200, json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"})
            elif path == "/DocuWare/Identity/.well-known/openid-configuration":
                return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
            elif path == "/DocuWare/Identity/connect/token":
                return httpx.Response(200, json={"access_token": "mock_token"})
            elif path == "/DocuWare/Platform":
                return httpx.Response(
                    200,
                    json={
                        "Links": [
                            {"rel": "organizations", "href": "/DocuWare/Platform/Organizations"}
                        ],
                        "Resources": [],
                        "Version": "7.10",
                    },
                )
            elif path == "/DocuWare/Platform/Organizations":
                return httpx.Response(
                    200,
                    json={
                        "Organization": [
                            {
                                "Name": "Test Org",
                                "Id": "1",
                                "Links": [
                                    {
                                        "rel": "filecabinets",
                                        "href": "/DocuWare/Platform/Organizations/1/FileCabinets",
                                    }
                                ],
                            }
                        ]
                    },
                )
            elif path == "/DocuWare/Platform/Organizations/1/FileCabinets":
                return httpx.Response(
                    200,
                    json={
                        "FileCabinet": [
                            {
                                "Name": "Archive",
                                "Id": "fc1",
                                "Links": [
                                    {
                                        "rel": "dialogs",
                                        "href": "/DocuWare/Platform/FileCabinets/fc1/Dialogs",
                                    }
                                ],
                            }
                        ]
                    },
                )
            elif "/Dialogs" in path and "fc1" in path and not path.endswith("dlg1"):
                return httpx.Response(
                    200,
                    json={
                        "Dialog": [
                            {
                                "DisplayName": "Default Search",
                                "Id": "dlg1",
                                "Type": "Search",
                                "$type": "DialogInfo",
                                "FileCabinetId": "fc1",
                                "Links": [
                                    {
                                        "rel": "self",
                                        "href": "/DocuWare/Platform/FileCabinets/fc1/Dialogs/dlg1",
                                    }
                                ],
                            }
                        ]
                    },
                )
            elif path.endswith("/dlg1"):
                return httpx.Response(
                    200,
                    json={
                        "Fields": [
                            {
                                "DBFieldName": "COMPANY",
                                "DlgLabel": "Company",
                                "DWFieldType": "String",
                            },
                            {
                                "DBFieldName": "BELEGDATUM",
                                "DlgLabel": "Belegdatum",
                                "DWFieldType": "Date",
                            },
                        ],
                        "Query": {
                            "Links": [
                                {
                                    "rel": "dialogExpression",
                                    "href": "/DocuWare/Platform/FileCabinets/fc1/Query/DialogExpression",
                                },
                            ]
                        },
                    },
                )
            elif "/DialogExpression" in path:
                # Capture the JSON body so tests can assert SortOrder shape.
                try:
                    self.captured_bodies.append(_json.loads(request.content.decode()))
                except Exception:
                    self.captured_bodies.append(None)
                return httpx.Response(
                    200,
                    json={
                        "Count": {"Value": 1},
                        "Items": [
                            {
                                "Title": "Invoice 1",
                                "Id": "doc1",
                                "ContentType": "application/pdf",
                                "Links": [
                                    {
                                        "rel": "self",
                                        "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1",
                                    }
                                ],
                            }
                        ],
                        "Links": [],
                    },
                )
            elif "/Documents/doc1" in path:
                return httpx.Response(
                    200,
                    json={
                        "Id": "doc1",
                        "Title": "Invoice 1",
                        "Links": [
                            {
                                "rel": "self",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1",
                            }
                        ],
                    },
                )
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))

    def _dlg(self):
        """Log in and return a ready-to-use SearchDialog."""
        self.client.login("user", "pass")
        org = self.client.organization("Test Org")
        assert org is not None
        fc = org.file_cabinet("Archive", required=True)
        return fc.search_dialog("Default Search", required=True)

    def test_search_workflow(self):
        dlg = self._dlg()
        results = dlg.search("COMPANY=ACME")
        result_list = list(results)
        self.assertEqual(len(result_list), 1)
        self.assertEqual(result_list[0].title, "Invoice 1")
        # SearchResultItem.id mirrors Document.id, available without an extra fetch
        self.assertEqual(result_list[0].id, "doc1")
        self.assertEqual(result_list[0].document.id, "doc1")

    def test_search_without_order_by_omits_sort_order(self):
        dlg = self._dlg()
        list(dlg.search("COMPANY=ACME"))
        self.assertNotIn("SortOrder", self.captured_bodies[-1])

    def test_order_by_single_field_in_body(self):
        dlg = self._dlg()
        list(dlg.search("COMPANY=ACME", order_by=[("BELEGDATUM", "desc")]))
        self.assertEqual(
            self.captured_bodies[-1].get("SortOrder"),
            [{"Field": "BELEGDATUM", "Direction": "Desc"}],
        )

    def test_order_by_multiple_fields_preserve_order(self):
        dlg = self._dlg()
        list(dlg.search(
            "COMPANY=ACME",
            order_by=[("BELEGDATUM", "desc"), ("COMPANY", "asc")],
        ))
        self.assertEqual(
            self.captured_bodies[-1].get("SortOrder"),
            [
                {"Field": "BELEGDATUM", "Direction": "Desc"},
                {"Field": "COMPANY", "Direction": "Asc"},
            ],
        )

    def test_order_by_display_name_resolves_to_db_name(self):
        dlg = self._dlg()
        list(dlg.search("COMPANY=ACME", order_by=[("Belegdatum", "desc")]))
        self.assertEqual(
            self.captured_bodies[-1].get("SortOrder"),
            [{"Field": "BELEGDATUM", "Direction": "Desc"}],
        )

    def test_order_by_direction_case_insensitive(self):
        dlg = self._dlg()
        list(dlg.search("COMPANY=ACME", order_by=[("BELEGDATUM", "DESC")]))
        self.assertEqual(
            self.captured_bodies[-1].get("SortOrder"),
            [{"Field": "BELEGDATUM", "Direction": "Desc"}],
        )

    def test_order_by_default_direction(self):
        dlg = self._dlg()
        list(dlg.search("COMPANY=ACME", order_by=[("BELEGDATUM", "default")]))
        self.assertEqual(
            self.captured_bodies[-1].get("SortOrder"),
            [{"Field": "BELEGDATUM", "Direction": "Default"}],
        )

    def test_order_by_unknown_field_raises(self):
        dlg = self._dlg()
        with self.assertRaises(SearchConditionError):
            dlg.search("COMPANY=ACME", order_by=[("NoSuchField", "asc")])

    def test_order_by_invalid_direction_raises(self):
        dlg = self._dlg()
        with self.assertRaises(SearchConditionError):
            dlg.search("COMPANY=ACME", order_by=[("BELEGDATUM", "sideways")])


if __name__ == "__main__":
    unittest.main()
