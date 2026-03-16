from __future__ import annotations

from typing import Optional

__all__ = [
    "DocuwareClientException",
    "AccountError",
    "DataError",
    "InternalError",
    "ApiError",
    "SearchConditionError",
    "ResourceError",
    "ResourceNotFoundError",
    "UserOrGroupError",
]


class DocuwareClientException(Exception):
    def __init__(
        self,
        *args,
        url: Optional[str] = None,
        status_code: Optional[int] = None,
        server_message: Optional[str] = None,
    ):
        super().__init__(*args)
        self.url = url
        self.status_code = status_code
        self.server_message = server_message

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
