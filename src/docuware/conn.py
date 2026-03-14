from __future__ import annotations

import json as stdjson
import logging
import urllib.parse as urlparse
from abc import ABC, abstractmethod
from collections.abc import Generator
from typing import Any, Dict, Optional, Tuple, Union

import httpx

from docuware import cijson, errors, parser, types

log = logging.getLogger(__name__)


def _server_message(resp: httpx.Response) -> Optional[str]:
    """Extract DocuWare's 'Message' field from a JSON error response, if present."""
    try:
        return resp.json().get("Message") or None
    except Exception:
        return None


DEFAULT_HEADERS = {
    "User-Agent": "Python docuware-client",
}

JSON_HEADERS = {
    "Accept": "application/json",
}

TEXT_HEADERS = {
    "Accept": "text/plain",
}


class BearerAuth(httpx.Auth):
    def __init__(self, token: str) -> None:
        self.token = token

    def auth_flow(
        self, request: httpx.Request
    ) -> Generator[httpx.Request, httpx.Response, None]:
        request.headers["Authorization"] = f"Bearer {self.token}"
        yield request


class Authenticator(ABC, types.AuthenticatorP):
    @abstractmethod
    def authenticate(self, conn: types.ConnectionP) -> httpx.Client: ...

    @abstractmethod
    def login(self, conn: types.ConnectionP) -> None: ...

    @abstractmethod
    def logoff(self, conn: types.ConnectionP) -> None: ...

    def _get(self, conn: types.ConnectionP, path: str) -> Dict:
        url = conn.make_url(path)
        resp = conn.session.get(url, headers={**DEFAULT_HEADERS, **JSON_HEADERS})
        if resp.status_code == 200:
            return cijson.loads(resp.text)
        raise errors.ResourceError(
            "Failed to get resource", url=url, status_code=resp.status_code
        )

    def _post(
        self,
        conn: types.ConnectionP,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None,
    ) -> Dict:
        url = conn.make_url(path)
        headers = {**DEFAULT_HEADERS, **(headers or {}), **JSON_HEADERS}
        resp = conn.session.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            return cijson.loads(resp.text)
        raise errors.ResourceError(
            "Failed to post to resource", url=url, status_code=resp.status_code
        )


class OAuth2Authenticator(Authenticator):
    def __init__(
        self,
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
    ):
        self.password = password
        self.username = username
        self.organization = organization
        self.token: Optional[str] = None

    def _apply_access_token(self, conn: types.ConnectionP, token: Optional[str]) -> None:
        conn.session.auth = BearerAuth(token) if token else None  # type: ignore[assignment]

    def _get_access_token(self, conn: types.ConnectionP) -> str:
        log.debug("Requesting access token")
        # According to https://support.docuware.com/en-us/knowledgebase/article/KBA-37505:
        # Step 1: Get responsible Identity Service
        res = self._get(conn, "/DocuWare/Platform/Home/IdentityServiceInfo")

        # Step 2: Get Identity Service Configuration
        path = f"{res.get('IdentityServiceUrl', '').rstrip('/')}/.well-known/openid-configuration"
        res = self._get(conn, path)

        # Step 3: Obtain an Access Token
        path = res.get("token_endpoint") or "/DocuWare/Identity/connect/token"
        data = {
            "grant_type": "password",
            "username": self.username,
            "password": self.password,
            "client_id": "docuware.platform.net.client",
            "scope": "docuware.platform",
        }
        try:
            result = self._post(conn, path, data=data)
        except errors.ResourceError as exc:
            if exc.status_code == 400:
                raise errors.AccountError("Login failed: invalid username or password") from exc
            raise
        token = result.get("access_token")
        if not token:
            raise errors.AccountError("No access token received")
        return token

    def authenticate(self, conn: types.ConnectionP) -> httpx.Client:
        self._apply_access_token(conn, None)  # clear stale token before re-authenticating
        self.token = self._get_access_token(conn)
        self._apply_access_token(conn, self.token)
        return conn.session

    def login(self, conn: types.ConnectionP) -> None:
        conn.session = self.authenticate(conn)

    def logoff(self, conn: types.ConnectionP) -> None:
        if self.token:
            # DocuWare Identity Server does not expose a standard revocation endpoint,
            # so we can only discard the token locally.
            self.token = None
            self._apply_access_token(conn, None)


class Connection(types.ConnectionP):
    def __init__(
        self,
        base_url: str,
        case_insensitive: bool = True,
        verify_certificate: bool = True,
        authenticator: Optional[types.AuthenticatorP] = None,
    ):
        self.base_url = base_url
        self.session = httpx.Client(verify=verify_certificate)
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
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
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
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        resp = self.post(path, headers=headers, json=json, data=data)
        return cijson.loads(resp.text) if self._case_insensitive else stdjson.loads(resp.text)

    def post_text(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict[str, Any]] = None,
        data: Optional[Union[Dict[str, Any], str, bytes]] = None,
    ) -> str:
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
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
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
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
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
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
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        resp = self.get(path, headers=headers)
        return cijson.loads(resp.text) if self._case_insensitive else stdjson.loads(resp.text)

    def get_text(self, path: str, headers: Optional[Dict[str, str]] = None) -> str:
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
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
