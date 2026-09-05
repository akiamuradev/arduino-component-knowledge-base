"""PostgreSQL repository for authentication and audit."""

from __future__ import annotations

import re
from datetime import UTC, datetime, timedelta
from typing import Final
from uuid import UUID, uuid4

from sqlalchemy import delete, func, select, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from arduino_component_kb.auth.domain import (
    AuditRecord,
    ManagedUserIdentity,
    Principal,
    Role,
    UserIdentity,
    UserStatus,
)
from arduino_component_kb.auth.models import AuditEvent, AuthSession, AuthThrottle, User, UserRole

_AUDIT_LABEL_PATTERN: Final = re.compile(r"^[a-z][a-z0-9_.]{0,79}$")
_ALLOWED_AUDIT_DETAIL_KEYS: Final = frozenset(
    {
        "bucket",
        "code",
        "component_revision",
        "component_id",
        "decision_id",
        "editor_expires_at",
        "key",
        "kind",
        "objects_deleted",
        "previous_status",
        "reason",
        "reset",
        "review_revision",
        "revision",
        "roles",
        "status",
        "summary",
        "survivor_component_id",
    }
)


def safe_audit_details(details: dict[str, object] | None) -> dict[str, object]:
    """Allow only bounded, explicitly reviewed metadata in durable audit."""
    if details is None:
        return {}
    if not details.keys() <= _ALLOWED_AUDIT_DETAIL_KEYS:
        raise ValueError("audit details contain an unsupported field")
    safe: dict[str, object] = {}
    for key, value in details.items():
        if value is None or isinstance(value, bool | int):
            safe[key] = value
        elif isinstance(value, str) and len(value) <= 200:
            safe[key] = value
        elif (
            isinstance(value, list)
            and len(value) <= 16
            and all(isinstance(item, str) and len(item) <= 80 for item in value)
        ):
            safe[key] = value
        else:
            raise ValueError("audit details contain an unsupported value")
    return safe


class AuthRepository:
    """Execute authentication operations inside a caller-owned transaction."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def find_user_by_login(self, login: str) -> UserIdentity | None:
        user = await self.session.scalar(select(User).where(User.login == login))
        if user is None:
            return None
        roles = await self._roles(user.id, datetime.now(UTC))
        return self._identity(user, roles)

    async def find_user(self, user_id: UUID) -> UserIdentity | None:
        user = await self.session.get(User, user_id)
        if user is None:
            return None
        return self._identity(user, await self._roles(user.id, datetime.now(UTC)))

    async def list_users(self, now: datetime) -> tuple[ManagedUserIdentity, ...]:
        """Return safe account state and current editor lifetime without password data."""
        users = list(await self.session.scalars(select(User).order_by(User.login)))
        managed: list[ManagedUserIdentity] = []
        for user in users:
            editor_expires_at = await self.session.scalar(
                select(UserRole.expires_at)
                .where(
                    UserRole.user_id == user.id,
                    UserRole.role == Role.EDITOR.value,
                    UserRole.revoked_at.is_(None),
                )
                .order_by(UserRole.granted_at.desc())
                .limit(1)
            )
            managed.append(
                ManagedUserIdentity(
                    id=user.id,
                    login=user.login,
                    display_name=user.display_name,
                    status=UserStatus(user.status),
                    roles=await self._roles(user.id, now),
                    editor_expires_at=editor_expires_at,
                )
            )
        return tuple(managed)

    async def lock_login(self, login: str) -> None:
        """Serialize creation of one normalized login in PostgreSQL."""
        await self.session.execute(select(func.pg_advisory_xact_lock(func.hashtext(login))))

    async def lock_administrator_membership(self) -> None:
        """Serialize changes that can remove the final active administrator."""
        await self.session.execute(select(func.pg_advisory_xact_lock(0x41434B42, 0x41444D49)))

    async def is_blocked(self, key_hashes: tuple[str, ...], now: datetime) -> bool:
        result = await self.session.scalar(
            select(func.count())
            .select_from(AuthThrottle)
            .where(
                AuthThrottle.key_hash.in_(key_hashes),
                AuthThrottle.blocked_until.is_not(None),
                AuthThrottle.blocked_until > now,
            )
        )
        return bool(result)

    async def register_failure(
        self,
        key_hashes: tuple[str, ...],
        now: datetime,
        *,
        window_seconds: int,
        failure_limit: int,
        block_seconds: int,
    ) -> None:
        for key_hash in key_hashes:
            await self.session.execute(
                insert(AuthThrottle)
                .values(
                    key_hash=key_hash,
                    failure_count=0,
                    window_started_at=now,
                    updated_at=now,
                )
                .on_conflict_do_nothing(index_elements=[AuthThrottle.key_hash])
            )
            throttle = await self.session.scalar(
                select(AuthThrottle).where(AuthThrottle.key_hash == key_hash).with_for_update()
            )
            window_expired = (
                throttle is None
                or throttle.window_started_at + timedelta(seconds=window_seconds) <= now
            )
            if throttle is None:
                raise RuntimeError("throttle row disappeared inside transaction")
            if window_expired:
                throttle.failure_count = 0
                throttle.window_started_at = now
                throttle.blocked_until = None
            throttle.failure_count += 1
            throttle.updated_at = now
            if throttle.failure_count >= failure_limit:
                throttle.blocked_until = now + timedelta(seconds=block_seconds)

    async def clear_failures(self, key_hashes: tuple[str, ...]) -> None:
        await self.session.execute(
            delete(AuthThrottle).where(AuthThrottle.key_hash.in_(key_hashes))
        )

    async def create_session(
        self,
        user: UserIdentity,
        *,
        token_hash: str,
        csrf_hash: str,
        now: datetime,
        expires_at: datetime,
    ) -> Principal:
        auth_session = AuthSession(
            id=uuid4(),
            user_id=user.id,
            token_hash=token_hash,
            csrf_hash=csrf_hash,
            created_at=now,
            expires_at=expires_at,
            last_seen_at=now,
        )
        self.session.add(auth_session)
        await self.session.flush()
        return Principal(
            user_id=user.id,
            login=user.login,
            display_name=user.display_name,
            roles=user.roles,
            session_id=auth_session.id,
            csrf_hash=csrf_hash,
            expires_at=expires_at,
        )

    async def resolve_session(self, token_hash: str, now: datetime) -> Principal | None:
        row = (
            await self.session.execute(
                select(AuthSession, User)
                .join(User, User.id == AuthSession.user_id)
                .where(
                    AuthSession.token_hash == token_hash,
                    AuthSession.revoked_at.is_(None),
                    AuthSession.expires_at > now,
                    User.status == UserStatus.ACTIVE.value,
                )
            )
        ).one_or_none()
        if row is None:
            return None
        auth_session, user = row._tuple()
        roles = await self._roles(user.id, now)
        if not roles:
            return None
        return Principal(
            user_id=user.id,
            login=user.login,
            display_name=user.display_name,
            roles=roles,
            session_id=auth_session.id,
            csrf_hash=auth_session.csrf_hash,
            expires_at=auth_session.expires_at,
        )

    async def revoke_session(self, session_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.id == session_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def revoke_user_sessions(self, user_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(AuthSession)
            .where(AuthSession.user_id == user_id, AuthSession.revoked_at.is_(None))
            .values(revoked_at=now)
        )

    async def mark_login(self, user_id: UUID, now: datetime, password_hash: str | None) -> None:
        values: dict[str, object] = {"last_login_at": now, "updated_at": now}
        if password_hash is not None:
            values["password_hash"] = password_hash
        await self.session.execute(update(User).where(User.id == user_id).values(**values))

    async def set_password(self, user_id: UUID, password_hash: str, now: datetime) -> None:
        """Replace one credential hash; session revocation remains an explicit service action."""
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(password_hash=password_hash, updated_at=now)
        )

    async def create_user(
        self,
        *,
        login: str,
        display_name: str,
        password_hash: str,
        roles: frozenset[Role],
        actor_id: UUID | None,
        now: datetime,
        editor_expires_at: datetime | None = None,
    ) -> UserIdentity:
        user = User(
            id=uuid4(),
            login=login,
            display_name=display_name,
            password_hash=password_hash,
            status=UserStatus.ACTIVE.value,
            created_at=now,
            updated_at=now,
        )
        self.session.add(user)
        await self.session.flush()
        for role in roles:
            self.session.add(
                UserRole(
                    id=uuid4(),
                    user_id=user.id,
                    role=role.value,
                    granted_by=actor_id,
                    granted_at=now,
                    expires_at=editor_expires_at if role is Role.EDITOR else None,
                )
            )
        await self.session.flush()
        return self._identity(user, roles)

    async def set_roles(
        self,
        user_id: UUID,
        roles: frozenset[Role],
        actor_id: UUID,
        now: datetime,
        editor_expires_at: datetime | None = None,
    ) -> None:
        await self.session.execute(
            update(UserRole)
            .where(UserRole.user_id == user_id, UserRole.revoked_at.is_(None))
            .values(revoked_at=now)
        )
        self.session.add_all(
            [
                UserRole(
                    id=uuid4(),
                    user_id=user_id,
                    role=role.value,
                    granted_by=actor_id,
                    granted_at=now,
                    expires_at=editor_expires_at if role is Role.EDITOR else None,
                )
                for role in roles
            ]
        )

    async def grant_editor(
        self,
        user_id: UUID,
        actor_id: UUID,
        now: datetime,
        expires_at: datetime,
    ) -> None:
        """Replace only the current editor grant and preserve every baseline role."""
        await self.session.execute(
            update(UserRole)
            .where(
                UserRole.user_id == user_id,
                UserRole.role == Role.EDITOR.value,
                UserRole.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )
        self.session.add(
            UserRole(
                id=uuid4(),
                user_id=user_id,
                role=Role.EDITOR.value,
                granted_by=actor_id,
                granted_at=now,
                expires_at=expires_at,
            )
        )

    async def revoke_editor(self, user_id: UUID, now: datetime) -> None:
        """Revoke only the editor grant while retaining its history."""
        await self.session.execute(
            update(UserRole)
            .where(
                UserRole.user_id == user_id,
                UserRole.role == Role.EDITOR.value,
                UserRole.revoked_at.is_(None),
            )
            .values(revoked_at=now)
        )

    async def disable_user(self, user_id: UUID, now: datetime) -> None:
        await self.session.execute(
            update(User)
            .where(User.id == user_id)
            .values(status=UserStatus.DISABLED.value, updated_at=now)
        )
        await self.revoke_user_sessions(user_id, now)

    async def count_active_administrators(self) -> int:
        administrators = await self.session.scalars(
            select(User.id)
            .select_from(User)
            .join(UserRole, UserRole.user_id == User.id)
            .where(
                UserRole.role == Role.ADMINISTRATOR.value,
                UserRole.revoked_at.is_(None),
                User.status == UserStatus.ACTIVE.value,
            )
            .with_for_update(of=User)
        )
        return len(list(administrators))

    async def list_audit_events(
        self,
        *,
        actor_user_id: UUID | None,
        action: str | None,
        occurred_from: datetime | None,
        occurred_to: datetime | None,
        limit: int,
        offset: int,
    ) -> tuple[tuple[AuditRecord, ...], int]:
        """Read a bounded reverse-chronological audit page with exact filters."""
        filters = []
        if actor_user_id is not None:
            filters.append(AuditEvent.actor_user_id == actor_user_id)
        if action is not None:
            filters.append(AuditEvent.action == action)
        if occurred_from is not None:
            filters.append(AuditEvent.occurred_at >= occurred_from)
        if occurred_to is not None:
            filters.append(AuditEvent.occurred_at < occurred_to)
        rows = (
            await self.session.execute(
                select(AuditEvent, User.login, User.display_name)
                .outerjoin(User, User.id == AuditEvent.actor_user_id)
                .where(*filters)
                .order_by(AuditEvent.occurred_at.desc(), AuditEvent.id.desc())
                .limit(limit)
                .offset(offset)
            )
        ).all()
        total = int(
            await self.session.scalar(select(func.count()).select_from(AuditEvent).where(*filters))
            or 0
        )
        return (
            tuple(
                AuditRecord(
                    id=event.id,
                    occurred_at=event.occurred_at,
                    actor_user_id=event.actor_user_id,
                    actor_type=event.actor_type,
                    actor_login=login,
                    actor_display_name=display_name,
                    action=event.action,
                    object_type=event.object_type,
                    object_id=event.object_id,
                    outcome=event.outcome,
                )
                for event, login, display_name in rows
            ),
            total,
        )

    async def list_audit_actions(self) -> tuple[str, ...]:
        """Return stable action identifiers for the authorized filter."""
        actions = await self.session.scalars(
            select(AuditEvent.action).distinct().order_by(AuditEvent.action)
        )
        return tuple(actions)

    async def audit(
        self,
        *,
        now: datetime,
        actor_user_id: UUID | None,
        action: str,
        object_type: str,
        object_id: UUID | None,
        request_id: str | None,
        outcome: str,
        details: dict[str, object] | None = None,
        actor_type: str | None = None,
    ) -> None:
        resolved_actor_type = actor_type or ("user" if actor_user_id else "anonymous")
        for label in (action, object_type, resolved_actor_type, outcome):
            if not _AUDIT_LABEL_PATTERN.fullmatch(label):
                raise ValueError("audit label is invalid")
        self.session.add(
            AuditEvent(
                id=uuid4(),
                occurred_at=now,
                actor_user_id=actor_user_id,
                actor_type=resolved_actor_type,
                action=action,
                object_type=object_type,
                object_id=object_id,
                request_id=request_id,
                outcome=outcome,
                details_safe_json=safe_audit_details(details),
            )
        )

    async def _roles(self, user_id: UUID, now: datetime) -> frozenset[Role]:
        values = await self.session.scalars(
            select(UserRole.role).where(
                UserRole.user_id == user_id,
                UserRole.revoked_at.is_(None),
                (UserRole.expires_at.is_(None) | (UserRole.expires_at > now)),
            )
        )
        return frozenset(Role(value) for value in values)

    @staticmethod
    def _identity(user: User, roles: frozenset[Role]) -> UserIdentity:
        return UserIdentity(
            id=user.id,
            login=user.login,
            display_name=user.display_name,
            password_hash=user.password_hash,
            status=UserStatus(user.status),
            roles=roles,
        )
