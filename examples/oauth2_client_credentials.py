"""OAuth2 Client Credentials login — service-to-service, no browser, no user.

Use this when a backend job, ETL pipeline, scheduled task, or MCP server
needs to talk to DocuWare under its own service identity (no human user
involved). The DocuWare App Registration must be of type "Trusted /
Service Application" and provide a client_secret.

For App-Registration setup (DocuWare side), see `docs/oauth2-setup.md`
(section "Service Application").

Usage:
    export DW_URL=https://acme.docuware.cloud
    export DW_CLIENT_ID=your-client-id
    export DW_CLIENT_SECRET=your-client-secret
    python oauth2_client_credentials.py
"""

from __future__ import annotations

import os
import pathlib

import docuware

CLIENT_ID = os.environ.get("DW_CLIENT_ID", "<your-client-id>")
CLIENT_SECRET = os.environ.get("DW_CLIENT_SECRET", "<your-client-secret>")
DOCUWARE_URL = os.environ.get("DW_URL", "<your-DocuWare-URL>")

STORE_PATH = pathlib.Path.home() / ".config" / "docuware-client" / ".credentials"


def main() -> None:
    with docuware.connect(
        url=DOCUWARE_URL,
        authenticator=docuware.ClientCredentialsAuthenticator(
            client_id=CLIENT_ID,
            client_secret=CLIENT_SECRET,
        ),
        credential_store=docuware.JsonFileCredentialStore(STORE_PATH),
    ) as client:
        print(f"Connected to DocuWare {client.version}")
        for org in client.organizations:
            print(f"  Organization: {org.name}")
            for fc in org.file_cabinets:
                print(f"    - {fc.name}")


if __name__ == "__main__":
    main()
