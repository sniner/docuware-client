import unittest

import httpx

from docuware import DocuwareClient


class TestFileCabinetOperations(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform":
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
        from unittest.mock import MagicMock

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


if __name__ == "__main__":
    unittest.main()
