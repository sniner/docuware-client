import logging
import os
import pathlib
import sys

import docuware
from docuware import connect


def default_credentials_file() -> pathlib.Path:
    default_path = pathlib.Path(".credentials")
    if default_path.exists():
        return default_path
    base = os.environ.get("XDG_CONFIG_HOME")
    if base:
        return pathlib.Path(base) / "docuware-client" / default_path.name
    return pathlib.Path.home() / ".docuware-client.cred"


logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    try:
        client = connect(verify_certificate=False, credentials_file=default_credentials_file())
    except docuware.DocuwareClientException as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print(f"Connected to {client.conn.base_url}")
    print(f"Docuware version: {client.version}")

    for org in client.organizations:
        print(f"Organization: {org.name} ({org.id})")
        for fc in org.file_cabinets:
            print(f"  - File Cabinet: {fc.name} ({fc.id})")
            for dlg in fc.dialogs:
                print(f"    - Dialog: {dlg.name} ({dlg.id})")
                for fld in dlg.fields.values():
                    print(f"      - {fld.name}: {fld.type} ({fld.id})")
        for basket in org.baskets:
            print(f"  - Basket: {basket.name} ({basket.id})")
            for dlg in basket.dialogs:
                print(f"    - Dialog: {dlg.name} ({dlg.id})")
                for fld in dlg.fields.values():
                    print(f"      - {fld.name}: {fld.type} ({fld.id})")


if __name__ == "__main__":
    main()
