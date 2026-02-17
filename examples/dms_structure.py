import logging
import sys

from docuware import connect

logging.basicConfig(level=logging.INFO, stream=sys.stderr)
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    try:
        client = connect(verify_certificate=False)
    except ValueError as e:
        print(f"Connection failed: {e}")
        print(
            "Please provide credentials via arguments, environment variables, or a .credentials file."
        )
        sys.exit(1)

    print(f"Connected to {client.conn.base_url}")
    print(f"Docuware version: {client.version}")

    for org in client.organizations:
        print(f"Organization: {org.name} ({org.id})")
        for fc in org.file_cabinets:
            print(f"  - File Cabinet: {fc.name} ({fc.id})")
            for dlg in fc.dialogs:
                print(f"    - Search Dialog: {dlg.name} ({dlg.id})")
                for fld in dlg.fields.values():
                    print(f"      - {fld.name}: {fld.type} ({fld.id})")


if __name__ == "__main__":
    main()
