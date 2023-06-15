import urllib.parse as urlparse
from typing import Any, Dict, Tuple

import requests

from docuware import cijson, errors, parser, utils


DEFAULT_HEADERS = {
    "User-Agent": "Python docuware-client",
}

JSON_HEADERS = {
    "Accept": "application/json",

}
TEXT_HEADERS = {
    "Accept": "text/plain",
}


class Connection:
    def __init__(self, base_url:str, case_insensitive:bool=True, cookiejar:dict=None):
        self.base_url = base_url
        self.session = requests.Session()
        self.cookiejar = cookiejar
        self._json_object_hook = cijson.case_insensitive_hook if case_insensitive else None

    @property
    def cookiejar(self):
        if self.session:
            cookies = requests.utils.dict_from_cookiejar(self.session.cookies)
        else:
            cookies = {}
        return cookies

    @cookiejar.setter
    def cookiejar(self, cookies:dict):
        if cookies:
            self.session.cookies.update(cookies)

    def make_path(self, path:str, query:dict) -> str:
        u = urlparse.urlsplit(path)
        q = "&".join(
            ([u.query] if u.query else []) +
            [f"{urlparse.quote_plus(k)}={urlparse.quote_plus(v)}" for k,v in query.items()])
        return urlparse.urlunsplit(u._replace(query=q))

    def make_url(self, path:str, query:dict=None) -> str:
        if query:
            path = self.make_path(path, query)
        return urlparse.urljoin(self.base_url, path)

    def _post(self, url:str, headers:Dict[str,str]=None, json:dict=None, data:Any=None):
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        return self.session.post(url, headers=headers, json=json, data=data)

    def post(self, path:str, headers:Dict[str,str]=None, json:dict=None, data:Any=None):
        url = self.make_url(path)
        resp = self._post(url, headers=headers, json=json, data=data)
        if resp.status_code==200:
            return resp
        else:
            raise errors.ResourceError(
                f"POST request failed with code {resp.status_code}",
                url=url,
                status_code=resp.status_code
            )

    def post_json(self, path:str, headers:Dict[str,str]=None, json:dict=None, data:Any=None):
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.post(path, headers=headers, json=json, data=data).json(object_hook=self._json_object_hook)

    def post_text(self, path:str, headers:Dict[str,str]=None, json:dict=None, data:Any=None):
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.post(path, headers=headers, json=json, data=data).text

    def _put(self, url:str, headers:Dict[str,str]=None, params:Any=None, json:dict=None, data:Any=None):
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        return self.session.put(url, headers=headers, params=params, json=json, data=data)

    def put(self, path:str, headers:Dict[str,str]=None, params:Any=None, json:dict=None, data:Any=None):
        url = self.make_url(path)
        resp = self._put(url, headers=headers, params=params, json=json, data=data)
        if resp.status_code==200:
            return resp
        else:
            raise errors.ResourceError(
                f"PUT request failed with code {resp.status_code} and message \'{resp.content}\'",
                url=url,
                status_code=resp.status_code
            )

    def put_json(self, path:str, headers:Dict[str,str]=None, params:Any=None, json:dict=None, data:Any=None):
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.put(path, headers=headers, params=params, json=json, data=data).json(object_hook=self._json_object_hook)

    def put_text(self, path:str, headers:Dict[str,str]=None, params:Any=None, json:dict=None, data:Any=None):
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.put(path, headers=headers, params=params, json=json, data=data).text

    def _get(self, url:str, headers:Dict[str,str]=None, data:Any=None):
        headers = {**DEFAULT_HEADERS, **headers} if headers else DEFAULT_HEADERS
        return self.session.get(url, headers=headers, data=data)

    def get(self, path:str, headers:Dict[str,str]=None, data:Any=None):
        url = self.make_url(path)
        resp = self._get(url, headers=headers, data=data)
        if resp.status_code==200:
            return resp
        else:
            raise errors.ResourceError(
                f"GET request failed with code {resp.status_code}",
                url=url,
                status_code=resp.status_code
            )

    def get_json(self, path:str, headers:Dict[str,str]=None):
        headers = {**headers, **JSON_HEADERS} if headers else JSON_HEADERS
        return self.get(path, headers=headers).json(object_hook=self._json_object_hook)

    def get_text(self, path:str, headers:Dict[str,str]=None):
        headers = {**headers, **TEXT_HEADERS} if headers else TEXT_HEADERS
        return self.get(path, headers=headers).text

    def get_bytes(self, path:str, mime_type:str=None, data:Any=None) -> Tuple[bytes,str,str]:
        url = self.make_url(path)
        resp = self._get(url, headers={"Accept": mime_type if mime_type else "*/*"}, data=data)
        if resp.status_code==200:
            content_type = resp.headers.get("Content-Type", "application/octet-stream")
            content_length = resp.headers.get("Content-Length")
            content_disposition = parser.parse_content_disposition(resp.headers.get("Content-Disposition"))
            if content_length and len(resp.content)!=int(content_length):
                raise errors.ResourceError(
                    f"Unexpected content length: expected {content_length}, got {len(resp.content)}",
                    url=url, status_code=resp.status_code)
            return resp.content, content_type, content_disposition.get("filename", "unknown.bin")
        raise errors.ResourceNotFoundError(
            f"Download failed, code {resp.status_code}",
            url=url, status_code=resp.status_code)


# vim: set et sw=4 ts=4: