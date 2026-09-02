"""Enforces the security schemes an Agent Card declares.

Only `api_key_security_scheme` and `http_auth_security_scheme` are actually
enforced here — see the `SecurityScheme` docstring in models.py for why
OAuth2/OIDC/mTLS stop at field-accurate modeling. Bearer-token verification
here is a static allow-list, not JWT signature verification: a real
deployment plugs in a `TokenValidator` (or reaches for a real OAuth2/OIDC
scheme instead of a bare bearer token) rather than hand-rolling one.
"""

from __future__ import annotations

from abc import ABC, abstractmethod

from .models import APIKeySecurityScheme, HTTPAuthSecurityScheme


class AuthenticationError(Exception):
    pass


class Authenticator(ABC):
    @abstractmethod
    def authenticate(self, headers: dict[str, str]) -> None:
        """Raise `AuthenticationError` on failure; return on success."""


class NoAuth(Authenticator):
    def authenticate(self, headers: dict[str, str]) -> None:
        return None


class ApiKeyAuthenticator(Authenticator):
    """Only `location: "header"` is enforced — query/cookie API keys need a
    transport-specific hook (FastAPI's `Query`/`Cookie` params) that a
    header check alone can't provide generically.
    """

    def __init__(self, scheme: APIKeySecurityScheme, valid_keys: set[str]):
        if scheme.location != "header":
            raise NotImplementedError(
                f"ApiKeyAuthenticator only enforces header-located keys, got {scheme.location!r}"
            )
        self.scheme = scheme
        self.valid_keys = valid_keys

    def authenticate(self, headers: dict[str, str]) -> None:
        key = headers.get(self.scheme.name.lower())
        if key is None or key not in self.valid_keys:
            raise AuthenticationError(f"missing or invalid API key {self.scheme.name!r}")


class BearerAuthenticator(Authenticator):
    def __init__(self, scheme: HTTPAuthSecurityScheme, valid_tokens: set[str]):
        if scheme.scheme.lower() != "bearer":
            raise NotImplementedError(
                f"BearerAuthenticator only enforces the Bearer scheme, got {scheme.scheme!r}"
            )
        self.scheme = scheme
        self.valid_tokens = valid_tokens

    def authenticate(self, headers: dict[str, str]) -> None:
        value = headers.get("authorization", "")
        prefix = "bearer "
        token = value[len(prefix) :].strip() if value.lower().startswith(prefix) else None
        if token is None or token not in self.valid_tokens:
            raise AuthenticationError("missing or invalid Bearer token")
