import httpx
import unittest
import json
from docuware import DocuwareClient

class TestFileCabinetOperations(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")
        
        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform":
                return httpx.Response(200, json={
                    "Links": [], "Resources": [], "Version": "7.10"
                })
            elif "/Documents" in request.url.path and request.method == "POST":
                # Entry creation (XML)
                return httpx.Response(200, text="Success")
            return httpx.Response(404)

        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        self.client.login("user", "pass")

    def test_create_data_entry(self):
        from docuware.filecabinet import FileCabinet
        
        fc = FileCabinet({
            "Id": "fc1",
            "Links": [{"rel": "documents", "href": "/DocuWare/Platform/FileCabinets/fc1/Documents"}]
        }, None)
        class MockOrg:
            def __init__(self, client): self.client = client
        fc.organization = MockOrg(self.client)
        
        data = {"COMPANY": "ACME", "DOCNO": "123"}
        result = fc.create_data_entry(data)
        self.assertEqual(result, "Success")

if __name__ == "__main__":
    unittest.main()
