from __future__ import annotations
from typing import Optional


class DocuwareClientException(Exception):
    def __init__(self, *args, url: Optional[str] = None, status_code: Optional[int] = None):
        super().__init__(*args)
        self.url = url
        self.status_code = status_code

    def __str__(self) -> str:
        if self.url:
            return f"[{self.url}] {super().__str__()}"
        else:
            return super().__str__()


class AccountError(DocuwareClientException):
    pass


class DataError(DocuwareClientException):
    pass


class InternalError(DocuwareClientException):
    pass


class ApiError(DocuwareClientException):
    pass


class SearchConditionError(ApiError):
    pass


class ResourceError(ApiError):
    pass


class ResourceNotFoundError(ApiError):
    pass


class UserOrGroupError(ApiError):
    pass

# vim: set et sw=4 ts=4:
