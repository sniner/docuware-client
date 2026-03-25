"""OAuth2 Authorization Code + PKCE login example for DocuWare.

This script demonstrates a complete interactive PKCE login flow using the
docuware-client library.  It is intended for developers and administrators
who want to understand or test OAuth2 authentication against a DocuWare
instance — for example, when building a new integration or verifying an
App Registration.

PREREQUISITES — DocuWare App Registration
==========================================

Before running this script, a Native Application must be registered in
DocuWare:

  DocuWare Configuration → Integrations → App Registration → Add

Settings:
  App type:     Native application
  Grant type:   Authorization Code with PKCE
  Client ID:    a UUID assigned by DocuWare when you create the registration
                (copy it — you will need it below)

  URL Redirects (Redirect URIs):
    http://localhost:18923/callback

  IMPORTANT: DocuWare validates the redirect URI exactly, including the port
  number.  The default port used by this script is 18923.  If you change
  CALLBACK_PORT below, update the App Registration to match.

  Scopes:
    docuware.platform  openid  dwprofile  offline_access

  Refresh token:  enabled

HOW IT WORKS
============

1. The script discovers the authorization and token endpoints automatically
   from the DocuWare instance (via IdentityServiceInfo + OpenID Connect
   discovery) — no manual endpoint configuration needed.
2. It starts a temporary local HTTP server on CALLBACK_PORT.
3. It opens your browser to the DocuWare login page.
4. After you log in, DocuWare redirects to http://localhost:<port>/callback
   with an authorization code.
5. The script exchanges the code for an access token and a refresh token
   and prints both to stdout.

Usage:
    python oauth2_login.py
"""

from __future__ import annotations

import http.server
import secrets
import time
import urllib.parse
import webbrowser

import docuware

CALLBACK_PORT = 18923
CALLBACK_PATH = "/callback"
REDIRECT_URI = f"http://localhost:{CALLBACK_PORT}{CALLBACK_PATH}"


# ---------------------------------------------------------------------------
# Local callback server
# ---------------------------------------------------------------------------


class _CallbackHandler(http.server.BaseHTTPRequestHandler):
    """Minimal HTTP handler that captures the OAuth2 callback."""

    code: str | None = None
    state: str | None = None
    error: str | None = None

    def do_GET(self) -> None:
        parsed = urllib.parse.urlparse(self.path)
        if parsed.path != CALLBACK_PATH:
            self.send_response(404)
            self.end_headers()
            return

        params = urllib.parse.parse_qs(parsed.query)
        cls = type(self)
        cls.code = params.get("code", [None])[0]
        cls.state = params.get("state", [None])[0]
        cls.error = params.get("error", [None])[0]

        self.send_response(200)
        self.send_header("Content-Type", "text/html; charset=utf-8")
        self.end_headers()
        if cls.error:
            self.wfile.write(
                b"<h1>Login failed</h1><p>Please close this window and try again.</p>"
            )
        else:
            self.wfile.write(b"<h1>Login successful!</h1><p>You can close this window.</p>")

    def log_message(self, format: str, *args: object) -> None:  # noqa: A002
        pass  # suppress request logging


# ---------------------------------------------------------------------------
# Main flow
# ---------------------------------------------------------------------------


def main() -> None:
    print()
    print("DocuWare OAuth2 PKCE Login — Example")
    print("=" * 40)
    print()
    print("This script will:")
    print("  1. Discover authorization endpoints from your DocuWare instance")
    print("  2. Open your browser for DocuWare login")
    print(f"  3. Receive the callback on http://localhost:{CALLBACK_PORT}")
    print("  4. Exchange the code for access + refresh tokens")
    print()
    print(f"Make sure http://localhost:{CALLBACK_PORT}/callback is registered")
    print("as a Redirect URI in your DocuWare App Registration.")
    print()

    # --- Step 1: collect inputs ---
    url_input = input("DocuWare URL or hostname (e.g. acme.docuware.cloud): ").strip()
    if not url_input:
        print("Error: URL is required.")
        return
    docuware_url = docuware.normalize_docuware_url(url_input)
    print(f"  → {docuware_url}")
    print()

    client_id = input("Client ID (from App Registration): ").strip()
    if not client_id:
        print("Error: Client ID is required.")
        return
    print()

    # --- Step 2: discover endpoints ---
    print("Discovering OAuth2 endpoints...")
    try:
        endpoints = docuware.discover_oauth_endpoints(docuware_url)
    except RuntimeError as exc:
        print(f"Error: {exc}")
        return
    print(f"  Authorization endpoint: {endpoints.authorization_endpoint}")
    print(f"  Token endpoint:         {endpoints.token_endpoint}")
    print()

    # --- Step 3: PKCE setup ---
    verifier, challenge = docuware.generate_pkce()
    state = secrets.token_urlsafe(32)
    auth_url = docuware.build_authorization_url(
        endpoints.authorization_endpoint, client_id, REDIRECT_URI, challenge, state,
    )

    # --- Step 4: start callback server and open browser ---
    _CallbackHandler.code = None
    _CallbackHandler.state = None
    _CallbackHandler.error = None

    server = http.server.HTTPServer(("127.0.0.1", CALLBACK_PORT), _CallbackHandler)

    print("Opening browser for DocuWare login...")
    print(f"Waiting for callback on port {CALLBACK_PORT} (timeout: 120 s) ...")
    print()
    webbrowser.open(auth_url)

    # Loop until the callback arrives or the deadline passes.
    # A single handle_request() is not enough — browsers often fire a
    # /favicon.ico request first, which would consume the only call.
    deadline = time.time() + 120
    while _CallbackHandler.code is None and _CallbackHandler.error is None:
        remaining = deadline - time.time()
        if remaining <= 0:
            break
        server.timeout = remaining
        server.handle_request()
    server.server_close()

    # --- Step 5: validate callback ---
    if _CallbackHandler.error:
        print(f"Error from DocuWare: {_CallbackHandler.error}")
        return
    if _CallbackHandler.code is None:
        print("Timed out — no callback received.")
        return
    if _CallbackHandler.state != state:
        print("State mismatch — possible CSRF. Aborting.")
        return

    # --- Step 6: exchange code for tokens ---
    print("Exchanging authorization code for tokens...")
    try:
        tokens = docuware.exchange_pkce_code(
            code=_CallbackHandler.code,
            code_verifier=verifier,
            redirect_uri=REDIRECT_URI,
            token_endpoint=endpoints.token_endpoint,
            client_id=client_id,
        )
    except Exception as exc:
        print(f"Token exchange failed: {exc}")
        return

    print()
    print("Success! Tokens obtained:")
    print(f"  access_token:  {tokens['access_token'][:40]}...")
    print(f"  refresh_token: {tokens.get('refresh_token', '(none)')[:40]}...")
    print(f"  expires_in:    {tokens.get('expires_in')} seconds")
    print()

    # --- Step 7: connect and verify ---
    print("Connecting to DocuWare with the obtained tokens...")
    try:
        client = docuware.connect_with_tokens(
            url=docuware_url,
            access_token=tokens["access_token"],
            refresh_token=tokens.get("refresh_token", ""),
            token_endpoint=endpoints.token_endpoint,
            client_id=client_id,
        )
    except Exception as exc:
        print(f"Connection failed: {exc}")
        return

    print(f"Connected to {client.conn.base_url}  (DocuWare {client.version})")
    print()
    print("File cabinets:")
    for org in client.organizations:
        print(f"  Organization: {org.name}")
        for fc in org.file_cabinets:
            print(f"    - {fc.name}")
    print()
    print("Reusable snippet for your own code:")
    print()
    print("  import docuware")
    print("  client = docuware.connect_with_tokens(")
    print(f"      url={docuware_url!r},")
    print("      access_token=tokens['access_token'],")
    print("      refresh_token=tokens['refresh_token'],")
    print(f"      token_endpoint={endpoints.token_endpoint!r},")
    print(f"      client_id={client_id!r},")
    print("  )")
    print()


if __name__ == "__main__":
    main()
