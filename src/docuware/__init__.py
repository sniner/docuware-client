from docuware.client import DocuwareClient, connect, connect_with_tokens
from docuware.auth import (
    Authenticator,
    ClientCredentialsAuthenticator,
    OAuth2Authenticator,
    PasswordGrantAuthenticator,
    PkceAuthenticator,
    TokenAuthenticator,
)
from docuware.dialogs import InfoDialog, Operation, QuoteMode, ResultTree, SearchDialog
from docuware.errors import (
    AccountError,
    ApiError,
    DataError,
    DocuwareClientException,
    InternalError,
    OAuthDiscoveryError,
    ResourceError,
    ResourceNotFoundError,
    SearchConditionError,
    UserOrGroupError,
)
from docuware.filecabinet import Basket, FileCabinet
from docuware.oauth import (
    DW_OAUTH_SCOPES,
    OAuthEndpoints,
    build_authorization_url,
    discover_oauth_endpoints,
    exchange_pkce_code,
    generate_pkce,
    normalize_docuware_url,
)
from docuware.organization import Organization
from docuware.persistence import CredentialStore, JsonFileCredentialStore, TokenStore
from docuware.textshot import TableZone, TextLine, TextPage, TextShot, TextZone, Word
from docuware.users import (
    Group,
    User,
)
from docuware.utils import (
    atomic_json_write,
    default_credentials_file,
    quote_value,
    random_password,
    unique_filename,
    write_binary_file,
)

Client = DocuwareClient

__all__ = [
    "AccountError",
    "ApiError",
    "Authenticator",
    "Basket",
    "Client",
    "ClientCredentialsAuthenticator",
    "CredentialStore",
    "DataError",
    "DocuwareClientException",
    "DocuwareClient",
    "FileCabinet",
    "Group",
    "InfoDialog",
    "InternalError",
    "JsonFileCredentialStore",
    "OAuth2Authenticator",
    "OAuthDiscoveryError",
    "Operation",
    "Organization",
    "PasswordGrantAuthenticator",
    "PkceAuthenticator",
    "QuoteMode",
    "ResultTree",
    "ResourceError",
    "ResourceNotFoundError",
    "SearchConditionError",
    "SearchDialog",
    "TableZone",
    "TextLine",
    "TextPage",
    "TextShot",
    "TextZone",
    "TokenAuthenticator",
    "TokenStore",
    "User",
    "UserOrGroupError",
    "Word",
    "DW_OAUTH_SCOPES",
    "OAuthEndpoints",
    "atomic_json_write",
    "build_authorization_url",
    "connect",
    "connect_with_tokens",
    "default_credentials_file",
    "discover_oauth_endpoints",
    "exchange_pkce_code",
    "generate_pkce",
    "normalize_docuware_url",
    "quote_value",
    "random_password",
    "unique_filename",
    "write_binary_file",
]
