import unittest

from docuware.structs import ResourcePattern, Endpoints
from docuware.errors import InternalError


class StructTests(unittest.TestCase):

    def test_ResourcePattern(self):
        name = "dialog"
        pattern = "/DocuWare/Platform/FileCabinets/{fcId}/Dialogs/{dlgId}?dialogType={dlgType}"
        url = "/DocuWare/Platform/FileCabinets/A/Dialogs/B?dialogType=C"
        p = ResourcePattern({"Name": name, "UriPattern": pattern,})
        self.assertEqual(p.name, name)
        self.assertEqual(p.pattern, pattern)
        self.assertEqual(p.fields, ["fcId", "dlgId", "dlgType"])
        self.assertEqual(p.apply({"dlgId": "B", "fcId": "A", "dlgType": "C"}), url)
        self.assertRaises(InternalError, p.apply, {"dlgId": "B", "dlgType": "C"}, strict=True)
        self.assertRaises(InternalError, p.apply, {"fcId": "A", "dlgId": "B", "dlgType": "C", "error": "D"}, strict=True)

    ENDPOINT_TEST_DATA = {
        "Links": [
            {
                "rel": "schemaSearch",
                "href": "/DocuWare/Platform/Schema/Search"
            },
            {
                "rel": "uriTemplatesDocumentation",
                "href": "/DocuWare/Platform/Home/UriTemplatesDocumentation"
            },
            {
                "rel": "schemas",
                "href": "/DocuWare/Platform/Schema"
            },
            {
                "rel": "linkModelOverview",
                "href": "/DocuWare/Platform/Content/PlatformLinkModel.pdf"
            },
            {
                "rel": "documentation",
                "href": "/DocuWare/Platform/Documentation",
                "type": "text/html"
            }
        ]
    }

    def test_Endpoints(self):
        ep = Endpoints(self.ENDPOINT_TEST_DATA)
        self.assertEqual(len(ep), 5)
        self.assertEqual(ep["linkModelOvErViEw"], self.ENDPOINT_TEST_DATA["Links"][3]["href"])
        self.assertEqual(ep.get("nothingHere", "ABC"), "ABC")
        self.assertRaises(KeyError, ep.__getitem__, "nothingHere")


if __name__ == "__main__":
    unittest.main()
