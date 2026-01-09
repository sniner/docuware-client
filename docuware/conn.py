from __future__ import annotations
import logging
import requests
import urllib.parse as urlparse
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Tuple

from requests.models import Response

from docuware import cijson, errors, parser, types, utils

from urllib3.exceptions import InsecureRequestWarning
from urllib3 import disable_warnings

from docuware.organization import Organization
disable_warnings(InsecureRequestWarning)


log = logging.getLogger(__name__)


DEFAULT_HEADERS = {
    "User-Agent": "Python docuware-client",
}

JSON_HEADERS = {
    "Accept": "application/json",
}

TEXT_HEADERS = {
    "Accept": "text/plain",
}

class Authenticator(ABC, types.AuthenticatorP):
    @abstractmethod
    def authenticate(self, conn: types.ConnectionP) -> requests.Session:
        ...

    @abstractmethod
    def login(self, conn: types.ConnectionP) -> Dict:
        ...

    @abstractmethod
    def logoff(self, conn: types.ConnectionP) -> None:
        ...

    def _get(self, conn: types.ConnectionP, path: str) -> Dict:
        url = conn.make_url(path)
        resp = conn.session.get(url, headers={**DEFAULT_HEADERS, **JSON_HEADERS})
        if resp.status_code == 200:
            return resp.json(object_hook=conn._json_object_hook)
        raise errors.ResourceError("Failed to get resource", url=url, status_code=resp.status_code)

    def _post(
        self,
        conn: types.ConnectionP,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        data: Optional[Any] = None
    ) -> Dict:
        url = conn.make_url(path)
        headers = {**DEFAULT_HEADERS, **(headers or {}), **JSON_HEADERS}
        resp = conn.session.post(url, headers=headers, data=data)
        if resp.status_code == 200:
            return resp.json(object_hook=conn._json_object_hook)
        raise errors.ResourceError("Failed to post to resource", url=url, status_code=resp.status_code)

class CookieAuthenticator(Authenticator):
    def __init__(
        self,
        username: Optional[str] = None,
        password: Optional[str] = None,
        organization: Optional[str] = None,
        saved_state: Optional[Dict] = None,
    ):
        self.password = password
        self.username = username
        self.organization = organization
        self.cookies = saved_state
        self.result: Optional[Dict] = None
        self._warn = True

    def authenticate(self, conn: types.ConnectionP) -> requests.Session:
        if self.cookies:
            log.debug("Authenticating with cookies")
            conn.session.cookies.update(self.cookies)
        else:
            if self._warn:
                log.warning("Cookie authentication not available")
                self._warn = False
        return conn.session

    def login(self, conn: types.ConnectionP) -> dict:
        endpoint = "/DocuWare/Platform/Account/Logon"

        headers = {
            "Content-Type": "application/x-www-form-urlencoded",
            "Accept": "application/json",
        }
        data = {
            "LoginType": "DocuWare",
            "RedirectToMyselfInCaseOfError": "false",
            "RememberMe": "false",
            "Password": self.password,
            "UserName": self.username,
        }
        if self.organization:
            data["Organization"] = self.organization

        try:
            self.result = self._post(conn, endpoint, headers=headers, data=data)
            self.cookies = requests.utils.dict_from_cookiejar(conn.session.cookies)
            return self.cookies
        except errors.ResourceError as exc:
            raise errors.AccountError(f"Log in failed with code {exc.status_code}")

    def logoff(self, conn: types.ConnectionP) -> None:
        self._get(conn, "/DocuWare/Platform/Account/Logoff")


class OAuth2Authenticator(Authenticator):
    def __init__(
        self,
        username: Optional[str],
        password: Optional[str],
        organization: Optional[str] = None,
        saved_state: Optional[Dict] = None,
    ):
        self.password = password
        self.username = username
        self.organization = organization
        self.token = (saved_state or {}).get("access_token")
        self.result: Dict = {}

    def _apply_access_token(self, conn: types.ConnectionP, token: Optional[str]) -> None:
        if token:
            conn.session.headers.update({
               "Authorization": f"Bearer {token}"
            })
        else:
            if "Authorization" in conn.session.headers:
                del conn.session.headers["Authorization"]

    def _get_access_token(self, conn: types.ConnectionP) -> Optional[str]:
        log.debug("Requesting access token")
        try:
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
                "scope": "docuware.platform"
            }
            self.result = self._post(conn, path, data=data)
            token = self.result.get("access_token")
            if not token:
               raise errors.ResourceError(status_code=599)
            return token
        except errors.ResourceError as exc:
            log.warning("Failed to get access token (%s)", exc.status_code)
        return None

    def authenticate(self, conn: types.ConnectionP) -> requests.Session:
        self.token = self._get_access_token(conn)
        self._apply_access_token(conn, self.token)
        return conn.session

    def login(self, conn: types.ConnectionP) -> Dict[str, Optional[str]]:
        self._apply_access_token(conn, self.token)
        conn.session = self.authenticate(conn)
        return {
            "access_token": self.token,
        }

    def logoff(self, conn: types.ConnectionP) -> None:
        if self.token:
            # FIXME: How to revoke an access token?
            #self._get(conn, "/DocuWare/Identity/connect/revocation")
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
        self.session = requests.Session()
        self.session.verify = verify_certificate
        self.authenticator = authenticator
        self._json_object_hook = cijson.case_insensitive_hook if case_insensitive else None

    def make_path(self, path: str, query: Dict[str, str]) -> str:
        u = urlparse.urlsplit(path)
        q = "&".join(
            ([u.query] if u.query else []) +
            [f"{urlparse.quote_plus(k)}={urlparse.quote_plus(v)}" for k, v in query.items()])
        return urlparse.urlunsplit(u._replace(query=q))

    def make_url(self, path: str, query: Optional[Dict[str, str]] = None) -> str:
        if query:
            path = self.make_path(path, query)
        return urlparse.urljoin(self.base_url, path)

    def _post(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None
    ) -> Response:
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        resp = self.session.post(url, headers=headers, json=json, data=data)
        if resp.status_code in (401, 403) and self.authenticator:
            self.session = self.authenticator.authenticate(self)
            resp = self.session.post(url, headers=headers, json=json, data=data)
        return resp

    def post(
        self,
        path: str,
        headers: Optional[Dict[str, str]] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None
    ) -> Response:
        url = self.make_url(path)
        resp = self._post(url, headers=headers, json=json, data=data)
        if resp.status_code == 200:
            return resp
        else:
            raise errors.ResourceError(
                f"POST request failed with code {resp.status_code}",
                url=url,
                status_code=resp.status_code
            )

    def post_json(self, path: str, headers: Optional[Dict[str, str]] = None, json: Optional[Dict] = None, data: Optional[Any] = None) -> Any:
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.post(path, headers=headers, json=json, data=data).json(object_hook=self._json_object_hook)

    def post_text(self, path: str, headers: Optional[Dict[str, str]] = None, json: Optional[Dict] = None, data: Optional[Any] = None) -> str:
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.post(path, headers=headers, json=json, data=data).text

    def _put(self, url: str, headers: Optional[Dict[str, str]] = None, params: Optional[Any] = None, json: Optional[Dict] = None, data: Optional[Any] = None) -> Response:
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        resp = self.session.put(url, headers=headers, params=params, json=json, data=data)
        if resp.status_code in (401, 403) and self.authenticator:
            self.session = self.authenticator.authenticate(self)
            resp = self.session.put(url, headers=headers, params=params, json=json, data=data)
        return resp

    def put(self, path: str, headers: Optional[Dict[str, str]] = None, params: Optional[Any] = None, json: Optional[Dict] = None, data: Optional[Any] = None) -> Response:
        url = self.make_url(path)
        resp = self._put(url, headers=headers, params=params, json=json, data=data)
        if resp.status_code == 200:
            return resp
        else:
            raise errors.ResourceError(
                f"PUT request failed with code {resp.status_code} and message \'{resp.content}\'",
                url=url,
                status_code=resp.status_code
            )

    def put_json(self, path: str, headers: Optional[Dict[str, str]] = None, params: Optional[Any] = None, json: Optional[Dict] = None,
                 data: Optional[Any] = None) -> Any:
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.put(path, headers=headers, params=params, json=json, data=data).json(
            object_hook=self._json_object_hook)

    def put_text(self, path: str, headers: Optional[Dict[str, str]] = None, params: Optional[Any] = None, json: Optional[Dict] = None,
                 data: Optional[Any] = None) -> str:
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.put(path, headers=headers, params=params, json=json, data=data).text

    def _get(self, url: str, headers: Optional[Dict[str, str]] = None, data: Optional[Any] = None) -> Response:
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        resp = self.session.get(url, headers=headers, data=data)
        if resp.status_code in (401, 403) and self.authenticator:
            self.session = self.authenticator.authenticate(self)
            resp = self.session.get(url, headers=headers, data=data)
        return resp

    def get(self, path: str, headers: Optional[Dict[str, str]] = None, data: Optional[Any] = None) -> Response:
        url = self.make_url(path)
        resp = self._get(url, headers=headers, data=data)
        if resp.status_code == 200:
            return resp
        else:
            raise errors.ResourceError(
                f"GET request failed with code {resp.status_code}",
                url=url,
                status_code=resp.status_code
            )

    def get_json(self, path: str, headers: Optional[Dict[str, str]] = None) -> Any:
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.get(path, headers=headers).json(object_hook=self._json_object_hook)

    def get_text(self, path: str, headers: Optional[Dict[str, str]] = None) -> str:
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.get(path, headers=headers).text

    def _delete(
        self,
        url: str,
        headers: Optional[Dict[str, str]] = None,
        params: Optional[Any] = None,
        json: Optional[Dict] = None,
        data: Optional[Any] = None
    ) -> Response:
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        resp = self.session.delete(url, headers=headers, params=params, json=json, data=data)
        if resp.status_code in (401, 403) and self.authenticator:
            self.session = self.authenticator.authenticate(self)
            resp = self.session.delete(url, headers=headers, params=params, json=json, data=data)
        return resp

    def delete(self, path: str, headers: Optional[Dict[str, str]] = None) -> Response:
        url = self.make_url(path)
        resp = self._delete(url, headers=headers)
        if resp.status_code == 200:
            return resp
        else:
            raise errors.ResourceError(
                f"DELETE request failed with code {resp.status_code}",
                url=url,
                status_code=resp.status_code
            )

    def get_bytes(
        self,
        path: str,
        mime_type: Optional[str] = None,
        data: Optional[Any] = None
    ) -> Tuple[bytes, str, str]:
        url = self.make_url(path)
        resp = self._get(url, headers={"Accept": mime_type if mime_type else "*/*"}, data=data)
        if resp.status_code == 200:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content_length = resp.headers.get("Content-Length")
            content_disposition = parser.parse_content_disposition(resp.headers.get("Content-Disposition", ""))
            if content_length and len(resp.content) != int(content_length):
                raise errors.ResourceError(
                    f"Unexpected content length: expected {content_length}, got {len(resp.content)}",
                    url=url, status_code=resp.status_code)
            return resp.content, content_type, content_disposition.get("filename") or "unknown.bin"
        raise errors.ResourceNotFoundError(
            f"Download failed, code {resp.status_code}",
            url=url,
            status_code=resp.status_code,
        )

# vim: set et sw=4 ts=4:
