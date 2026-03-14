import unittest
from unittest.mock import MagicMock

import httpx

from docuware import Basket, DocuwareClient, FileCabinet
from docuware.organization import Organization
from docuware.types import DocuwareClientP


class TestFileCabinetOperations(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform/Home/IdentityServiceInfo":
                return httpx.Response(200, json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"})
            elif request.url.path == "/DocuWare/Identity/.well-known/openid-configuration":
                return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
            elif request.url.path == "/DocuWare/Identity/connect/token":
                return httpx.Response(200, json={"access_token": "mock_token"})
            elif request.url.path == "/DocuWare/Platform":
                return httpx.Response(
                    200, json={"Links": [], "Resources": [], "Version": "7.10"}
                )
            elif "/Documents" in request.url.path and request.method == "POST":
                # Entry creation / Upload
                # Return a minimal document structure
                return httpx.Response(200, json={"Id": "123", "Title": "Test Doc", "Links": []})
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        self.client.login("user", "pass")

    def test_create_document(self):
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client

        fc = FileCabinet(
            {
                "Id": "fc1",
                "Links": [
                    {
                        "rel": "documents",
                        "href": "/DocuWare/Platform/FileCabinets/fc1/Documents",
                    }
                ],
            },
            mock_org,
        )

        doc = fc.create_document(fields={"COMPANY": "ACME"})
        self.assertEqual(doc.id, "123")
        self.assertEqual(doc.title, "Test Doc")


class TestBasketSeparation(unittest.TestCase):
    def _make_org(self, fc_response):
        mock_client = MagicMock(spec=DocuwareClientP)
        mock_conn = MagicMock()
        mock_client.conn = mock_conn
        mock_conn.get_json.return_value = fc_response
        org = Organization(
            {"Name": "TestOrg", "Id": "org1", "Links": [{"rel": "filecabinets", "href": "/fc"}]},
            mock_client,
        )
        return org

    def test_file_cabinets_excludes_baskets(self):
        org = self._make_org({
            "FileCabinet": [
                {"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []},
                {"Id": "bk1", "Name": "Inbox", "IsBasket": True, "Links": []},
            ]
        })
        self.assertEqual(len(org.file_cabinets), 1)
        self.assertEqual(org.file_cabinets[0].id, "fc1")

    def test_baskets_returns_only_baskets(self):
        org = self._make_org({
            "FileCabinet": [
                {"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []},
                {"Id": "bk1", "Name": "Inbox", "IsBasket": True, "Links": []},
            ]
        })
        self.assertEqual(len(org.baskets), 1)
        self.assertIsInstance(org.baskets[0], Basket)
        self.assertTrue(org.baskets[0].is_basket)
        self.assertEqual(org.baskets[0].id, "bk1")

    def test_basket_is_instance_of_filecabinet(self):
        org = self._make_org({
            "FileCabinet": [
                {"Id": "bk1", "Name": "Inbox", "IsBasket": True, "Links": []},
            ]
        })
        self.assertIsInstance(org.baskets[0], FileCabinet)

    def test_api_called_once_for_both(self):
        org = self._make_org({
            "FileCabinet": [
                {"Id": "fc1", "Name": "Archive", "IsBasket": False, "Links": []},
                {"Id": "bk1", "Name": "Inbox", "IsBasket": True, "Links": []},
            ]
        })
        _ = org.file_cabinets
        _ = org.baskets
        org.client.conn.get_json.assert_called_once()


if __name__ == "__main__":
    unittest.main()
