import unittest
from unittest.mock import MagicMock

import httpx

from docuware import DocuwareClient, TextShot
from docuware.document import Document
from docuware.filecabinet import FileCabinet
from docuware.textshot import TextLine, TextPage, TextZone, Word
from docuware.types import OrganizationP


# A small handcrafted payload that matches the structure of a real
# /Sections/{id}/Textshot response (intellix:DocumentContent).
SAMPLE_TEXTSHOT = {
    "Pages": [
        {
            "$type": "PageContent",
            "Lang": "de-DE",
            "SizeX": 2480,
            "SizeY": 3507,
            "HorizontalDpi": 300,
            "VerticalDpi": 300,
            "SkewAngle": 0.0,
            "Rotation": "Rotate0Degree",
            "Items": [
                {
                    "$type": "TextZone",
                    "Ln": [
                        {
                            "Items": [
                                {"$type": "Word", "Value": "Hello", "L": 100, "T": 200, "W": 300, "H": 40},
                                {"$type": "Space", "W": 30},
                                {"$type": "Word", "Value": "World", "L": 430, "T": 200, "W": 300, "H": 40},
                            ]
                        },
                        {
                            "Items": [
                                {"$type": "Word", "Value": "Line2", "L": 100, "T": 260, "W": 300, "H": 40},
                            ]
                        },
                    ],
                },
                {
                    "$type": "PictureZone",  # must be ignored
                    "L": 0, "T": 0, "W": 100, "H": 100,
                },
            ],
        },
        {
            "$type": "PageContent",
            "Lang": "en",
            "SizeX": 100,
            "SizeY": 100,
            "Items": [
                {
                    "$type": "TextZone",
                    "Ln": [
                        {"Items": [{"$type": "Word", "Value": "Page2"}]},
                    ],
                },
            ],
        },
    ]
}


class TestTextShotParsing(unittest.TestCase):
    def test_top_level_shape(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        self.assertEqual(len(ts.pages), 2)
        self.assertIsInstance(ts.pages[0], TextPage)

    def test_page_attributes(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        p0 = ts.pages[0]
        self.assertEqual(p0.language, "de-DE")
        self.assertEqual(p0.width, 2480)
        self.assertEqual(p0.height, 3507)
        self.assertEqual(p0.dpi_x, 300)
        self.assertEqual(p0.rotation, "Rotate0Degree")

    def test_picture_zone_is_ignored(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        # PictureZone is in Items but only TextZone should populate .zones
        self.assertEqual(len(ts.pages[0].zones), 1)
        self.assertIsInstance(ts.pages[0].zones[0], TextZone)

    def test_lines_and_words(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        zone = ts.pages[0].zones[0]
        self.assertEqual(len(zone.lines), 2)
        self.assertIsInstance(zone.lines[0], TextLine)

        line0 = zone.lines[0]
        # Space items are skipped; only Words land in .words
        self.assertEqual(len(line0.words), 2)
        self.assertIsInstance(line0.words[0], Word)
        self.assertEqual(line0.words[0].value, "Hello")
        self.assertEqual(line0.words[0].left, 100)
        self.assertEqual(line0.words[0].top, 200)

    def test_flat_text(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        # words within a line are space-joined, lines by \n, zones by \n, pages by \f
        expected = "Hello World\nLine2\fPage2"
        self.assertEqual(ts.text, expected)

    def test_words_iterator(self):
        ts = TextShot(SAMPLE_TEXTSHOT)
        words = [w.value for w in ts.words()]
        self.assertEqual(words, ["Hello", "World", "Line2", "Page2"])

    def test_empty_payload(self):
        ts = TextShot({})
        self.assertEqual(ts.pages, [])
        self.assertEqual(ts.text, "")
        self.assertEqual(list(ts.words()), [])

    def test_word_defaults(self):
        w = Word({"Value": "x"})
        self.assertEqual(w.value, "x")
        self.assertEqual(w.left, 0)
        self.assertEqual(w.top, 0)
        self.assertEqual(w.width, 0)
        self.assertEqual(w.height, 0)
        self.assertFalse(w.bold)
        self.assertIsNone(w.font_size)


class TestAttachmentTextshot(unittest.TestCase):
    """Exercise DocumentAttachment.textshot()/text() end-to-end with httpx mock."""

    def setUp(self):
        self.client = DocuwareClient("https://example.com")

        def handler(request: httpx.Request):
            path = request.url.path
            if path == "/DocuWare/Platform/Home/IdentityServiceInfo":
                return httpx.Response(
                    200, json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"}
                )
            if path == "/DocuWare/Identity/.well-known/openid-configuration":
                return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
            if path == "/DocuWare/Identity/connect/token":
                return httpx.Response(200, json={"access_token": "mock_token"})
            if path == "/DocuWare/Platform":
                return httpx.Response(200, json={"Links": [], "Resources": [], "Version": "7.11"})
            if path == "/DocuWare/Platform/FileCabinets/fc1/Sections/sec1":
                return httpx.Response(
                    200,
                    json={
                        "Id": "sec1",
                        "Links": [
                            {
                                "rel": "self",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Sections/sec1",
                            },
                            {
                                "rel": "textshot",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Sections/sec1/Textshot",
                            },
                        ],
                    },
                )
            if path == "/DocuWare/Platform/FileCabinets/fc1/Sections/sec1/Textshot":
                return httpx.Response(200, json=SAMPLE_TEXTSHOT)
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        self.client.login("user", "pass")

        mock_org = MagicMock(spec=OrganizationP)
        mock_org.client = self.client
        self.fc = FileCabinet({"Id": "fc1"}, mock_org)
        self.doc = Document(
            {
                "Id": "doc1",
                "Sections": [
                    {
                        "Id": "sec1",
                        "OriginalFileName": "test.pdf",
                        "Links": [
                            {
                                "rel": "self",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Sections/sec1",
                            }
                        ],
                    }
                ],
            },
            self.fc,
        )

    def test_textshot_returns_class(self):
        att = self.doc.attachments[0]
        ts = att.textshot()
        self.assertIsInstance(ts, TextShot)
        self.assertEqual(len(ts.pages), 2)

    def test_text_shortcut(self):
        att = self.doc.attachments[0]
        self.assertEqual(att.text(), "Hello World\nLine2\fPage2")

    def test_missing_textshot_endpoint(self):
        # Attachment whose Section response carries no textshot link
        doc = Document(
            {
                "Id": "doc2",
                "Sections": [
                    {
                        "Id": "sec_no_ts",
                        "Links": [
                            {
                                "rel": "self",
                                "href": "/DocuWare/Platform/FileCabinets/fc1/Sections/no_ts",
                            }
                        ],
                    }
                ],
            },
            self.fc,
        )

        # Mock returns 404 for that section URL, so _fetch_endpoints will fail.
        # To test the "no textshot endpoint" path cleanly, install a section
        # response without a textshot link.
        original = self.client.conn.session

        def handler(request: httpx.Request):
            path = request.url.path
            if path == "/DocuWare/Platform/FileCabinets/fc1/Sections/no_ts":
                return httpx.Response(
                    200,
                    json={
                        "Id": "sec_no_ts",
                        "Links": [
                            {
                                "rel": "fileDownload",
                                "href": "/whatever",
                            }
                        ],
                    },
                )
            return original.send(request)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))

        att = doc.attachments[0]
        from docuware.errors import DataError
        with self.assertRaises(DataError):
            att.textshot()


if __name__ == "__main__":
    unittest.main()
