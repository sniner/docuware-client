"""Custom CredentialStore example: SQLite-backed token storage.

Shows how to subclass :class:`docuware.CredentialStore` with a database
backend instead of the default JSON file. The same pattern applies to any
other transactional storage (PostgreSQL, MySQL, …).

Highlights:

* :meth:`save` is atomic. A single UPSERT inside ``BEGIN IMMEDIATE`` takes
  the write lock up front, so no concurrent reader can observe a
  half-written state. ``COMMIT`` is the visibility point.
* The ``key`` column makes the store multi-tenant: one row per logical
  identity (user, tenant, service account). Default key is ``"default"``;
  pass any other string (e.g. ``key=f"tenant-{tenant_id}"``) to keep
  credentials for separate identities side-by-side in the same database.

For App-Registration setup (DocuWare side), see ``docs/oauth2-setup.md``.

Usage:
    python credential_store_sqlite.py
"""

from __future__ import annotations

import json
import pathlib
import sqlite3
from typing import Any, Dict, Optional

import docuware

CLIENT_ID = "<your-client-id-from-DocuWare-App-Registration>"
DOCUWARE_URL = "<your-DocuWare-URL>"  # e.g. "acme.docuware.cloud"
REDIRECT_PORT = 18923  # must match the Redirect URI in the App Registration

DB_PATH = pathlib.Path.home() / ".local" / "share" / "docuware-client" / "credentials.sqlite3"


class SqliteCredentialStore(docuware.CredentialStore):
    """CredentialStore backed by a single-row-per-key SQLite table.

    Pass ``key="tenant-42"`` (or any other string) to keep multiple
    identities side-by-side in the same database.
    """

    _SCHEMA = (
        "CREATE TABLE IF NOT EXISTS dw_credentials ("
        "    key    TEXT PRIMARY KEY,"
        "    bundle TEXT NOT NULL"
        ")"
    )

    def __init__(self, conn: sqlite3.Connection, key: str = "default") -> None:
        self.conn = conn
        self.key = key
        # We manage transactions explicitly in save() so we can issue
        # BEGIN IMMEDIATE. Don't share this connection with code that
        # relies on Python's implicit transaction handling — give that
        # code its own connection.
        self.conn.isolation_level = None
        self.conn.execute(self._SCHEMA)

    def load(self) -> Optional[Dict[str, Any]]:
        cur = self.conn.execute(
            "SELECT bundle FROM dw_credentials WHERE key = ?",
            (self.key,),
        )
        row = cur.fetchone()
        return json.loads(row[0]) if row else None

    def save(self, bundle: Dict[str, Any]) -> None:
        # BEGIN IMMEDIATE acquires the write lock up front so no concurrent
        # writer can sneak in between statements. For a single-statement
        # save() this is paranoid; for any save() that grows to multiple
        # statements, it's what keeps the whole bundle atomic.
        self.conn.execute("BEGIN IMMEDIATE")
        try:
            self.conn.execute(
                "INSERT INTO dw_credentials (key, bundle) VALUES (?, ?) "
                "ON CONFLICT(key) DO UPDATE SET bundle = excluded.bundle",
                (self.key, json.dumps(bundle)),
            )
        except Exception:
            self.conn.execute("ROLLBACK")
            raise
        self.conn.execute("COMMIT")


def main() -> None:
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    conn = sqlite3.connect(DB_PATH)
    try:
        # In a multi-tenant setup, derive `key` from the active tenant —
        # e.g. key=f"tenant-{tenant_id}" — and instantiate one store per
        # request.
        store = SqliteCredentialStore(conn, key="default")

        with docuware.connect(
            url=DOCUWARE_URL,
            authenticator=docuware.PkceAuthenticator(
                client_id=CLIENT_ID,
                redirect_port=REDIRECT_PORT,
            ),
            credential_store=store,
        ) as client:
            print(f"Connected to DocuWare {client.version}")
            for org in client.organizations:
                print(f"  Organization: {org.name}")
                for fc in org.file_cabinets:
                    print(f"    - {fc.name}")
    finally:
        conn.close()


if __name__ == "__main__":
    main()
