"""Archive documents from a DocuWare basket (inbox) to a file cabinet.

This example walks through the inbox-to-archive workflow:

1. Pick an ``Inbox`` basket and an ``Archive`` file cabinet.
2. Inspect the archive's store dialog to learn which index fields are
   mandatory (``NotEmpty``).
3. Pre-check locally and then call :meth:`Document.archive` to move the
   document with the required index values.

Set DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG in the environment, or use a
``.credentials`` file — see ``README.md``.
"""
from __future__ import annotations

from datetime import date

import docuware
from docuware.dialogs import StoreDialog


def main() -> None:
    dw = docuware.connect()
    org = next(iter(dw.organizations))

    basket = org.basket("Inbox", required=True)
    archive = org.file_cabinet("Archive", required=True)

    # Find the archive's (default) store dialog so we can inspect field rules.
    store_dlg = next(
        (dlg for dlg in archive.dialogs if isinstance(dlg, StoreDialog)),
        None,
    )
    if store_dlg is not None:
        print("Mandatory fields on the archive:")
        for fid, f in store_dlg.required_fields.items():
            detail = f"{f.type}"
            if f.length > 0:
                detail += f"({f.length})"
            if f.mask:
                detail += f", mask={f.mask!r}"
            print(f"  - {fid} [{f.name}] {detail}")

    # Values we will assign to the first document in the basket.
    index_values = {
        "DOCTYPE": "Invoice",
        "COMPANY": "ACME GmbH",
        "DOCDATE": date.today(),
    }

    if store_dlg is not None:
        missing = store_dlg.validate_fields(index_values)
        if missing:
            raise SystemExit(f"Missing required fields for archive: {missing}")

    # Take the first document in the basket via its search dialog.
    search = basket.search_dialog(required=True)
    items = iter(search.search({}))  # empty query: all documents
    try:
        first = next(items)
    except StopIteration:
        print("Basket is empty — nothing to archive.")
        return

    doc = first.document
    print(f"Archiving {doc} → {archive}")
    archived = doc.archive(archive, fields=index_values)
    print(f"Stored as {archived}")


if __name__ == "__main__":
    main()
