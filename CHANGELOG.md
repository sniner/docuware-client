# Changelog

All notable changes to this project will be documented in this file.
See [Keep a Changelog](https://keepachangelog.com/en/1.0.0/) and [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.3] - 2026-03-15

### Fixed

- **`datetime_to_string()`**: millisecond precision was silently lost due to an
  operator precedence bug. Unobservable in practice (DocuWare uses integer seconds),
  but the output was formally incorrect
- **`User.as_dict()`**: `Active=False` was incorrectly dropped from the result,
  making it impossible to represent an explicitly inactive user without `overrides`
- **`default_credentials_file()`**: now respects `~/.config` as the XDG default
  when `$XDG_CONFIG_HOME` is not set; falls back to `~/.docuware-client.cred`
  only on systems where `~/.config` does not exist

### Tests

- Library code (excluding CLI) now at ~92% coverage

## [0.7.2] - 2026-03-14

### Added

- **`QuoteMode`** enum and **`quote_value()`** exported from the top-level package
- **`SearchDialog.search()` / `SearchQuery.search()`**: new `quote` parameter
  (`QuoteMode.PARTIAL` by default) that automatically escapes DocuWare metacharacters
  `(` `)` in field values while preserving wildcards `*` `?`. Pass `QuoteMode.ALL`
  to also escape wildcards, or `QuoteMode.NONE` to disable. Escaping is idempotent

### Fixed

- **Search conditions**: passing a `date`/`datetime` value in a dict-form condition
  previously produced `/Date(ms)/`, which DocuWare rejects as search input with a
  422 error. Values are now serialised as ISO 8601 strings
- **Search conditions**: passing `None` as a field value now correctly produces
  `EMPTY()` (search for documents where the field is empty) instead of the literal
  string `"None"`
- **Error messages**: 4xx/5xx responses now include the server's response body in
  the exception message, making errors much easier to diagnose

## [0.7.1] - 2026-03-14

### Added

- **`FileCabinet.search_dialog()`**: without a key, now returns the dialog marked
  as default in DocuWare instead of the first in the list
- **`Dialog.associated_dialog`**: navigate from a `SearchDialog` to its
  `ResultListDialog` and on to the `InfoDialog` without an extra HTTP call
- **`InfoDialog`**, **`ResultTree`**: new `Dialog` subclasses exported from the
  top-level package, enabling `isinstance` checks for all dialog types
- **`StoreDialog.fields`**: enumerate the index fields of a store dialog before
  calling `FileCabinet.create_document()`

### Fixed

- **`FileCabinet.search_dialog()`**: could not be called more than once reliably

## [0.7.0] - 2026-03-13

### Breaking changes

- **Cookie authentication removed.** Only OAuth2 is supported from this version
  on; OAuth2 requires DocuWare 7.10 or later. If you rely on cookie authentication,
  stay on 0.6.x
- **`.session` files replaced.** Credentials are now stored as JSON in a
  `.credentials` file; existing `.session` files are ignored

### Added

- **`ControlFile`** / **`FieldType`**: generate `.dwcontrol` XML files for the
  DocuWare Document Import service (see KBA-34830, KBA-36502)

### Changed

- **Login errors**: an invalid username or password now raises `AccountError` with
  a clear message instead of a generic HTTP error
- **CLI**: credentials stored at `$XDG_CONFIG_HOME/docuware-client/.credentials`
  (fallback: `~/.docuware-client.cred`)
- **Packaging**: migrated from Poetry to [uv](https://docs.astral.sh/uv/)

## [0.6.3] - 2026-03-07

### Added

- **`Client`**: shorthand alias for `DocuwareClient`
- Stable public API surface via explicit `__all__`

## [0.6.2] - 2026-02-21

### Fixed

- **CLI**: file cabinet lookup is now case-insensitive

## [0.6.1] - 2026-02-18

### Added

- **CLI**: `create`, `update`, `attach`, `detach`, and `get` commands for
  managing documents and attachments from the command line
- **`FileCabinet.create_document()`**: create a data record from index fields
- **`FileCabinet.get_document()`**: fetch a document by ID
- **`Document.update()`**: modify document index fields
- **`Document.upload_attachment()`** / **`DocumentAttachment.delete()`**:
  manage document attachments

## [0.6.0] - 2026-02-16

### Changed

- **HTTP layer**: migrated from `requests` to `httpx`

### Removed

- Dependency on `requests`
