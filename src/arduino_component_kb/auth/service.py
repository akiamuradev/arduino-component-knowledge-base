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
    Principal,
    Role,
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
            object_id=principal.session_id,
            request_id=request_id,
            outcome="success",
        )
        return LoginResult(principal, raw_session, raw_csrf)

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
    ) -> UserIdentity:
        normalized = normalize_login(login)
        await self.repository.lock_login(normalized)
        if await self.repository.find_user_by_login(normalized) is not None:
            raise UserAlreadyExistsError
        if not roles:
            roles = frozenset({Role.STUDENT})
        now = datetime.now(UTC)
        user = await self.repository.create_user(
            login=normalized,
            display_name=display_name.strip(),
            password_hash=self.passwords.hash(password),
            roles=roles,
            actor_id=actor.user_id,
            now=now,
        )
        await self.repository.audit(
            now=now,
            actor_user_id=actor.user_id,
            action="identity.user_created",
            object_type="user",
            object_id=user.id,
            request_id=request_id,
            outcome="success",
            details={"roles": sorted(role.value for role in roles)},
        )
        return user

    async def set_roles(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        roles: frozenset[Role],
        request_id: str | None,
    ) -> None:
        user = await self._existing_user(user_id)
        if Role.ADMINISTRATOR in user.roles and Role.ADMINISTRATOR not in roles:
            if await self.repository.count_active_administrators() <= 1:
                raise LastAdministratorError
        now = datetime.now(UTC)
        await self.repository.set_roles(
            user_id, roles or frozenset({Role.STUDENT}), actor.user_id, now
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
            details={"roles": sorted(role.value for role in roles)},
        )

    async def disable_user(
        self,
        *,
        actor: Principal,
        user_id: UUID,
        request_id: str | None,
    ) -> None:
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

    def _throttle_keys(self, login: str, client_identifier: str) -> tuple[str, str]:
        pepper = self.settings.auth_throttle_pepper.get_secret_value().encode()

        def keyed(kind: str, value: str) -> str:
            return hmac.new(pepper, f"{kind}:{value}".encode(), hashlib.sha256).hexdigest()

        return keyed("account", login), keyed("client", client_identifier)
