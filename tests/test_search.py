import httpx
import unittest
import json
from docuware import DocuwareClient

class TestSearchFlow(unittest.TestCase):
    def setUp(self):
        self.client = DocuwareClient("https://example.com")
        
        def handler(request: httpx.Request):
            path = request.url.path
            if path == "/DocuWare/Platform/Account/Logon":
                return httpx.Response(200, json={"Token": "mock_token"})
            elif path == "/DocuWare/Platform":
                return httpx.Response(200, json={
                    "Links": [
                        {"rel": "organizations", "href": "/DocuWare/Platform/Organizations"}
                    ],
                    "Resources": [],
                    "Version": "7.10"
                })
            elif path == "/DocuWare/Platform/Organizations":
                return httpx.Response(200, json={
                    "Organization": [
                        {
                            "Name": "Test Org", 
                            "Id": "1", 
                            "Links": [
                                {"rel": "filecabinets", "href": "/DocuWare/Platform/Organizations/1/FileCabinets"}
                            ]
                        }
                    ]
                })
            elif path == "/DocuWare/Platform/Organizations/1/FileCabinets":
                 return httpx.Response(200, json={
                    "FileCabinet": [
                        {
                            "Name": "Archive", 
                            "Id": "fc1", 
                            "Links": [
                                {"rel": "dialogs", "href": "/DocuWare/Platform/FileCabinets/fc1/Dialogs"}
                            ]
                        }
                    ]
                })
            elif "/Dialogs" in path and "fc1" in path and not path.endswith("dlg1"):
                return httpx.Response(200, json={
                    "Dialog": [
                        {
                            "DisplayName": "Default Search",
                            "Id": "dlg1",
                            "Type": "Search",
                            "$type": "DialogInfo",
                            "FileCabinetId": "fc1",
                            "Links": [
                                {"rel": "self", "href": "/DocuWare/Platform/FileCabinets/fc1/Dialogs/dlg1"}
                            ]
                        }
                    ]
                })
            elif path.endswith("/dlg1"):
                return httpx.Response(200, json={
                    "Fields": [
                        {"DBFieldName": "COMPANY", "DlgLabel": "Company", "DWFieldType": "String"}
                    ],
                    "Query": {
                        "Links": [
                            {"rel": "dialogExpression", "href": "/DocuWare/Platform/FileCabinets/fc1/Query/DialogExpression"},
                            {"rel": "dialogExpressionLink", "href": "/DocuWare/Platform/FileCabinets/fc1/Query/DialogExpressionLink"}
                        ]
                    }
                })
            elif "/DialogExpressionLink" in path:
                return httpx.Response(200, text="/DocuWare/Platform/Results/123\n")
            elif "/Results/123" in path:
                return httpx.Response(200, json={
                    "Count": {"Value": 1},
                    "Items": [
                        {
                            "Title": "Invoice 1",
                            "Id": "doc1",
                            "ContentType": "application/pdf",
                            "Links": [
                                {"rel": "self", "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1"}
                            ]
                        }
                    ],
                    "Links": []
                })
            elif "/Documents/doc1" in path:
                return httpx.Response(200, json={
                    "Id": "doc1",
                    "Title": "Invoice 1",
                    "Links": [
                         {"rel": "self", "href": "/DocuWare/Platform/FileCabinets/fc1/Documents/doc1"}
                    ]
                })
            return httpx.Response(404)
        
        self.client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))
        
    def test_search_workflow(self):
        # 1. Login
        self.client.login("user", "pass")
        
        # 2. Get FC and Search Dialog
        org = self.client.organization("Test Org")
        fc = org.file_cabinet("Archive")
        dlg = fc.search_dialog("Default Search")
        
        # 3. Perform Search
        results = dlg.search("COMPANY=ACME")
        
        # 4. Verify
        result_list = list(results)
        self.assertEqual(len(result_list), 1)
        self.assertEqual(result_list[0].title, "Invoice 1")
        # SearchResultItem doesn't have .id, it has .document.id
        self.assertEqual(result_list[0].document.id, "doc1")

if __name__ == "__main__":
    unittest.main()
