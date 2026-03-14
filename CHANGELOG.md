# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.2] - 2026-03-14

### Added

- **`QuoteMode`** enum and **`quote_value()`** utility exported from the top-level
  package.
- **`SearchDialog.search()` / `SearchQuery.search()`**: new `quote` parameter
  (`QuoteMode.PARTIAL` by default) that automatically escapes DocuWare
  metacharacters in field values when using the dict form. `PARTIAL` escapes
  `(` and `)` while preserving wildcard characters `*` and `?`; `ALL` also
  escapes wildcards; `NONE` disables automatic escaping. The escaping is
  idempotent — existing workarounds with manually pre-escaped values continue
  to work unchanged.

### Fixed

- **`ConditionParser`**: `date` and `datetime` values in dict-form search
  conditions now produce ISO 8601 strings (`"2024-03-15"` /
  `"2024-03-15T12:00:00"`) instead of `/Date(ms)/`. DocuWare accepts
  `/Date(ms)/` only in its own responses, not as search input — passing it
  as a condition value caused a 422 Unprocessable Entity error.
- **`ConditionParser`**: passing `None` as a single dict value previously
  fell through to `str(None)` = `"None"`. It now correctly produces `EMPTY()`
  (search for documents where the field is empty), consistent with `None`
  inside a list.
- **`ConditionParser.convert_field_value(None)`**: returns `EMPTY()` instead
  of `*` to correctly express an empty-field search rather than a wildcard.
- **Error messages**: `conn.get()` and `conn.post()` now include the server's
  response body (up to 500 characters) in the exception message, making 4xx
  errors much easier to diagnose.

## [0.7.1] - 2026-03-14

### Added

- **`Dialog.is_default`**: exposes the `IsDefault` flag from the API response.
  `FileCabinet.search_dialog()` without a key now prefers the default dialog
  over the first in the list.
- **`Dialog.associated_dialog_id` / `Dialog.associated_dialog`**: expose the
  `AssignedDialogId` relationship from the API — navigates from a `SearchDialog`
  to its `ResultListDialog` and from there to the `InfoDialog` without an extra
  HTTP call.
- **`InfoDialog`** and **`ResultTree`**: new subclasses of `Dialog` so that
  `isinstance` checks work for all dialog types. Both are exported from the
  top-level package.
- **`StoreDialog.fields`**: lazy-loads and caches the index fields of a store
  dialog, enabling field discovery before calling `FileCabinet.create_document()`.

### Changed

- **`Dialog.name`** falls back to `Id` when `DisplayName` is absent or empty
  (`DisplayName` is optional in the XSD, `Id` is required).
- **`Dialog._load()` / `_on_loaded()`**: the duplicated lazy-loading logic from
  `SearchDialog` and `TaskListDialog` is now a single implementation in the `Dialog`
  base class, with an `_on_loaded(config)` hook for subclass-specific
  post-load work (Template Method pattern).
- **`dialogExpressionLink` workaround** moved from `SearchQuery.__init__` into
  `SearchDialog._on_loaded()`, keeping the API-bug fix close to where the
  dialog config is processed rather than inside the query class.
- **`FileCabinet.dialogs`** filter: the `"_" not in Id` heuristic that excludes
  mobile/internal dialog copies is now documented with a comment explaining the
  rationale. Also guards against a missing `Id` key.

### Fixed

- `FileCabinet.search_dialog()` previously used a generator that could only be
  consumed once; it now uses a list, which also enables the `IsDefault` check.

## [0.7.0] - 2026-03-13

### Breaking changes

- **Cookie authentication removed.** `CookieAuthenticator` and all related session
  management code have been deleted. Only OAuth2 is supported from this version on.
  OAuth2 requires DocuWare 7.10 or later. If you rely on cookie authentication,
  stay on 0.6.x.
- `.session` files are no longer created or used. Credentials are now stored as
  JSON in a `.credentials` file.

### Added

- **`dwcontrol.py`**: new `ControlFile` class and `FieldType` enum for generating
  `.dwcontrol` XML files used by the DocuWare Document Import service
  (see KBA-34830, KBA-36502).
- **`BearerAuth`**: dedicated `httpx.Auth` subclass for Bearer token injection,
  replacing the previous ad-hoc header manipulation.

### Changed

- **Packaging**: migrated from Poetry to [uv](https://docs.astral.sh/uv/);
  source tree restructured to `src/` layout (`src/docuware/`).
- **Auth**: `OAuth2Authenticator.login()` now returns `None` instead of the
  leftover `{"access_token": ...}` dict that was a relic of the cookie
  authenticator.
- **Error handling**: `_get_access_token()` always raises on failure instead of
  silently returning `None`. An HTTP 400 response from the token endpoint is now
  translated to `AccountError: Login failed: invalid username or password` for a
  clear user-facing message.
- **CLI**: credentials are now stored in
  `$XDG_CONFIG_HOME/docuware-client/.credentials` (fallback:
  `$HOME/.docuware-client.cred`). `--credentials-file` validates that the given
  path is not a directory.
- **Code cleanup**: removed dead code and simplified internals across `conn.py`,
  `client.py`, `dialogs.py`, `document.py`, `filecabinet.py`, `organization.py`,
  `parser.py`, `structs.py`, and `utils.py`.
- **Tests**: mock handlers updated to simulate the full OAuth2 token flow
  (IdentityServiceInfo → openid-configuration → token endpoint).
- Updated GitHub Actions workflow for the new `src/` layout and uv.

### Removed

- `CookieAuthenticator` and all cookie/session-based login code.
- `poetry.lock` (replaced by `uv.lock`).

## [0.6.3] - 2026-03-07

### Added

- **`__init__.py`**: explicit `__all__` for a stable, documented public API surface.
- `Client` as a shorthand alias for `DocuwareClient`.

### Changed

- Updated dependencies.

## [0.6.2] - 2026-02-21

### Added
- **CI**: Added GitHub actions workflow for running tests and building releases.

### Fixed
- **CLI**: Fixed `get_file_cabinet` lookup so that file cabinets are correctly found in a case-insensitive manner.

## [0.6.1] - 2026-02-18

### Added
- **CLI**: added `create` command to create documents (optionally with file content) and set index fields.
- **CLI**: added `update` command to modify index fields of existing documents.
- **CLI**: added `attach` command to add files as attachments to documents.
- **CLI**: added `detach` command to remove specific attachments.
- **CLI**: added `get` command to retrieve documents by ID. Use `--attachment` (optionally with `--output`) to download content. Supports wildcard `*` for all attachments.
- **API**: added `FileCabinet.create_document` to create a data record from index fields.
- **API**: added `FileCabinet.get_document` to fetch a document by ID directly.
- **API**: added `Document.update` to modify document fields.
- **API**: added `Document.upload_attachment` and `DocumentAttachment.delete`.

### Changed
- Refactored `FileCabinet` to use clearer method names and removed broken legacy methods (`create_data_entry`, `update_data_entry`).
- Improved `docuware.conn` to support `files` and `params` in request methods.

## [0.6.0] - 2026-02-16

### Changed
- **Core**: Migrated entire HTTP layer from `requests` to `httpx` for better performance and async compatibility potential.
- Updated `types.py` protocols to reflect `httpx` response types.

### Removed
- Removed dependency on `requests`.
