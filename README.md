# docuware-client

This is a client library for the REST API of [DocuWare][1] DMS. Since
DocuWare provides no official developer documentation for the REST API beyond
XSD schema files, this client covers only a part of the API's functionality.

Please keep in mind: **This is an independent project with no affiliation to
DocuWare GmbH.** It is a work in progress, may yield unexpected results, and
almost certainly contains bugs.

> **Breaking change in 0.7.0 — OAuth2 only**
>
> Starting with version 0.7.0, **only OAuth2 authentication is supported.**
> Cookie-based authentication has been removed completely.
> If you rely on cookie authentication, please stay on version **0.6.x**.
>
> OAuth2 requires DocuWare 7.10 or later. Credentials are stored in a
> `.credentials` file; the `.session` file is no longer created or used.

## Usage

The recommended way to connect is via `docuware.connect()`, which resolves
credentials from arguments, environment variables, or a `.credentials` file
and handles login automatically:

```python
import docuware

# Credentials from arguments:
dw = docuware.connect(url="http://localhost", username="...", password="...", organization="...")

# Or from environment variables DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG:
dw = docuware.connect()

# Or from a .credentials file:
dw = docuware.connect(credentials_file="/path/to/.credentials")
```

Credentials are saved automatically to the file specified by `credentials_file`
after a successfull login.

For more control, use `DocuwareClient` and `login()` explicitly:

```python
import docuware

dw = docuware.Client("http://localhost")
dw.login("username", "password", "organization")
```

Iterate over the organizations and file cabinets and baskets:

```python
for org in dw.organizations:
    print(org)
    for fc in org.file_cabinets:
        print("   ", fc)
    for b in org.baskets:
        print("   ", b)
```

If you already know the ID or name of the objects, you can also access them
directly.

```python
org = dw.organization("1")
fc = org.file_cabinet("Archive")
basket = org.basket("Inbox")
# If you know the ID:
doc = fc.get_document("123456")
```

Now some examples of how to search for documents. First you need a search
dialog:

```python
# Let's use the first one:
dlg = fc.search_dialog()
# Or a specific search dialog:
dlg = fc.search_dialog("Default search dialog")
```

Each search term consists of a field name and a search pattern. Each search
dialog knows its fields:

```python
for field in dlg.fields.values():
    print("Id    =", field.id)
    print("Length=", field.length)
    print("Name  =", field.name)
    print("Type  =", field.type)
    print("-------")
```

Let's search for some documents:

```python
# Search for DOCNO equal to '123456':
for result in dlg.search("DOCNO=123456"):
    print(result)
# Search for two patterns alternatively:
for result in dlg.search(["DOCNO=123456", "DOCNO=654321"], operation=docuware.Operation.OR):
    print(result)
# Search for documents in a date range (01-31 January 2023):
for result in dlg.search("DWSTOREDATETIME=2023-01-01T00:00:00,2023-02-01T00:00:00"):
    print(result)
```

DocuWare search values may contain metacharacters such as `(`, `)`, `*`, and
`?`. When using the **dict form**, parentheses are automatically escaped by
default so that literal values just work:

```python
# Parentheses are escaped automatically — no 422 error:
for result in dlg.search({"DOCTYPE": "Invoice (incoming)"}):
    print(result)
```

The escaping behaviour is controlled by the `quote` parameter
(`QuoteMode.PARTIAL` by default):

- **`QuoteMode.PARTIAL`** *(default)*: escapes `(` and `)`, but leaves
  wildcard characters `*` and `?` intact.
- **`QuoteMode.ALL`**: also escapes `*` and `?` when they must be treated as
  literals.
- **`QuoteMode.NONE`**: no automatic escaping — use when you need full control
  over the value syntax.

```python
import docuware

dlg.search({"NAME": "Müller*"})                           # wildcard preserved
dlg.search({"NAME": "50%"}, quote=docuware.QuoteMode.NONE)     # no escaping
dlg.search({"NAME": "a*b"}, quote=docuware.QuoteMode.ALL)      # * escaped
```

Passing `None` as a field value searches for documents where that field is
empty (`EMPTY()`).

The **string and list forms** are raw condition strings — escaping is the
caller's responsibility:

```python
# Manual escaping required in string/list form:
for result in dlg.search("DOCTYPE=Invoice \\(incoming\\)"):
    print(result)
```

Search terms can be as simple as a single string, but can also be more complex.
The following two queries are equivalent:

```python
dlg.search(["FIELD1=TERM1,TERM2", "FIELD2=TERM3"])
dlg.search({"FIELD1": ["TERM1", "TERM2"], "FIELD2": ["TERM3"]})
```

When a field value is a **list of two elements**, DocuWare interprets it as a
**range search** (`TERM1 ≤ field ≤ TERM2`). The first value must be less than
or equal to the second. This applies to all field types — dates, numbers, and
strings alike. `date` and `datetime` objects are converted to ISO 8601
automatically:

```python
from datetime import date
# Documents with DOCDATE in January 2023:
dlg.search({"DOCDATE": [date(2023, 1, 1), date(2023, 1, 31)]})
# Documents with CUSTOMERNO between 1000 and 2000:
dlg.search({"CUSTOMERNO": [1000, 2000]})
# Open-ended ranges — use None for the missing bound:
dlg.search({"DOCDATE": [date(2023, 1, 1), None]})   # from 2023-01-01 onwards
dlg.search({"DOCDATE": [None, date(2023, 12, 31)]})  # up to 2023-12-31
```

To match a field against a set of **discrete values**, use separate conditions
with `operation=docuware.Operation.OR`:

```python
dlg.search(["CUSTOMERNO=1234", "CUSTOMERNO=5678"], operation=docuware.Operation.OR)
```

The result of a search is always an iterator over the search results, even if
no result was obtained. Each individual search result holds a `document`
attribute, which gives access to the document in the archive. The document
itself can be downloaded as a whole or only individual attachments.

```python
for result in dlg.search("DOCNO=123456"):
    doc = result.document
    # Download the complete document ...
    data, content_type, filename = doc.download(keep_annotations=True)
    docuware.write_binary_file(data, filename)
    # ... or individual attachments (or sections, as DocuWare calls them)
    for att in doc.attachments:
        data, content_type, filename = att.download()
        docuware.write_binary_file(data, filename)
```

Create a new document with index fields:

```python
data = {
    "Subject": "My Document",
    "Date": "2023-01-01",
}
# Create document:
doc = fc.create_document(fields=data)
# Add a file as attachment to the new document:
doc.upload_attachment("path/to/file.pdf")
```

Update index fields of a document:

```python
doc.update({"Status": "Approved", "Amount": 120.0})
```

Delete documents:

```python
dlg = fc.search_dialog()
for result in dlg.search(["FIELD1=TERM1,TERM2", "FIELD2=TERM3"]):
    document = result.document
    document.delete()
```

### Archiving a document from a basket (inbox) to a file cabinet

Archiving is the inbox-to-archive workflow: a document sitting in a DocuWare
basket (document tray / "Inbox") is transferred into a proper file cabinet,
at which point the mandatory index fields of that cabinet must be filled in.
Under the hood this maps to a `POST` on the destination cabinet's `transfer`
relation — the same operation the DocuWare REST API exposes as
`FileCabinetTransferInfo` / `DocumentsTransferInfo`.

The simplest case — move a single document:

```python
basket = org.basket("Inbox", required=True)
archive = org.file_cabinet("Archive", required=True)

doc = basket.get_document("42")
archived = doc.archive(archive)     # default: keep_source=False → move
# `doc` is now marked as deleted; `archived` is the document in the archive.
```

If the archive requires index fields the source document doesn't have (this
is the common case — inbox documents usually carry little or no index data),
pass them via `fields=`:

```python
from datetime import date

archived = doc.archive(
    archive,
    fields={
        "DOCTYPE":  "Invoice",
        "COMPANY":  "ACME GmbH",
        "DOCDATE":  date(2026, 4, 22),
        "AMOUNT":   199.90,
    },
)
```

Keys may be either the database field name (`DBFieldName`) or the dialog
label. Values are serialised according to their Python type (`str`, `int`,
`float`, `bool`, `date`/`datetime`).

Pass `keep_source=True` to **copy** instead of move:

```python
# Document stays in the basket; a copy is created in the archive
archived = doc.archive(archive, keep_source=True)
```

Additional flags mirror the DocuWare API:

- `fill_intellix=True` — apply Intellix index-data suggestions on the
  destination cabinet's default assigned dialog.
- `use_default_dialog=True` — use the user's default store dialog for the
  destination (affects default values and validation).

#### Mandatory fields and validation

The destination cabinet's **store dialog** determines which fields must be
filled when a document is archived. The server enforces this and rejects the
transfer with a `ResourceError` if requirements aren't met. Each field's
settings are exposed on the store dialog's fields:

| Attribute          | Meaning                                                    |
|--------------------|------------------------------------------------------------|
| `not_empty` / `required` | Field must have a value (DocuWare's `NotEmpty`). |
| `length`           | Maximum length of text fields.                             |
| `mask`             | Regular expression the value must match.                   |
| `mask_error_text`  | Human-readable message if the mask doesn't match.          |
| `read_only`        | Field cannot be set by the client.                         |
| `select_list_only` | Value must come from the field's select list.              |

You can inspect the store dialog of the destination cabinet up front and run
a client-side pre-check before calling `archive()`:

```python
store_dlg = next(
    dlg for dlg in archive.dialogs
    if isinstance(dlg, docuware.dialogs.StoreDialog)
)

# List the fields DocuWare will insist on:
for fid, f in store_dlg.required_fields.items():
    print(f"required: {fid} ({f.name}, {f.type})")

# Pre-check the values you're about to submit:
values = {"DOCTYPE": "Invoice", "COMPANY": "ACME"}
missing = store_dlg.validate_fields(values)
if missing:
    raise RuntimeError(f"Still missing: {missing}")

doc.archive(archive, fields=values)
```

`validate_fields()` is a best-effort local check against the field-level
`NotEmpty` flag; the authoritative validation (mask, length, dialog-level
mandatory rules added in 7.1+, conditional rules, user rights) still happens
on the server.

#### Archiving several documents at once

For batch archiving — for example, processing all documents currently in a
basket — use the destination cabinet's `transfer()` method directly:

```python
# Move every document out of the basket into the archive, tagging them all
# with the same DOCTYPE:
docs_to_archive = [
    {"id": d.id, "fields": {"DOCTYPE": "Invoice"}}
    for d in basket_docs
]
archived_docs = archive.transfer(
    source=basket,
    documents=docs_to_archive,
    keep_source=False,
)
```

Items may be plain ids, `Document` objects, or mappings with per-document
field overrides (as shown above). If no item carries overrides, the client
sends the smaller `FileCabinetTransferInfo` body and the source document's
existing index data is preserved on the destination.


Users and groups of an organisation can be accessed and managed:

```python
# Iterate over the list of users and groups:
for user in org.users:
    print(user)
for group in org.groups:
    print(group)

# Find a specific user:
user = org.users["John Doe"]  # or: org.users.get("John Doe")

# Add a user to a group:
group = org.groups["Managers"]  # or: org.groups.get("Managers")
group.add_user(user)
# or
user.add_to_group(group)

# Deactivate user:
user.active = False # or True to activate user

# Create a new user:
user = docuware.User(first_name="John", last_name="Doe")
org.users.add(user, password="123456")
```


## OAuth2 / PKCE authentication

If your application handles the OAuth2 login itself — for example via the
Authorization Code + PKCE flow — you can connect with externally obtained tokens
using `connect_with_tokens()`:

```python
import docuware

dw = docuware.connect_with_tokens(
    url="https://acme.docuware.cloud/DocuWare/Platform",
    access_token="...",
    refresh_token="...",
    token_endpoint="https://acme.docuware.cloud/DocuWare/Identity/connect/token",
    client_id="your-client-id",
    on_token_refresh=lambda tokens: save_tokens(tokens),  # optional: persist rotated tokens
)
```

The `docuware.oauth` module provides two helpers for the PKCE flow itself:
`discover_oauth_endpoints()` resolves the authorization and token endpoints from
a DocuWare instance, and `exchange_pkce_code()` exchanges the authorization code
for tokens.

See [`examples/oauth2_login.py`](examples/oauth2_login.py) for a complete
reference implementation including browser launch, local callback server, and
CSRF state verification.


## CLI usage

This package also includes a simple CLI program for collecting information
about the archive and searching and downloading documents or attachments.

First you need to log in:

```console
$ dw-client login --url http://localhost/ --username "Doe, John" --password FooBar --organization "Doe Inc."
```

The credentials are stored in `$XDG_CONFIG_HOME/docuware-client/.credentials`
(or `$HOME/.docuware-client.cred` if `XDG_CONFIG_HOME` is not set).
Use `--credentials-file /path/to/file` to specify a different location.

Of course, `--help` will give you a list of all options:

```console
$ dw-client --help
```

Some search examples (Bash shell syntax). The `--file-cabinet` option accepts
both file cabinet names and basket names:

```console
$ dw-client search --file-cabinet Archive Customer=Foo\*
$ dw-client search --file-cabinet Archive DocNo=123456 "DocType=Invoice \\(incoming\\)"
$ dw-client search --file-cabinet Archive DocDate=2022-02-14
$ dw-client search --file-cabinet Inbox DocDate=2022-02-14
```

Downloading documents:

```console
$ dw-client search --file-cabinet Archive Customer=Foo\* --download document --annotations
```

> Note: `--annotations` forces the download as a PDF with annotations embedded. Without this flag, the document is downloaded in its original format without annotations.

Downloading a specific document by ID (new in v0.6.1):

```console
$ dw-client get --file-cabinet Archive --id 123456
```

Downloading attachments of a specific document:

```console
# Download document itself (original format) to stdout:
$ dw-client get --file-cabinet Archive --id 123456 --attachment document > output.pdf

# Download specific attachment:
$ dw-client get --file-cabinet Archive --id 123456 --attachment ATTACHMENT_ID --output my_file.pdf

# Download all attachments to a directory:
$ dw-client get --file-cabinet Archive --id 123456 --attachment "*" --output ./downloads/
```

Creating and updating documents:

```console
# Create a new document with index fields:
$ dw-client create --file-cabinet Archive --file invoice.pdf Subject="New Invoice" Amount=100.50

# Update index fields of an existing document:
$ dw-client update --file-cabinet Archive --id 123456 Status=Approved

# Add an attachment to a document:
$ dw-client attach --file-cabinet Archive --id 123456 --file supplement.pdf

# Remove an attachment:
$ dw-client detach --file-cabinet Archive --id 123456 --attachment-id ATTACHMENT_ID
```

Downloading attachments (or sections):

```console
$ dw-client search --file-cabinet Archive DocNo=123456 --download attachments
```

Some information about your DocuWare installation:

```console
$ dw-client info
```

Listing all organizations, file cabinets, baskets and dialogs at once:

```console
$ dw-client list
```

A more specific list, only one file cabinet or basket (by name):

```console
$ dw-client list --file-cabinet Archive
$ dw-client list --file-cabinet Inbox
```

You can also display a (partial) selection of the contents of individual fields:

```console
$ dw-client list --file-cabinet Archive --dialog custom --field DocNo
```


## Further reading

* Entry point to [DocuWare's official documentation][2] of the REST API.
* Notable endpoint: `/DocuWare/Platform/Content/PlatformLinkModel.pdf`


## License

This work is released under the BSD 3 license. You may use and redistribute
this software as long as the copyright notice is preserved.


[1]: https://docuware.com/
[2]: https://developer.docuware.com/rest/index.html
