"""OAuth2 Authorization Code + PKCE login example (native / public client).

This script demonstrates a complete PKCE login flow for a *native* (public)
DocuWare app — first run opens the browser, subsequent runs reuse the
persisted tokens from `~/.config/docuware-client/.credentials`.

The PKCE flow itself, the local callback server, the browser launch, the
state validation, and the token rotation are all handled by
:class:`PkceAuthenticator` inside the library — this script is just the
user-facing wiring.

For App-Registration setup (DocuWare side), see `docs/oauth2-setup.md`.

Usage:
    python oauth2_login.py
"""

from __future__ import annotations

import pathlib

import docuware

CLIENT_ID = "<your-client-id-from-DocuWare-App-Registration>"
DOCUWARE_URL = "<your-DocuWare-URL>"  # e.g. "acme.docuware.cloud"
REDIRECT_PORT = 18923  # must match the Redirect URI in the App Registration

STORE_PATH = pathlib.Path.home() / ".config" / "docuware-client" / ".credentials"


def main() -> None:
    with docuware.connect(
        url=DOCUWARE_URL,
        authenticator=docuware.PkceAuthenticator(
            client_id=CLIENT_ID,
            redirect_port=REDIRECT_PORT,
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
