# docuware-client

This is a client library for the REST API of [DocuWare][1] DMS. Since
[DocuWare's documentation][2] regarding the REST API is very sparse (at the
time these lines were written), this client serves only a part of the API's
functionality.

Please keep in mind: **This software is not related to DocuWare.** It is a work
in progress, may yield unexpected results, and almost certainly contains bugs.

> ⚠️ Starting with version 0.5.0, OAuth2 authentication is the new default.
> Unless you explicitly request cookie authentication with
> `dw.login(..., cookie_auth=True)`, OAuth2 will be used. OAuth2 authentication
> has been available since DocuWare 7.10, and
> [cookie authentication will be discontinued](https://start.docuware.com/blog/product-news/docuware-sdk-discontinuation-of-cookie-authentication)
> with DocuWare 7.11.


## Usage

First you have to log in and create a persistent session:

```python
import json
import pathlib
import docuware

dw = docuware.Client("http://localhost")
session = dw.login("username", "password", "organization")
with open(".session", "w") as f:
    json.dump(session, f)
```

From then on you have to reuse the session, otherwise you will be locked out of
the DocuWare service for a period of time (10 minutes or even longer). As the
session cookie may change on subsequent logins, update the session file on
every login.

```python
session_file = pathlib.Path(".session")
if session_file.exists():
    with open(session_file) as f:
        session = json.load(f)
else:
    session = None
dw = docuware.Client("http://localhost")
session = dw.login("username", "password", "organization", saved_session=session)
with open(session_file, "w") as f:
    json.dump(session, f)
```

Iterate over the organizations and file cabinets:

```python
for org in dw.organizations:
    print(org)
    for fc in org.file_cabinets:
        print("   ", fc)
```

If you already know the ID or name of the objects, you can also access them
directly.

```python
org = dw.organization("1")
fc = org.file_cabinet("Archive")
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
for result in dlg.search(["DOCNO=123456", "DOCNO=654321"], operation=docuware.OR):
    print(result)
# Search for documents in a date range (01-31 January 2023):
for result in dlg.search("DWSTOREDATETIME=2023-01-01T00:00:00,2023-02-01T00:00:00")
    print(result)
```

Please note that search terms may also contain metacharacters such as `*`, `(`,
`)`, which may need to be escaped when searching for these characters
themselves.

```python
for result in dlg.search("DOCTYPE=Invoice \\(incoming\\)"):
    print(result)
```

Search terms can be as simple as a single string, but can also be more complex.
The following two queries are equivalent:

```python
dlg.search(["FIELD1=TERM1,TERM2", "FIELD2=TERM3"])
dlg.search({"FIELD1": ["TERM1", "TERM2"], "FIELD2": ["TERM3"]})
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

Create data entry in file cabinet:
```python
data = {
    "FIELD1": "value1",
    "FIELD2": "value2",
}
response = fc.create_data_entry(data)
```

_Subject to rewrite:_ Update data fields of document. The search parameter must
return a single document. Use a loop to execute this function on multiple
documents:

```python
fields = {
    "FIELD1": "value1",
    "FIELD2": 99999
}
response = fc.update_data_entry(["FIELD1=TERM1,TERM2", "FIELD2=TERM3"], user_fields)
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
$ dw-client login --url http://localhost/ --username "Doe, John" --password FooBar --organization "Doe Inc."
```

The credentials and the session cookie are stored in the `.credentials` and
`.session` files in the current directory.

Of course, `--help` will give you a list of all options:

```console
$ dw-client --help
```

Some search examples (Bash shell syntax):

```console
$ dw-client search --file-cabinet Archive Customer=Foo\*
$ dw-client search --file-cabinet Archive DocNo=123456 "DocType=Invoice \\(incoming\\)"
$ dw-client search --file-cabinet Archive DocDate=2022-02-14
```

Downloading documents:

```console
$ dw-client search --file-cabinet Archive Customer=Foo\* --download document --annotations
```

Downloading attachments (or sections):

```console
$ dw-client search --file-cabinet Archive DocNo=123456 --download attachments
```

Some information about your DocuWare installation:

```console
$ dw-client info
```

Listing all organizations, file cabinets and dialogs at once:

```console
$ dw-client list
```

A more specific list, only one file cabinet:

```console
$ dw-client list --file-cabinet Archive
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
