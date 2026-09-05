"""Authentication, session, RBAC administration, and audit services."""

from __future__ import annotations

import hashlib
import hmac
import secrets
from datetime import UTC, datetime, timedelta
from uuid import UUID

from arduino_component_kb.auth.domain import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LastAdministratorError,
    LoginResult,
    ManagedUserIdentity,
    Principal,
    Role,
    RoleGrantPolicyError,
    TooManyAttemptsError,
    UserAlreadyExistsError,
    UserIdentity,
    UserStatus,
    normalize_login,
)
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings


def token_hash(value: str) -> str:
    """Hash opaque session material before persistence or comparison."""
    return hashlib.sha256(value.encode()).hexdigest()


class AuthService:
    """Coordinate authentication policies inside a transaction."""

    def __init__(
        self,
        repository: AuthRepository,
        settings: Settings,
        passwords: PasswordManager,
    ) -> None:
        self.repository = repository
        self.settings = settings
        self.passwords = passwords

    async def login(
        self,
        *,
        login: str,
        password: str,
        client_identifier: str,
        request_id: str | None,
    ) -> LoginResult:
        now = datetime.now(UTC)
        try:
            normalized_login = normalize_login(login)
        except InvalidCredentialsError:
            normalized_login = "\x00invalid-login"
        keys = self._throttle_keys(normalized_login, client_identifier)
        if await self.repository.is_blocked(keys, now):
            await self.repository.audit(
                now=now,
                actor_user_id=None,
                action="auth.login",
                object_type="session",
                object_id=None,
                request_id=request_id,
                outcome="blocked",
            )
            raise TooManyAttemptsError

        user = await self.repository.find_user_by_login(normalized_login)
        valid = self.passwords.verify(user.password_hash if user else None, password)
        if user is None or not valid or user.status is not UserStatus.ACTIVE:
            await self.repository.register_failure(
                keys,
                now,
                window_seconds=self.settings.auth_failure_window_seconds,
                failure_limit=self.settings.auth_failure_limit,
                block_seconds=self.settings.auth_block_seconds,
            )
            await self.repository.audit(
                now=now,
                actor_user_id=user.id if user else None,
                action="auth.login",
                object_type="session",
                object_id=None,
                request_id=request_id,
                outcome="failed",
            )
            raise InvalidCredentialsError

        await self.repository.clear_failures(keys)
        result = await self._start_session(user, now)
        replacement_hash = (
            self.passwords.hash(password)
            if self.passwords.needs_rehash(user.password_hash)
            else None
        )
        await self.repository.mark_login(user.id, now, replacement_hash)
        await self.repository.audit(
            now=now,
            actor_user_id=user.id,
            action="auth.login",
            object_type="session",
            object_id=result.principal.session_id,
            request_id=request_id,
            outcome="success",
        )
        return result

    async def register(
        self,
        *,
        login: str,
        password: str,
        client_identifier: str,
        request_id: str | None,
    ) -> LoginResult:
        """Create a self-registered student and its first server-side session."""
        normalized = normalize_login(login)
        now = datetime.now(UTC)
        throttle_keys = (self._throttle_key("registration_client", client_identifier),)
        if await self.repository.is_blocked(throttle_keys, now):
            await self.repository.audit(
                now=now,
                actor_user_id=None,
                action="identity.self_registration",
                object_type="user",
                object_id=None,
                request_id=request_id,
                outcome="blocked",
            )
            raise TooManyAttemptsError
        await self.repository.register_failure(
            throttle_keys,
            now,
            window_seconds=self.settings.auth_failure_window_seconds,
            failure_limit=self.settings.auth_failure_limit,
            block_seconds=self.settings.auth_block_seconds,
        )
        await self.repository.lock_login(normalized)
        if await self.repository.find_user_by_login(normalized) is not None:
            raise UserAlreadyExistsError
        user = await self.repository.create_user(
            login=normalized,
            display_name=normalized,
            password_hash=self.passwords.hash(password),
            roles=frozenset({Role.STUDENT}),
            actor_id=None,
            now=now,
        )
        result = await self._start_session(user, now)
        await self.repository.mark_login(user.id, now, None)
        await self.repository.audit(
            now=now,
            actor_user_id=user.id,
            action="identity.self_registered",
            object_type="user",
            object_id=user.id,
            request_id=request_id,
            outcome="success",
            details={"roles": [Role.STUDENT.value]},
        )
        return result

    async def authenticate(self, raw_session: str | None) -> Principal:
        if raw_session is None or len(raw_session) > 256:
            raise AuthenticationRequiredError
        principal = await self.repository.resolve_session(
            token_hash(raw_session), datetime.now(UTC)
        )
        if principal is None:
            raise AuthenticationRequiredError
        return principal

    async def logout(self, principal: Principal, request_id: str | None) -> None:
        now = datetime.now(UTC)
        await self.repository.revoke_session(principal.session_id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=principal.user_id,
            action="auth.logout",
            object_type="session",
            object_id=principal.session_id,
            request_id=request_id,
            outcome="success",
        )

    async def create_user(
        self,
        *,
        actor: Principal,
        login: str,
        display_name: str,
        password: str,
        roles: frozenset[Role],
        request_id: str | None,
        editor_expires_at: datetime | None = None,
    ) -> UserIdentity:
        normalized = normalize_login(login)
        await self.repository.lock_login(normalized)
        if await self.repository.find_user_by_login(normalized) is not None:
            raise UserAlreadyExistsError
        if not roles:
            roles = frozenset({Role.STUDENT})
        now = datetime.now(UTC)
        self._validate_role_lifetime(roles, editor_expires_at, now)
        user = await self.repository.create_user(
            login=normalized,
            display_name=display_name.strip(),
            password_hash=self.passwords.hash(password),
            roles=roles,
            actor_id=actor.user_id,
            now=now,
            editor_expires_at=editor_expires_at,
        )
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.user_created",
            object_type="user",
            object_id=user.id,
            request_id=request_id,
            outcome="success",
            details={
                "roles": sorted(role.value for role in roles),
                "editor_expires_at": (
                    editor_expires_at.isoformat() if editor_expires_at is not None else None
                ),
            },
        )
        return user

    async def list_users(self) -> tuple[ManagedUserIdentity, ...]:
        """Return safe administrator-facing account state."""
        return await self.repository.list_users(datetime.now(UTC))

    async def list_administrators(self) -> tuple[ManagedUserIdentity, ...]:
        """Return only active administrator accounts for the dedicated workspace."""
        users = await self.repository.list_users(datetime.now(UTC))
        return tuple(
            user
            for user in users
            if user.status is UserStatus.ACTIVE and Role.ADMINISTRATOR in user.roles
        )

    async def create_administrator(
        self,
        *,
        actor: Principal,
        login: str,
        password: str,
        request_id: str | None,
    ) -> UserIdentity:
        """Create an administrator without accepting role or permission input."""
        normalized = normalize_login(login)
        await self.repository.lock_administrator_membership()
        await self.repository.lock_login(normalized)
        if await self.repository.find_user_by_login(normalized) is not None:
            raise UserAlreadyExistsError
        now = datetime.now(UTC)
        user = await self.repository.create_user(
            login=normalized,
            display_name=normalized,
            password_hash=self.passwords.hash(password),
            roles=frozenset({Role.ADMINISTRATOR}),
            actor_id=actor.user_id,
            now=now,
        )
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.administrator_created",
            object_type="user",
            object_id=user.id,
            request_id=request_id,
            outcome="success",
            details={"roles": [Role.ADMINISTRATOR.value]},
        )
        return user

    async def reset_password(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        password: str,
        request_id: str | None,
    ) -> None:
        """Replace a local password, revoke sessions, and record no credential material."""
        user = await self._existing_user(user_id)
        now = datetime.now(UTC)
        password_hash = self.passwords.hash(password)
        await self.repository.set_password(user.id, password_hash, now)
        await self.repository.revoke_user_sessions(user.id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.password_reset",
            object_type="user",
            object_id=user.id,
            request_id=request_id,
            outcome="success",
        )

    async def grant_editor(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        expires_at: datetime,
        request_id: str | None,
    ) -> None:
        """Grant temporary editorial access without changing baseline roles."""
        await self.repository.lock_administrator_membership()
        user = await self._existing_user(user_id)
        now = datetime.now(UTC)
        if user.status is not UserStatus.ACTIVE or Role.ADMINISTRATOR in user.roles:
            raise RoleGrantPolicyError
        effective_roles = user.roles | frozenset({Role.EDITOR})
        self._validate_role_lifetime(effective_roles, expires_at, now)
        await self.repository.grant_editor(user_id, actor.user_id, now, expires_at)
        await self.repository.revoke_user_sessions(user_id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action=(
                "identity.editor_expiry_changed"
                if Role.EDITOR in user.roles
                else "identity.editor_granted"
            ),
            object_type="user",
            object_id=user_id,
            request_id=request_id,
            outcome="success",
            details={"editor_expires_at": expires_at.isoformat()},
        )

    async def revoke_editor(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        request_id: str | None,
    ) -> None:
        """Revoke temporary editorial access without deleting grant history."""
        await self.repository.lock_administrator_membership()
        user = await self._existing_user(user_id)
        if Role.EDITOR not in user.roles:
            raise RoleGrantPolicyError
        now = datetime.now(UTC)
        await self.repository.revoke_editor(user_id, now)
        await self.repository.revoke_user_sessions(user_id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.editor_revoked",
            object_type="user",
            object_id=user_id,
            request_id=request_id,
            outcome="success",
        )

    async def set_roles(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        roles: frozenset[Role],
        request_id: str | None,
        editor_expires_at: datetime | None = None,
    ) -> None:
        await self.repository.lock_administrator_membership()
        user = await self._existing_user(user_id)
        if Role.ADMINISTRATOR in user.roles and Role.ADMINISTRATOR not in roles:
            if await self.repository.count_active_administrators() <= 1:
                raise LastAdministratorError
        now = datetime.now(UTC)
        effective_roles = roles or frozenset({Role.STUDENT})
        self._validate_role_lifetime(effective_roles, editor_expires_at, now)
        await self.repository.set_roles(
            user_id,
            effective_roles,
            actor.user_id,
            now,
            editor_expires_at=editor_expires_at,
        )
        await self.repository.revoke_user_sessions(user_id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.roles_changed",
            object_type="user",
            object_id=user_id,
            request_id=request_id,
            outcome="success",
            details={
                "roles": sorted(role.value for role in effective_roles),
                "editor_expires_at": (
                    editor_expires_at.isoformat() if editor_expires_at is not None else None
                ),
            },
        )

    async def disable_user(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        request_id: str | None,
    ) -> None:
        await self.repository.lock_administrator_membership()
        user = await self._existing_user(user_id)
        if (
            Role.ADMINISTRATOR in user.roles
            and await self.repository.count_active_administrators() <= 1
        ):
            raise LastAdministratorError
        now = datetime.now(UTC)
        await self.repository.disable_user(user_id, now)
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.user_disabled",
            object_type="user",
            object_id=user_id,
            request_id=request_id,
            outcome="success",
        )

    async def _existing_user(self, user_id: UUID) -> UserIdentity:
        user = await self.repository.find_user(user_id)
        if user is None:
            raise AuthenticationRequiredError
        return user

    @staticmethod
    def _validate_role_lifetime(
        roles: frozenset[Role],
        editor_expires_at: datetime | None,
        now: datetime,
    ) -> None:
        has_editor = Role.EDITOR in roles
        if has_editor != (editor_expires_at is not None):
            raise RoleGrantPolicyError
        if has_editor and roles.isdisjoint({Role.STUDENT, Role.TEACHER, Role.ADMINISTRATOR}):
            raise RoleGrantPolicyError
        if editor_expires_at is not None and (
            editor_expires_at.tzinfo is None or editor_expires_at <= now
        ):
            raise RoleGrantPolicyError

    def _throttle_keys(self, login: str, client_identifier: str) -> tuple[str, str]:
        return self._throttle_key("account", login), self._throttle_key("client", client_identifier)

    def _throttle_key(self, kind: str, value: str) -> str:
        pepper = self.settings.auth_throttle_pepper.get_secret_value().encode()
        return hmac.new(pepper, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()

    async def _start_session(self, user: UserIdentity, now: datetime) -> LoginResult:
        raw_session = secrets.token_urlsafe(32)
        raw_csrf = secrets.token_urlsafe(32)
        expires_at = now + timedelta(minutes=self.settings.session_ttl_minutes)
        principal = await self.repository.create_session(
            user,
            token_hash=token_hash(raw_session),
            csrf_hash=token_hash(raw_csrf),
            now=now,
            expires_at=expires_at,
        )
        return LoginResult(principal, raw_session, raw_csrf)
