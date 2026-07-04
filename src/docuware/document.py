from __future__ import annotations

import logging
import mimetypes
import pathlib
from typing import IO, Any, Dict, Optional, Tuple, Union

from docuware import cijson, errors, fields, structs, textshot, types, utils

log = logging.getLogger(__name__)


class Document:
    def __init__(self, config: Dict, file_cabinet: types.FileCabinetP):
        self.file_cabinet = file_cabinet
        self.id = config.get("Id")
        self.title = config.get("Title")
        self.content_type = config.get("ContentType")
        self.size = config.get("FileSize", 0)
        self.modified = utils.datetime_from_string(config.get("LastModified"))
        self.created = utils.datetime_from_string(config.get("CreatedAt"))
        self.endpoints = structs.Endpoints(config)
        self.attachments = [DocumentAttachment(s, self) for s in config.get("Sections", [])]
        self.fields = [fields.FieldValue.from_config(f) for f in config.get("Fields", [])]
        self._deleted: bool = False

    def _assert_alive(self) -> None:
        if self._deleted:
            raise errors.DataError(f"Document {self.id!r} has already been deleted")

    @property
    def client(self) -> types.DocuwareClientP:
        return self.file_cabinet.organization.client

    def field(self, key: str, default: Optional[Any] = None) -> Optional[fields.FieldValue]:
        return structs.first_item_by_id_or_name(self.fields, key, default=default)

    @staticmethod
    def _download(
        client: types.DocuwareClientP, endpoint: str, keep_annotations: bool = True
    ) -> Tuple[bytes, str, str]:
        return client.conn.get_bytes(
            endpoint,
            params={
                "keepAnnotations": "true" if keep_annotations else "false",
                "targetFileType": "PDF" if keep_annotations else "Auto",
            },
        )

    def thumbnail(self) -> Tuple[bytes, str, str]:
        self._assert_alive()
        return self.client.conn.get_bytes(self.endpoints["thumbnail"])

    def download(self, keep_annotations: bool = True) -> Tuple[bytes, str, str]:
        self._assert_alive()
        return Document._download(
            self.client,
            self.endpoints["fileDownload"],
            keep_annotations=keep_annotations,
        )

    def download_all(self) -> Tuple[bytes, str, str]:
        self._assert_alive()
        return self.client.conn.get_bytes(self.endpoints["downloadAsArchive"])

    def delete(self) -> None:
        self._assert_alive()
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        self.client.conn.delete(self.endpoints["self"], headers=headers)
        self._deleted = True

    def update(self, fields: Dict[str, Any]) -> Document:
        self._assert_alive()
        json_fields = []
        for key, value in fields.items():
            type_name, value = structs.python_to_dw_field(value)
            json_fields.append({"FieldName": key, "Item": value, "ItemElementName": type_name})

        data = {"Field": json_fields}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        endpoint = self.endpoints.get("fields")
        if not endpoint:
            # Some document representations omit the "fields" relation; the
            # platform exposes it at <self>/Fields.
            if "self" not in self.endpoints:
                raise errors.InternalError(
                    f"Document {self.id!r} has neither a 'fields' nor a 'self' endpoint"
                )
            endpoint = self.endpoints["self"] + "/Fields"

        _ = self.client.conn.put_json(endpoint, headers=headers, json=data)
        return self

    def upload_attachment(
        self, file: Union[pathlib.Path, str, IO[bytes]]
    ) -> DocumentAttachment:
        self._assert_alive()
        # New sections are posted to the "files" relation; older server
        # versions expose only "sections", which accepts the same POST.
        endpoint = self.endpoints.get("files") or self.endpoints.get("sections")
        if not endpoint:
            if "self" not in self.endpoints:
                raise errors.InternalError(
                    f"Document {self.id!r} has no endpoint to upload an attachment to"
                )
            endpoint = self.endpoints["self"] + "/Sections"

        mime_type = "application/octet-stream"
        filename = "attachment"

        opened_file = None
        if isinstance(file, (str, pathlib.Path)):
            path = pathlib.Path(file)
            filename = path.name
            guessed, _ = mimetypes.guess_type(path)
            mime_type = guessed or mime_type
            opened_file = open(path, "rb")
            content = opened_file
        else:
            content = file
            if hasattr(file, "name"):
                filename = pathlib.Path(file.name).name
                guessed, _ = mimetypes.guess_type(filename)
                mime_type = guessed or mime_type

        try:
            # httpx sets the multipart boundary; no manual Content-Type here
            files = {"file": (filename, content, mime_type)}
            resp = self.client.conn.post(endpoint, files=files)
        finally:
            if opened_file:
                opened_file.close()

        # The platform answers with the created section
        try:
            data = cijson.loads(resp.text)
        except ValueError:
            data = None
        if data and "ContentType" in data:
            new_att = DocumentAttachment(data, self)
            self.attachments.append(new_att)
            return new_att

        # Unexpected response shape: reload the document and find the new
        # section by its original filename
        doc_data = self.client.conn.get_json(self.endpoints["self"])
        self.attachments = [DocumentAttachment(s, self) for s in doc_data.get("Sections", [])]
        for att in reversed(self.attachments):
            if att.filename == filename:
                return att

        raise errors.InternalError(
            f"Attachment {filename!r} uploaded but not found in reloaded document"
        )

    def __str__(self) -> str:
        return f"{self.__class__.__name__} '{self.title}' [{self.id}]"


# Attachment seems more reasonable than Section. In the DocuWare context a section is
# not a part of a file or document, but an individual attachment to the DocuWare document.
class DocumentAttachment:
    def __init__(self, config: Dict, document: Document):
        self.document = document
        self.content_type = config.get("ContentType")
        self.filename = config.get("OriginalFileName")
        self.id = config.get("Id")
        self.size = config.get("FileSize", 0)
        self.pages = config.get("PageCount", 0)
        self.modified = utils.datetime_from_string(config.get("ContentModified"))
        self.has_annotations = config.get("HasTextAnnotation")
        self.endpoints = structs.Endpoints(config)

    @property
    def client(self) -> types.DocuwareClientP:
        return self.document.client

    def _fetch_endpoints(self, required: str = "fileDownload") -> None:
        if required not in self.endpoints:
            config = self.client.conn.get_json(self.endpoints["self"])
            self.endpoints = structs.Endpoints(config)

    def download(self, keep_annotations: bool = False) -> Tuple[bytes, str, str]:
        self._fetch_endpoints()
        data, mime, filename = Document._download(
            self.client,
            self.endpoints["fileDownload"],
            keep_annotations=keep_annotations,
        )
        return data, mime, self.filename or filename

    def textshot(self) -> textshot.TextShot:
        self._fetch_endpoints(required="textshot")
        endpoint = self.endpoints.get("textshot")
        if not endpoint:
            raise errors.DataError(
                "Attachment has no textshot endpoint; "
                "the file cabinet may not be fulltext-indexed or the document has not been processed yet"
            )
        return textshot.TextShot(self.client.conn.get_json(endpoint))

    def text(self) -> str:
        return self.textshot().text

    def delete(self) -> None:
        # _fetch_endpoints() itself needs the "self" relation, so there is no
        # way to recover when it is missing.
        if "self" not in self.endpoints:
            raise errors.InternalError(
                f"Attachment {self.id!r} has no self endpoint, cannot delete"
            )
        self.client.conn.delete(self.endpoints["self"])
        if isinstance(self.document.attachments, list) and self in self.document.attachments:
            self.document.attachments.remove(self)

    def __str__(self) -> str:
        return f"Attachment '{self.filename}' [{self.id}, {self.content_type}]"
