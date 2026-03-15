import unittest

import httpx

from docuware import DocuwareClient


class TestDocumentOperations(unittest.TestCase):
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
        self.assertTrue(doc._deleted)
        self.assertEqual(doc.id, "doc1")  # id preserved after deletion

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


class TestDocumentAdditional(unittest.TestCase):
    """Tests for previously uncovered Document / DocumentAttachment paths."""

    def setUp(self):
        self.client = DocuwareClient("https://example.com")
        self.fc_id = "fc1"
        self.doc_id = "doc1"

        def handler(request: httpx.Request):
            path = request.url.path
            if path == "/DocuWare/Platform/Home/IdentityServiceInfo":
                return httpx.Response(200, json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"})
            elif path == "/DocuWare/Identity/.well-known/openid-configuration":
                return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
            elif path == "/DocuWare/Identity/connect/token":
                return httpx.Response(200, json={"access_token": "mock_token"})
            elif path == "/DocuWare/Platform":
                return httpx.Response(200, json={"Links": [], "Resources": [], "Version": "7.10"})
            elif path == f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Thumbnail":
                return httpx.Response(
                    200, content=b"thumb_bytes",
                    headers={"Content-Type": "image/png",
                             "Content-Disposition": 'attachment; filename="thumb.png"'},
                )
            elif path == f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/FileDownloadAsArchive":
                return httpx.Response(
                    200, content=b"zip_bytes",
                    headers={"Content-Type": "application/zip",
                             "Content-Disposition": 'attachment; filename="archive.zip"'},
                )
            elif path == f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Fields":
                if request.method == "PUT":
                    return httpx.Response(200, json={"Id": self.doc_id, "Links": []})
            elif path == f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Sections":
                if request.method == "POST":
                    return httpx.Response(200, json={
                        "Id": "sec_new",
                        "ContentType": "text/plain",
                        "OriginalFileName": "note.txt",
                        "FileSize": 5,
                        "Links": [],
                    })
            elif path == f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Sections/sec1":
                if request.method == "DELETE":
                    return httpx.Response(200)
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        self.client.login("user", "pass")

    def _make_doc(self, extra_links=None, sections=None):
        from unittest.mock import MagicMock
        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client
        fc = FileCabinet({"Id": self.fc_id}, mock_org)
        links = [
            {"rel": "self",              "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}"},
            {"rel": "thumbnail",         "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Thumbnail"},
            {"rel": "fileDownload",      "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/File"},
            {"rel": "downloadAsArchive", "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/FileDownloadAsArchive"},
            {"rel": "fields",            "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Fields"},
            {"rel": "files",             "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Sections"},
        ] + (extra_links or [])
        return Document(
            {"Id": self.doc_id, "Title": "Test Doc", "Links": links, "Sections": sections or []},
            fc,
        )

    # --- _assert_alive ---

    def test_assert_alive_raises_on_deleted_doc(self):
        from docuware import errors
        doc = self._make_doc()
        doc._deleted = True
        with self.assertRaises(errors.DataError):
            doc.thumbnail()
        with self.assertRaises(errors.DataError):
            doc.download_all()
        with self.assertRaises(errors.DataError):
            doc.delete()
        with self.assertRaises(errors.DataError):
            doc.update({})
        with self.assertRaises(errors.DataError):
            import io
            doc.upload_attachment(io.BytesIO(b"x"))

    # --- field() ---

    def test_field_lookup_by_id(self):
        from unittest.mock import MagicMock
        from docuware.document import Document
        from docuware.filecabinet import FileCabinet
        from docuware.types import OrganizationP

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client
        fc = FileCabinet({"Id": self.fc_id}, mock_org)
        doc = Document({
            "Id": self.doc_id,
            "Fields": [
                {"FieldName": "COMPANY", "Item": "ACME", "ItemElementName": "String"},
            ],
            "Links": [],
        }, fc)
        f = doc.field("COMPANY")
        self.assertIsNotNone(f)
        self.assertEqual(f.id, "COMPANY")

    def test_field_not_found_returns_default(self):
        doc = self._make_doc()
        self.assertIsNone(doc.field("NONEXISTENT"))

    # --- thumbnail() ---

    def test_thumbnail_returns_image_bytes(self):
        doc = self._make_doc()
        data, mime, name = doc.thumbnail()
        self.assertEqual(data, b"thumb_bytes")
        self.assertEqual(mime, "image/png")

    # --- download_all() ---

    def test_download_all_returns_archive(self):
        doc = self._make_doc()
        data, mime, name = doc.download_all()
        self.assertEqual(data, b"zip_bytes")
        self.assertIn("zip", mime)

    # --- update() ---

    def test_update_returns_self(self):
        doc = self._make_doc()
        result = doc.update({"COMPANY": "New Corp", "YEAR": 2024})
        self.assertIs(result, doc)

    # --- upload_attachment() ---

    def test_upload_attachment_from_io(self):
        import io
        doc = self._make_doc()
        f = io.BytesIO(b"hello")
        f.name = "note.txt"
        att = doc.upload_attachment(f)
        self.assertEqual(att.filename, "note.txt")
        self.assertIn(att, doc.attachments)

    # --- DocumentAttachment.delete() ---

    def test_attachment_delete_removes_from_list(self):
        doc = self._make_doc(sections=[{
            "Id": "sec1",
            "OriginalFileName": "old.pdf",
            "Links": [{"rel": "self",
                       "href": f"/DocuWare/Platform/FileCabinets/{self.fc_id}/Documents/{self.doc_id}/Sections/sec1"}],
        }])
        att = doc.attachments[0]
        self.assertEqual(len(doc.attachments), 1)
        att.delete()
        self.assertEqual(len(doc.attachments), 0)

    # --- DocumentAttachment.__str__ ---

    def test_attachment_str_representation(self):
        doc = self._make_doc(sections=[{
            "Id": "sec1",
            "OriginalFileName": "report.pdf",
            "ContentType": "application/pdf",
            "Links": [],
        }])
        s = str(doc.attachments[0])
        self.assertIn("report.pdf", s)
        self.assertIn("sec1", s)


if __name__ == "__main__":
    unittest.main()
