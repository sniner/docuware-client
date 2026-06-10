"""Verify the 0.8.0 deprecation aliases continue to work, with warnings.

Companion to :mod:`tests.test_persistence` (which covers the ``TokenStore``
→ ``CredentialStore`` deprecation).
"""
from __future__ import annotations

import warnings

import pytest

import docuware
from docuware import OAuth2Authenticator, PasswordGrantAuthenticator, errors


def test_oauth2authenticator_instantiation_warns():
    with pytest.warns(DeprecationWarning, match="OAuth2Authenticator is deprecated"):
        OAuth2Authenticator("u", "p")


def test_oauth2authenticator_is_password_grant_subclass():
    """Existing isinstance() checks against PasswordGrantAuthenticator keep working."""
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        auth = OAuth2Authenticator("u", "p", organization="o")
    assert isinstance(auth, PasswordGrantAuthenticator)
    assert auth.username == "u"
    assert auth.password == "p"
    assert auth.organization == "o"
    assert auth.METHOD == "password"


def test_oauth2authenticator_to_bundle_uses_password_method():
    with warnings.catch_warnings():
        warnings.simplefilter("ignore", DeprecationWarning)
        auth = OAuth2Authenticator("u", "p")
    bundle = auth.to_bundle()
    assert bundle["method"] == "password"
    assert bundle["username"] == "u"


def test_connect_with_tokens_warns():
    with pytest.warns(DeprecationWarning, match="connect_with_tokens is deprecated"):
        # Fails validation (no tokens given) — the warning must fire first
        with pytest.raises(errors.AccountError):
            docuware.connect_with_tokens("https://dw.example.com")
