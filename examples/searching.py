import json
import logging
import sys
from datetime import date, datetime

import docuware
from docuware import connect, default_credentials_file
from docuware.types import SearchDialogP

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# Suppress verbose logging from httpx and httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def _json_default(obj):
    if isinstance(obj, (date, datetime)):
        return obj.isoformat()
    raise TypeError(f"Object of type {type(obj).__name__} is not JSON serializable")


def demo_search(dlg: SearchDialogP, query, **kwargs):
    print(f"\n--- Searching: {json.dumps(query, default=_json_default)} ---")

    try:
        result = dlg.search(query, **kwargs)
    except docuware.ResourceError as e:
        print(f"Search failed with code {e.status_code}:")
        print(e.server_message)
        print(e.url)
        return

    print(f"Found {result.count} documents.")

    for i, item in enumerate(result):
        if i >= 5:
            print("... (stopping after 5 results)")
            break

        # 'item' is a SearchResultItem
        print(f"\nDocument [{i + 1}]: {item.title or 'No Title'} (ID: {item.document.id})")
        print(f"  Content Type: {item.content_type}")

        # Access fields
        # item.fields is a list of FieldValue objects
        print("  Fields:")
        for field in item.fields:
            if field.value:  # Only print non-empty fields
                print(f"    - {field.name}: {field.value}")


def main():
    # Connect to DocuWare
    # This looks for credentials in:
    # 1. Arguments (if provided)
    # 2. Environment variables (DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG)
    # 3. .credentials file ($XDG_CONFIG_HOME/docuware-client/.credentials or $HOME/.docuware-client.cred)
    try:
        client = connect(verify_certificate=False, credentials_file=default_credentials_file())
    except docuware.DocuwareClientException as e:
        print(f"Connection failed: {e}")
        sys.exit(1)

    print(f"Connected to: {client.conn.base_url}")

    org = next(client.organizations)
    print(f"Organization: {org.name} ({org.id})")
    assert len(org.file_cabinets) > 0
    fc = org.file_cabinet("Archiv")
    assert fc is not None
    print(f"File Cabinet: {fc.name} ({fc.id})")
    dlg = fc.search_dialog()
    assert dlg is not None
    print(f"Search Dialog: {dlg.name} ({dlg.id})")

    # Single field, exact match.
    # Parentheses in the value are escaped automatically (QuoteMode.PARTIAL is the default).
    # Adapt field names to your own file cabinet.
    demo_search(dlg, {"BELEGART": "Lieferschein (ausgehend)"})

    # Range search: a list [from, to] defines a value range.
    # date/datetime objects are converted to ISO 8601 automatically.
    # Values must be in ascending order; both endpoints are inclusive.
    now = datetime.now()
    first_day_of_year = date(now.year, 1, 1)
    today = date.today()
    demo_search(dlg, {"BELEGDATUM": [first_day_of_year, today]})

    # Multiple fields — all conditions must match (AND).
    # Every key in the dict is an additional AND constraint.
    demo_search(
        dlg,
        {
            "BELEGART": "Lieferschein (ausgehend)",
            "FIRMA": "LEONHARD WEISS",
        },
    )

    # Wildcard pattern: * matches any sequence of characters, ? matches one character.
    # Wildcards are preserved by default (QuoteMode.PARTIAL).
    demo_search(dlg, {"FIRMA": "LEONHARD*"})

    # Numeric range: finds all documents where KUNDENNUMMER is between the two values.
    # The first value must be less than or equal to the second, otherwise no results.
    demo_search(dlg, {"KUNDENNUMMER": [625116, 650485]})

    # OR across separate conditions using the list/string form.
    # In string form, escaping is the caller's responsibility — no automatic quoting.
    # Use this form when you need OR across different fields, or OR on numeric fields.
    demo_search(
        dlg,
        ["KUNDENNUMMER=650485", "KUNDENNUMMER=625116"],
        operation=docuware.Operation.OR,
    )


if __name__ == "__main__":
    main()
