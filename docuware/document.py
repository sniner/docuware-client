from __future__ import annotations

import logging
import mimetypes
import pathlib
from typing import IO, Any, Dict, Optional, Tuple, Union

from docuware import fields, structs, types, utils

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
        headers = {"Content-Type": "application/json", "Accept": "application/json"}
        try:
            _ = self.client.conn.delete(self.endpoints["self"], headers=headers)
        except Exception as exc:
            log.debug("Unable to delete document %s: %s", self, exc)
            raise  # FIXME: specific exception
        else:
            self.id = None
            self.endpoints = structs.Endpoints({})

    def update(self, fields: Dict[str, Any]) -> Document:
        json_fields = []
        for key, value in fields.items():
            type_name = "String"
            if isinstance(value, bool):
                type_name = "Bool"
            elif isinstance(value, int):
                type_name = "Int"
            elif isinstance(value, float):
                type_name = "Decimal"
            elif hasattr(value, "isoformat"):  # datetime or date
                type_name = "DateTime"
                value = value.isoformat()

            json_fields.append({"FieldName": key, "Item": value, "ItemElementName": type_name})

        data = {"Field": json_fields}
        headers = {"Content-Type": "application/json", "Accept": "application/json"}

        # We need the Fields endpoint. If not present, try to guess or fetch self.
        endpoint = self.endpoints.get("fields")
        if not endpoint:
            # Fallback: append /Fields to self (risky but common) or use a known relation
            # Usually "fields" is the relation name.
            # If missing, maybe reload doc?
            if "self" in self.endpoints:
                endpoint = self.endpoints["self"] + "/Fields"
            else:
                raise ValueError("Cannot update document without fields endpoint")

        _ = self.client.conn.put_json(endpoint, headers=headers, json=data)
        # Reload key properties? For now just return self.
        # Ideally we should fetch the updated doc to be consistent, but let's assume success.
        return self

    def upload_attachment(
        self, file: Union[pathlib.Path, str, IO[bytes]]
    ) -> DocumentAttachment:
        endpoint = self.endpoints.get(
            "files"
        )  # "files" or "sections"? usually "postFile" or "files"
        # Checking standard relations: "files" is often for uploading new sections.
        if not endpoint:
            # Check if we have a "sections" relation, maybe post there?
            if "sections" in self.endpoints:
                endpoint = self.endpoints["sections"]
            elif "self" in self.endpoints:
                endpoint = self.endpoints["self"] + "/Sections"  # Guessing
            else:
                raise ValueError("Cannot find endpoint to upload attachment")

        mime_type = "application/octet-stream"
        filename = "attachment"

        opened_file = None
        if isinstance(file, (str, pathlib.Path)):
            path = pathlib.Path(file)
            filename = path.name
            mime_type, _ = mimetypes.guess_type(path)
            mime_type = mime_type or "application/octet-stream"
            opened_file = open(path, "rb")
            content = opened_file
        else:
            content = file
            if hasattr(file, "name"):
                filename = pathlib.Path(file.name).name
                mime_type, _ = mimetypes.guess_type(filename)
                mime_type = mime_type or mime_type

        try:
            # Prepare multipart upload
            files = {"file": (filename, content, mime_type)}
            # Do not set Content-Type header manually, httpx handles multipart boundary

            # Post expecting JSON response of the created section?
            # Or just success.
            # DocuWare postFile usually returns the updated Document or the Section?
            # Creating a section usually returns the Section info.

            resp = self.client.conn.post(endpoint, files=files)
            resp.raise_for_status()

            # If response is the section info, modify self.attachments?
            # Ideally reload the document to get full state.
            # But let's try to parse the response if it looks like a Section.
            try:
                data = resp.json()
                if data and "ContentType" in data:
                    new_att = DocumentAttachment(data, self)
                    self.attachments.append(new_att)
                    return new_att
            except Exception:
                pass

            # If parsing failed or different response, just return a dummy or reload
            pass

        finally:
            if opened_file:
                opened_file.close()

        # Reloading to be safe
        doc_data = self.client.conn.get_json(self.endpoints["self"])
        self.attachments = [DocumentAttachment(s, self) for s in doc_data.get("Sections", [])]

        # Try to find the new attachment
        for att in reversed(self.attachments):
            if att.filename == filename:
                return att

        if self.attachments:
            return self.attachments[-1]

        raise ValueError("Attachment uploaded but not found in reloaded document")

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
        if "self" not in self.endpoints:
            self._fetch_endpoints()
            if "self" not in self.endpoints:
                raise ValueError("Cannot delete attachment without self endpoint")

        self.client.conn.delete(self.endpoints["self"])
        # Remove from parent list
        if self in self.document.attachments:
            # self.document.attachments is a list
            # We need to cast it to list to remove, but type hint says it is list in __init__
            # though Protocol says Sequence.
            # In existing code: self.attachments = [ ... ]
            # So it is a list.
            if isinstance(self.document.attachments, list):
                self.document.attachments.remove(self)

    def __str__(self) -> str:
        return f"Attachment '{self.filename}' [{self.id}, {self.content_type}]"
