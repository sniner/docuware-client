import unittest

import httpx

from docuware import DocuwareClient


class TestDocumentOperations(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")

        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform":
                return httpx.Response(
                    200, json={"Links": [], "Resources": [], "Version": "7.10"}
                )
            elif request.url.path == "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1":
                if request.method == "GET":
                    return httpx.Response(
                        200,
                        json={
                            "Id": "doc1",
                            "Title": "Test Doc",
                            "Links": [
                                {
                                    "rel": "fileDownload",
                                    "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/File",
                                },
                                {
                                    "rel": "self",
                                    "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1",
                                },
                            ],
                            "Sections": [
                                {
                                    "Id": "sec1",
                                    "OriginalFileName": "test.pdf",
                                    "Links": [
                                        {
                                            "rel": "self",
                                            "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/Sections/sec1",
                                        }
                                    ],
                                }
                            ],
                        },
                    )
                elif request.method == "DELETE":
                    return httpx.Response(200)
            elif request.url.path == "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/File":
                return httpx.Response(
                    200,
                    content=b"fake_pdf_content",
                    headers={
                        "Content-Type": "application/pdf",
                        "Content-Disposition": 'attachment; filename="test.pdf"',
                    },
                )
            elif (
                request.url.path
                == "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/Sections/sec1"
            ):
                return httpx.Response(
                    200,
                    json={
                        "Id": "sec1",
                        "Links": [
                            {
                                "rel": "fileDownload",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/Sections/sec1/File",
                            }
                        ],
                    },
                )
            elif (
                request.url.path
                == "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/Sections/sec1/File"
            ):
                return httpx.Response(
                    200,
                    content=b"attachment_content",
                    headers={"Content-Type": "application/pdf"},
                )
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        self.client.login("user", "pass")

    def test_document_download(self):
        # Proper setup
        from unittest.mock import MagicMock

        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        # Proper setup
        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client
        # So fc.organization.client works if fc.organization is MockOrg.
        # But we are mocking it, so we can just set it.

        fc = FileCabinet({"Id": "fc1"}, mock_org)

        doc = Document(
            {
                "Id": "doc1",
                "Links": [
                    {
                        "rel": "fileDownload",
                        "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/File",
                    }
                ],
            },
            fc,
        )

        data, mime, filename = doc.download()
        self.assertEqual(data, b"fake_pdf_content")
        self.assertEqual(mime, "application/pdf")
        self.assertEqual(filename, "test.pdf")

    def test_attachment_download(self):
        from unittest.mock import MagicMock

        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client

        fc = FileCabinet({"Id": "fc1"}, mock_org)

        doc = Document(
            {
                "Id": "doc1",
                "Sections": [
                    {
                        "Id": "sec1",
                        "OriginalFileName": "attachment.pdf",
                        "Links": [
                            {
                                "rel": "self",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1/Sections/sec1",
                            }
                        ],
                    }
                ],
            },
            fc,
        )

        att = doc.attachments[0]
        data, mime, filename = att.download()
        self.assertEqual(data, b"attachment_content")
        self.assertEqual(filename, "attachment.pdf")

    def test_document_delete(self):
        from unittest.mock import MagicMock

        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client

        fc = FileCabinet({"Id": "fc1"}, mock_org)

        doc = Document(
            {
                "Id": "doc1",
                "Links": [
                    {
                        "rel": "self",
                        "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1",
                    }
                ],
            },
            fc,
        )

        doc.delete()
        self.assertIsNone(doc.id)

    def test_document_str(self):
        from unittest.mock import MagicMock

        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client
        fc = FileCabinet({"Id": "fc1"}, mock_org)

        doc = Document({"Id": "doc1", "Title": "Test Doc"}, fc)

        self.assertIn("Test Doc", str(doc))
        self.assertIn("doc1", str(doc))
        self.assertIn("Document", str(doc))


if __name__ == "__main__":
    unittest.main()
