"""Authentication domain types without infrastructure dependencies."""

from __future__ import annotations

import re
import unicodedata
from dataclasses import dataclass
from datetime import datetime
from enum import StrEnum
from uuid import UUID

_LOGIN_PATTERN = re.compile(r"^[\w.@+-]{3,100}$", re.UNICODE)


class Role(StrEnum):
    """Human RBAC roles enforced by the backend."""

    STUDENT = "student"
    TEACHER = "teacher"
    ADMINISTRATOR = "administrator"


class UserStatus(StrEnum):
    """Account lifecycle state."""

    ACTIVE = "active"
    DISABLED = "disabled"


@dataclass(frozen=True, slots=True)
class UserIdentity:
    """Authentication fields loaded for one user."""

    id: UUID
    login: str
    display_name: str
    password_hash: str
    status: UserStatus
    roles: frozenset[Role]


@dataclass(frozen=True, slots=True)
class Principal:
    """Authenticated session principal."""

    user_id: UUID
    login: str
    display_name: str
    roles: frozenset[Role]
    session_id: UUID
    csrf_hash: str
    expires_at: datetime


@dataclass(frozen=True, slots=True)
class LoginResult:
    """New opaque session material returned only to the HTTP boundary."""

    principal: Principal
    session_token: str
    csrf_token: str


class AuthError(Exception):
    """Base class for typed authentication failures."""


class InvalidCredentialsError(AuthError):
    """Credentials are invalid without revealing which field failed."""


class AuthenticationRequiredError(AuthError):
    """An opaque session is missing, invalid, expired, or revoked."""


class TooManyAttemptsError(AuthError):
    """Persistent brute-force policy currently blocks authentication."""


class PasswordPolicyError(AuthError):
    """A proposed password violates the server policy."""


class UserAlreadyExistsError(AuthError):
    """The normalized login is already assigned."""


class LastAdministratorError(AuthError):
    """An operation would remove the last active administrator."""


def normalize_login(value: str) -> str:
    """Normalize and validate a stable case-insensitive login key."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not _LOGIN_PATTERN.fullmatch(normalized):
        raise InvalidCredentialsError
    return normalized
