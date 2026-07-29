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
    EDITOR = "editor"
    ADMINISTRATOR = "administrator"


class Permission(StrEnum):
    """Stable server-side capabilities used at authorization boundaries."""

    COMPONENTS_VIEW = "components.view"
    COMPONENTS_PROPOSE_CORRECTION = "components.propose_correction"
    COMPONENTS_CREATE = "components.create"
    COMPONENTS_EDIT = "components.edit"
    COMPONENTS_ARCHIVE = "components.archive"
    COMPONENTS_DELETE = "components.delete"
    COMPONENTS_SUBMIT_FOR_REVIEW = "components.submit_for_review"
    COMPONENTS_REVIEW = "components.review"
    COMPONENTS_PUBLISH = "components.publish"
    IMPORTS_VIEW = "imports.view"
    IMPORTS_CREATE = "imports.create"
    IMPORTS_RETRY = "imports.retry"
    IMPORTS_CANCEL = "imports.cancel"
    USERS_VIEW = "users.view"
    USERS_MANAGE = "users.manage"
    ROLES_ASSIGN = "roles.assign"
    AUDIT_VIEW = "audit.view"
    SYSTEM_SETTINGS = "system.settings"
    SYSTEM_DIAGNOSTICS = "system.diagnostics"


_VIEW_PERMISSIONS = frozenset({Permission.COMPONENTS_VIEW})
_EDITOR_PERMISSIONS = _VIEW_PERMISSIONS | frozenset(
    {
        Permission.COMPONENTS_CREATE,
        Permission.COMPONENTS_EDIT,
        Permission.COMPONENTS_ARCHIVE,
        Permission.COMPONENTS_SUBMIT_FOR_REVIEW,
        Permission.IMPORTS_VIEW,
        Permission.IMPORTS_CREATE,
        Permission.IMPORTS_RETRY,
        Permission.IMPORTS_CANCEL,
    }
)
_ROLE_PERMISSIONS: dict[Role, frozenset[Permission]] = {
    Role.STUDENT: _VIEW_PERMISSIONS,
    Role.TEACHER: _VIEW_PERMISSIONS | frozenset({Permission.COMPONENTS_PROPOSE_CORRECTION}),
    Role.EDITOR: _EDITOR_PERMISSIONS,
    Role.ADMINISTRATOR: frozenset(Permission),
}


def permissions_for_roles(roles: frozenset[Role]) -> frozenset[Permission]:
    """Resolve the union of capabilities granted by backend-loaded roles."""
    return frozenset(
        permission for role in roles for permission in _ROLE_PERMISSIONS.get(role, frozenset())
    )


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
class ManagedUserIdentity:
    """Safe account state shown in administrator user management."""

    id: UUID
    login: str
    display_name: str
    status: UserStatus
    roles: frozenset[Role]
    editor_expires_at: datetime | None


@dataclass(frozen=True, slots=True)
class AuditRecord:
    """Safe read model for one immutable audit event."""

    id: UUID
    occurred_at: datetime
    actor_user_id: UUID | None
    actor_type: str
    actor_login: str | None
    actor_display_name: str | None
    action: str
    object_type: str
    object_id: UUID | None
    outcome: str


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

    @property
    def permissions(self) -> frozenset[Permission]:
        """Resolve permissions without accepting client-provided capability data."""
        return permissions_for_roles(self.roles)

    def can(self, permission: Permission) -> bool:
        """Return whether this authenticated principal has one capability."""
        return permission in self.permissions


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


class RoleGrantPolicyError(AuthError):
    """A role grant has an invalid or missing lifetime."""


def normalize_login(value: str) -> str:
    """Normalize and validate a stable case-insensitive login key."""
    normalized = unicodedata.normalize("NFKC", value).strip().casefold()
    if not _LOGIN_PATTERN.fullmatch(normalized):
        raise InvalidCredentialsError
    return normalized
