import logging
import sys

from docuware import connect

# Setup logging to see what's happening
logging.basicConfig(level=logging.INFO, stream=sys.stderr)

# Suppress verbose logging from httpx and httpcore
logging.getLogger("httpx").setLevel(logging.WARNING)
logging.getLogger("httpcore").setLevel(logging.WARNING)


def main():
    # Connect to DocuWare
    # This looks for credentials in:
    # 1. Arguments (if provided)
    # 2. Environment variables (DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG)
    # 3. .credentials file in the current directory or config dir
    # 4. .session file (reusing previous login)
    try:
        client = connect(verify_certificate=False)
    except ValueError as e:
        print(f"Connection failed: {e}")
        print(
            "Please provide credentials via arguments, environment variables, or a .credentials file."
        )
        sys.exit(1)

    print(f"Connected to {client.conn.base_url}")

    # List all organizations and their file cabinets
    print("\n--- Organizations & File Cabinets ---")
    first_org_id = ""
    for org in client.organizations:
        print(f"Organization: {org.name} ({org.id})")
        if not first_org_id:
            first_org_id = org.id
        for fc in org.file_cabinets:
            print(f"  - File Cabinet: {fc.name} ({fc.id})")

    # Work with a specific organization and file cabinet
    # Update these IDs/Names to match your system!
    FC_ID = "Documents"  # Common default file cabinet name

    org = client.organization(first_org_id)
    if not org:
        print(f"\nOrganization '{first_org_id}' not found.")
        return

    fc = org.file_cabinet(FC_ID)
    if not fc:
        print(f"\nFile cabinet '{FC_ID}' not found in organization '{org.name}'.")
        # Try to pick the first one available
        try:
            fc = next(org.file_cabinets)
            print(f"Using first available file cabinet: {fc.name}")
        except StopIteration:
            print("No file cabinets found.")
            return

    # Use a dialog to search
    # "Search" is the default name for the standard search dialog
    dialog = fc.search_dialog("Search")
    if not dialog:
        # Fallback: use any available search dialog
        dialog = fc.search_dialog()

    if not dialog:
        print(f"No search dialog found for '{fc.name}'.")
        return

    print(f"\n--- Searching in '{fc.name}' using '{dialog.name}' ---")

    # Example search: Find all documents (modified recently if possible, or just all)
    # You can pass a query string like "DOCTYPE=Invoice" or a dictionary
    try:
        # Search for everything (careful with large archives!)
        # Using a limit is a good practice, though handling it in the loop is easier here
        search_results = dialog.search(conditions=[])

        print(f"Found {search_results.count} documents.")

        for i, item in enumerate(search_results):
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

            # You can also access the full document object for more details
            # doc = item.document
            # print(f"  Created at: {doc.created}")

    except Exception as e:
        print(f"Search failed: {e}")


if __name__ == "__main__":
    main()
