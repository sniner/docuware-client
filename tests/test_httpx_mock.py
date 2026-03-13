import unittest

import httpx

from docuware import DocuwareClient


class TestHttpxMigration(unittest.TestCase):
    def test_mock_login_and_orgs(self):
        # Define the mock responses
        def handler(request: httpx.Request):
            if request.url.path == "/DocuWare/Platform/Home/IdentityServiceInfo":
                return httpx.Response(200, json={"IdentityServiceUrl": "https://example.com/DocuWare/Identity"})
            elif request.url.path == "/DocuWare/Identity/.well-known/openid-configuration":
                return httpx.Response(200, json={"token_endpoint": "/DocuWare/Identity/connect/token"})
            elif request.url.path == "/DocuWare/Identity/connect/token":
                return httpx.Response(200, json={"access_token": "mock_token"})
            elif request.url.path == "/DocuWare/Platform":
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
            elif request.url.path == "/DocuWare/Platform/Organizations":
                return httpx.Response(
                    200, json={"Organization": [{"Name": "Test Org", "Id": "1", "Links": []}]}
                )
            return httpx.Response(404)

        # Create client with MockTransport
        client = DocuwareClient("https://example.com")
        # Inject mock transport into the session
        client.conn.session = httpx.Client(transport=httpx.MockTransport(handler))

        # Perform login (mocked)
        client.login("user", "pass")

        # Verify organizations call
        orgs = list(client.organizations)
        self.assertEqual(len(orgs), 1)
        self.assertEqual(orgs[0].name, "Test Org")


if __name__ == "__main__":
    unittest.main()
