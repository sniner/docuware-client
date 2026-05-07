"""Persistence adapters for OAuth2 token bundles.

DocuWare's IdentityServer issues *rotating* refresh tokens with reuse
detection (RFC 6749 §10.4): every successful refresh response invalidates
the prior refresh token, and reuse of the prior token revokes the entire
token family. Clients that want to survive a process restart must
therefore persist the rotated tokens *every* time a refresh succeeds —
not only at first login.

:class:`TokenStore` is the adapter interface the library uses to do that
without taking a position on *where* tokens live (file, keyring, secrets
manager, database row, ...). Users supply a concrete implementation; the
library calls it at the right moments via
:func:`docuware.connect_with_tokens`.

A reference :class:`TokenStore` implementation backed by a JSON file is
shown in ``examples/oauth2_login.py``.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from typing import Any, Dict, Optional


class TokenStore(ABC):
    """Adapter for loading and persisting an OAuth2 token bundle.

    Implementations decide *where* tokens live. The library is responsible
    for *when* to call :meth:`save` — exactly once per successful refresh,
    so that the next process start sees the rotated refresh token.

    Implementations MUST persist atomically (e.g. write-temp + rename) so
    a crash mid-write cannot leave the store with no usable refresh token.
    See :func:`docuware.atomic_json_write` for a primitive that does this.
    """

    @abstractmethod
    def load(self) -> Optional[Dict[str, Any]]:
        """Return the stored token bundle, or ``None`` if nothing stored.

        Expected keys: ``access_token``, ``refresh_token``. Implementations
        may store additional fields (e.g. ``expires_at``, ``scope``); the
        library passes them through unchanged.
        """

    @abstractmethod
    def save(self, tokens: Dict[str, Any]) -> None:
        """Persist the given token bundle.

        Called after every successful refresh, and once initially in the
        bootstrap path when an empty store is seeded with explicit tokens.
        MUST be atomic.
        """
