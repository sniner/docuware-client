# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.0.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
