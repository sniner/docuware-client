"""Persistence adapters for auth credential bundles.

DocuWare supports four auth flows, each with its own credential bundle shape.
:class:`CredentialStore` is the adapter interface the library uses to persist
those bundles across process restarts, without taking a position on *where*
they live (file, keyring, secrets manager, …). Users supply a concrete
implementation; the library calls it at the right moments.

Bundle shape depends on the auth ``method``:

- ``method="password"``           — ``url``, ``username``, ``password``,
                                    ``organization``
- ``method="client_credentials"`` — ``url``, ``client_id``, ``client_secret``,
                                    optionally ``scope``
- ``method="pkce"``               — ``url``, ``client_id``, optionally
                                    ``client_secret``, ``access_token``,
                                    ``refresh_token``, ``token_endpoint``
- ``method="token"``              — like ``pkce`` (bring-your-own tokens)

The ``method`` field is optional in stored bundles and defaults to
``"password"`` when absent — keeps existing ``.credentials`` files (and
consumers like ``docuware-mcp``) working unchanged.

The library ships a reference :class:`JsonFileCredentialStore`; most callers
will use it directly rather than write their own adapter.
"""

from __future__ import annotations

import json
import logging
import pathlib
import warnings
from abc import ABC, abstractmethod
from typing import Any, Dict, Optional, Union

from docuware.utils import atomic_json_write, default_credentials_file

log = logging.getLogger(__name__)


class CredentialStore(ABC):
    """Adapter for loading and persisting an auth credential bundle.

    Implementations decide *where* credentials live. The library is
    responsible for *when* to call :meth:`save`:

      - once after first login (initial seed)
      - after every successful token refresh (PKCE token rotation)

    Implementations MUST persist atomically (e.g. write-temp + rename) so a
    crash mid-write cannot leave the store with no usable credentials. See
    :func:`docuware.atomic_json_write` for a primitive that does this.
    """

    @abstractmethod
    def load(self) -> Optional[Dict[str, Any]]:
        """Return the stored credential bundle, or ``None`` if nothing stored.

        Bundle keys depend on ``method`` — see the module docstring.
        """

    @abstractmethod
    def save(self, bundle: Dict[str, Any]) -> None:
        """Persist the given credential bundle. MUST be atomic.

        Called after the initial login (seed) and after every successful
        token refresh (PKCE rotation).
        """


class JsonFileCredentialStore(CredentialStore):
    """CredentialStore backed by a JSON file with atomic writes.

    Files are written with mode 0o600 on each save. Parent directories are
    created on demand. UTF-8 with optional BOM is supported on read.

    If ``path`` is omitted, falls back to
    :func:`docuware.default_credentials_file` — i.e. the same default location
    the legacy ``connect(credentials_file=...)`` path uses.
    """

    def __init__(self, path: Optional[Union[str, pathlib.Path]] = None) -> None:
        if path is None:
            path = default_credentials_file()
        self.path = pathlib.Path(path).expanduser()

    def load(self) -> Optional[Dict[str, Any]]:
        if not self.path.exists():
            return None
        try:
            with open(self.path, encoding="utf-8-sig") as f:
                return json.load(f)
        except (json.JSONDecodeError, OSError) as exc:
            log.warning("Failed to load credentials from %s: %s", self.path, exc)
            return None

    def save(self, bundle: Dict[str, Any]) -> None:
        atomic_json_write(self.path, bundle, indent=4)


class TokenStore(CredentialStore):
    """Deprecated alias for :class:`CredentialStore`.

    The 0.7.14 ``TokenStore`` adapter has been generalized to
    :class:`CredentialStore`, which handles password, client_credentials,
    PKCE and bring-your-own-token bundles uniformly. Subclassing
    ``TokenStore`` still works but triggers a :class:`DeprecationWarning`.
    """

    def __init_subclass__(cls, **kwargs: Any) -> None:
        super().__init_subclass__(**kwargs)
        warnings.warn(
            "TokenStore is deprecated, subclass CredentialStore instead",
            DeprecationWarning,
            stacklevel=2,
        )
