from __future__ import annotations

import json as stdjson
import logging
import os
import urllib.parse as urlparse
from typing import Any, Dict, Optional, Tuple, Union

import httpx

from docuware import cijson, errors, parser, types
from docuware.const import ACCEPT_JSON, ACCEPT_TEXT, BASE_HEADERS

log = logging.getLogger(__name__)

# Default request timeout in seconds.  DocuWare Cloud can be slow on the first
# requests after login (session warm-up).  Override with the DW_TIMEOUT env var.
_DEFAULT_TIMEOUT: float = float(os.environ.get("DW_TIMEOUT", "30"))


def _server_message(resp: httpx.Response) -> Optional[str]:
    """Extract DocuWare's 'Message' field from a JSON error response, if present."""
    try:
        return resp.json().get("Message") or None
    except Exception:
        return None


class Connection(types.ConnectionP):
    def __init__(
        self,
        base_url: str,
        case_insensitive: bool = True,
        verify_certificate: bool = True,
        authenticator: Optional[types.AuthenticatorP] = None,
        timeout: Optional[float] = None,
    ):
        self.base_url = base_url
        self.session = httpx.Client(
            verify=verify_certificate,
            timeout=httpx.Timeout(timeout if timeout is not None else _DEFAULT_TIMEOUT),
        )
        self.authenticator = authenticator
        self._case_insensitive = case_insensitive

    def make_path(self, path: str, query: Dict[str, str]) -> str:
        u = urlparse.urlsplit(path)
        q = "&".join(
            ([u.query] if u.query else [])
            + [f"{urlparse.quote_plus(k)}={urlparse.quote_plus(v)}" for k, v in query.items()]
        )
        return urlparse.urlunsplit(u._replace(query=q))

    def make_url(self, path: str, query: Optional[Dict[str, str]] = None) -> str:
        if query:
            path = self.make_path(path, query)
        return urlparse.urljoin(self.base_url, path)

    def _request(
        self,
        method: str,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        headers = {**BASE_HEADERS, **headers} if headers else BASE_HEADERS
        content = data if isinstance(data, (bytes, str)) else None
        form_data = data if isinstance(data, dict) else None
        kwargs: Dict[str, Any] = dict(
            headers=headers,
            json=json,
            data=form_data,
            content=content,
            files=files,
            params=params,
        )
        resp = self.session.request(method, url, **kwargs)
        if resp.status_code in (401, 403) and self.authenticator:
            self.session = self.authenticator.authenticate(self)
            resp = self.session.request(method, url, **kwargs)
        return resp

    def post(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
        files: Optional[Dict[str, Any]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        url = self.make_url(path)
        resp = self._request(
            "POST",
            url,
            headers=headers,
            json=json,
            data=data,
            files=files,
            params=params,
        )
        if resp.status_code == 200:
            return resp
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"POST {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )

    def post_json(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> Any:
        headers = {**headers, **ACCEPT_JSON} if headers else ACCEPT_JSON
        resp = self.post(path, headers=headers, json=json, data=data)
        return cijson.loads(resp.text) if self._case_insensitive else stdjson.loads(resp.text)

    def post_text(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> str:
        headers = {**headers, **ACCEPT_TEXT} if headers else ACCEPT_TEXT
        return self.post(path, headers=headers, json=json, data=data).text

    def put(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> httpx.Response:
        url = self.make_url(path)
        resp = self._request(
            "PUT",
            url,
            headers=headers,
            json=json,
            data=data,
            params=params,
        )
        if resp.status_code == 200:
            return resp
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"PUT {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )

    def put_json(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> Any:
        headers = {**headers, **ACCEPT_JSON} if headers else ACCEPT_JSON
        resp = self.put(path, headers=headers, params=params, json=json, data=data)
        return cijson.loads(resp.text) if self._case_insensitive else stdjson.loads(resp.text)

    def put_text(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> str:
        headers = {**headers, **ACCEPT_TEXT} if headers else ACCEPT_TEXT
        return self.put(path, headers=headers, params=params, json=json, data=data).text

    def get(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        url = self.make_url(path)
        resp = self._request(
            "GET",
            url,
            headers=headers,
            params=params,
        )
        if resp.status_code == 200:
            return resp
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"GET {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )

    def get_json(self, path: str, headers: Optional[Dict[str, str]] = None) -> Any:
        headers = {**headers, **ACCEPT_JSON} if headers else ACCEPT_JSON
        resp = self.get(path, headers=headers)
        return cijson.loads(resp.text) if self._case_insensitive else stdjson.loads(resp.text)

    def get_text(self, path: str, headers: Optional[Dict[str, str]] = None) -> str:
        headers = {**headers, **ACCEPT_TEXT} if headers else ACCEPT_TEXT
        return self.get(path, headers=headers).text

    def delete(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> httpx.Response:
        url = self.make_url(path)
        resp = self._request(
            "DELETE",
            url,
            headers=headers,
            params=params,
        )
        if resp.status_code == 200:
            return resp
        msg = _server_message(resp)
        raise errors.ResourceError(
            f"DELETE {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )

    def get_bytes(
        self,
        path: str,
        mime_type: Optional[str] = None,
        params: Optional[Dict[str, str]] = None,
    ) -> Tuple[bytes, str, str]:
        url = self.make_url(path)
        resp = self._request(
            "GET",
            url,
            headers={"Accept": mime_type if mime_type else "*/*"},
            params=params,
        )
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content_length = resp.headers.get("Content-Length")
            content_disposition = parser.parse_content_disposition(
                resp.headers.get("Content-Disposition", "")
            )
            if content_length and len(resp.content) != int(content_length):
                raise errors.ResourceError(
                    f"Unexpected content length: expected {content_length}, got {len(resp.content)}",
                    url=url,
                    status_code=resp.status_code,
                )
            return (
                resp.content,
                content_type,
                content_disposition.get("filename") or "unknown.bin",
            )
        msg = _server_message(resp)
        raise errors.ResourceNotFoundError(
            f"Download failed {resp.status_code}" + (f": {msg}" if msg else ""),
            url=url,
            status_code=resp.status_code,
            server_message=msg,
        )
