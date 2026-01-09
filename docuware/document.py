from __future__ import annotations
import logging
from typing import Any, Optional, Tuple, Union

from docuware import structs, types, utils, fields

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

    @property
    def client(self) -> types.DocuwareClientP:
        return self.file_cabinet.organization.client

    def field(self, key: str, default: Optional[Any] = None) -> Optional[fields.FieldValue]:
        return structs.first_item_by_id_or_name(self.fields, key, default=default)

    @staticmethod
    def _download(client: types.DocuwareClientP, endpoint: str, keep_annotations: bool = True) -> Tuple[bytes, str, str]:
        return client.conn.get_bytes(endpoint, data={
            "keepAnnotations": "true" if keep_annotations else "false",
            "targetFileType": "PDF" if keep_annotations else "Auto",
        })

    def thumbnail(self) -> Tuple[bytes, str, str]:
        return self.client.conn.get_bytes(self.endpoints["thumbnail"])

    def download(self, keep_annotations: bool = True) -> Tuple[bytes, str, str]:
        return Document._download(
            self.client,
            self.endpoints["fileDownload"],
            keep_annotations=keep_annotations,
        )

    def download_all(self) -> Tuple[bytes, str, str]:
        return self.client.conn.get_bytes(self.endpoints["downloadAsArchive"])

    def delete(self):
        headers = {
            "Content-Type": "application/json",
            "Accept": "application/json"
        }
        try:
            _ = self.client.conn.delete(self.endpoints["self"], headers=headers)
        except Exception as exc:
            log.debug("Unable to delete document %s: %s", self, exc)
            raise  # FIXME: specific exception
        else:
            self.id = None
            self.endpoints: Dict[str, str] = {}

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

    def _fetch_endpoints(self) -> None:
        if "fileDownload" not in self.endpoints:
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

    def delete(self) -> None:
        raise NotImplementedError

    def __str__(self) -> str:
        return f"Attachment '{self.filename}' [{self.id}, {self.content_type}]"
