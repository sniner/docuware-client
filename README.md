# docuware-client

This is a client library for the REST API of [DocuWare][1] DMS. It lets you
query your DocuWare archives, download and upload documents, read and update
index fields, retrieve OCR'd text from fulltext-indexed cabinets, and manage
users and groups. The bundled `dw-client` command exposes the most common
operations on the shell.

Since DocuWare does not appear to publish official developer documentation
for the REST API beyond XSD schema files, this client likely does not cover
the full functionality of the API.

Please keep in mind: **This is an independent project with no affiliation to
DocuWare GmbH.**

> **Looking to connect an LLM to DocuWare?** Have a look at the sister
> project [docuware-mcp][3] (also on PyPI) — an MCP server built on top of
> this library that exposes DocuWare to LLM clients like Claude Desktop.

> **Breaking change in 0.7.0 — OAuth2 only**
>
> Starting with version 0.7.0, **only OAuth2 authentication is supported.**
> Cookie-based authentication has been removed completely.
> If you rely on cookie authentication, please stay on version **0.6.x**.
>
> OAuth2 requires DocuWare 7.10 or later. Credentials are stored in a
> `.credentials` file; the `.session` file is no longer created or used.

## Usage

The recommended way to connect is via `docuware.connect()`. It supports all
four OAuth2 flows (password grant, client credentials, PKCE, bring-your-own
token) through a single entry point — see [`docs/oauth2-setup.md`](docs/oauth2-setup.md)
for App Registration setup and detailed flow comparison.

### Password grant (legacy)

For existing setups with a real DocuWare user account:

```python
import docuware

# Credentials from arguments:
dw = docuware.connect(url="http://localhost", username="...", password="...", organization="...")

# Or from environment variables DW_URL, DW_USERNAME, DW_PASSWORD, DW_ORG:
dw = docuware.connect()

# Or from a credentials file (legacy shortcut):
dw = docuware.connect(credentials_file="/path/to/.credentials")
```

Credentials are saved automatically to the file specified by `credentials_file`
after a successful login.

### PKCE (native/desktop, recommended for interactive use)

First call opens the browser; subsequent calls reuse persisted tokens:

```python
dw = docuware.connect(
    url="acme.docuware.cloud",
    authenticator=docuware.PkceAuthenticator(client_id="<UUID>"),
    credential_store=docuware.JsonFileCredentialStore("~/.config/docuware-client/.credentials"),
)
```

Token rotation (RFC 6749 §10.4) is handled automatically — rotated tokens
are written back to the store on every refresh.

### Client Credentials (service-to-service, no user)

For backend jobs, ETL, MCP servers, scheduled tasks:

```python
dw = docuware.connect(
    url="acme.docuware.cloud",
    authenticator=docuware.ClientCredentialsAuthenticator(
        client_id="<UUID>",
        client_secret="<from App Registration>",
    ),
    credential_store=docuware.JsonFileCredentialStore("/etc/myapp/.credentials"),
)
```

See [`docs/oauth2-setup.md`](docs/oauth2-setup.md) for the DocuWare App
Registration details for each flow, and `examples/oauth2_*.py` for
complete runnable scripts.

### Bring your own token

If your application handles the OAuth2 login itself — for example via the
Authorization Code + PKCE flow — you can connect with externally obtained
tokens using a `TokenAuthenticator`:

```python
import docuware

dw = docuware.connect(
    url="https://acme.docuware.cloud/DocuWare/Platform",
    authenticator=docuware.TokenAuthenticator(
        access_token="...",
        refresh_token="...",
        token_endpoint="https://acme.docuware.cloud/DocuWare/Identity/connect/token",
        client_id="your-client-id",
    ),
    credential_store=docuware.JsonFileCredentialStore("~/.config/myapp/.credentials"),
)
```

DocuWare rotates refresh tokens; with a `credential_store` the rotated tokens
are persisted automatically on every refresh. Alternatively, set the
authenticator's `on_token_refresh` callback to persist the credential bundle
yourself. The older `connect_with_tokens()` entry point still works but is
deprecated since 0.8.0 and emits a `DeprecationWarning`.

The `docuware.oauth` module provides two helpers for the PKCE flow itself:
`discover_oauth_endpoints()` resolves the authorization and token endpoints
from a DocuWare instance, and `exchange_pkce_code()` exchanges the
authorization code for tokens.

See [`examples/oauth2_login.py`](examples/oauth2_login.py) for a complete
reference implementation including browser launch, local callback server, and
CSRF state verification.

### Direct client construction

`connect()` covers the common cases. For tighter control over the auth
pipeline — custom refresh callbacks, a custom browser opener, or driving
the login step explicitly in a larger workflow — build the authenticator
yourself, pass it to the `DocuwareClient` constructor, and call `login()`:

```python
import docuware

auth = docuware.PkceAuthenticator(
    client_id="<UUID>",
    redirect_port=8765,
    on_browser_open=lambda url: print(f"Open: {url}"),
)
dw = docuware.Client("http://localhost", authenticator=auth)
dw.login()
```

In this mode none of `connect()`'s convenience kicks in — no environment
variables are consulted, and persistence is opt-in via
`auth.add_store(store, url=...)` before calling `login()`.

### Working with the API

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

Results can be **sorted server-side** with `order_by`. Pass a list of
`(field, direction)` tuples; direction is `"asc"`, `"desc"`, or `"default"`
(case-insensitive). Field names can be the DB-name or the display label:

```python
# "Newest invoices first":
dlg.search({"DOCTYPE": "Invoice"}, order_by=[("DOCDATE", "desc")])

# Multi-field sort — primary by date desc, ties broken by customer asc:
dlg.search(
    {"DOCTYPE": "Invoice"},
    order_by=[("DOCDATE", "desc"), ("CUSTOMERNO", "asc")],
)
```

Without `order_by`, DocuWare returns the result in an unspecified order. Sorting
server-side avoids loading every hit and sorting client-side, which matters for
large result sets and integrations such as MCP.

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

For fulltext-indexed file cabinets, the OCR'd text of each attachment can be
retrieved directly — handy for feeding documents into search indexes or LLMs:

```python
for result in dlg.search("DOCNO=123456"):
    for att in result.document.attachments:
        # Plain text — pages joined by form feed (\f), lines by \n:
        print(att.text())

        # Or get the structured object (pages → zones → lines → words with coordinates):
        ts = att.textshot()
        for page in ts.pages:
            print(f"page lang={page.language}, {len(list(page.words()))} words")
```

`textshot()` returns a `TextShot` mirroring DocuWare's `intellix:DocumentContent`
schema; word coordinates are in twips (1/1440 inch). A `DataError` is raised if
the file cabinet is not fulltext-indexed or the document has not yet been
processed by the OCR pipeline.

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


## CLI usage

This package also includes a simple CLI program for collecting information
about the archive and searching and downloading documents or attachments.

First you need to log in:

```console
$ dw-client login --url http://localhost/ --username "Doe, John" --organization "Doe Inc."
Password:
```

When `--password` is omitted, you are prompted interactively — this keeps the
password out of the process list and your shell history. Passing
`--password` on the command line still works (e.g. for scripting).

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

Downloading a specific document by ID:

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
* Notable endpoint: `/DocuWare/Platform/Schema/File/schema-0.xsd` — root of
  the XSD schema files; all other schemas are linked from here via
  `xs:import` and `xs:include`.


## License

This work is released under the BSD 3 license. You may use and redistribute
this software as long as the copyright notice is preserved.


[1]: https://docuware.com/
[2]: https://developer.docuware.com/rest/index.html
[3]: https://github.com/sniner/docuware-mcp
