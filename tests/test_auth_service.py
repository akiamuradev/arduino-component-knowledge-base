"""Authentication service policy tests with a transaction-local repository double."""

from __future__ import annotations

from datetime import UTC, datetime, timedelta
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from arduino_component_kb.auth.domain import (
    AuthenticationRequiredError,
    InvalidCredentialsError,
    LastAdministratorError,
    Principal,
    Role,
    RoleGrantPolicyError,
    TooManyAttemptsError,
    UserAlreadyExistsError,
    UserIdentity,
    UserStatus,
)
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.auth.service import AuthService
from arduino_component_kb.config import Settings


def settings() -> Settings:
    return Settings(
        _env_file=None,
        environment="test",
        database_url="postgresql+asyncpg://ackb:placeholder@localhost/ackb",
        auth_failure_limit=3,
    )


def repository_mock() -> Mock:
    return Mock(spec=AuthRepository)


async def test_blocked_login_is_audited_and_never_checks_credentials() -> None:
    credential_input = "untrusted input"
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=True)
    repository.audit = AsyncMock()
    repository.find_user_by_login = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())
    with pytest.raises(TooManyAttemptsError):
        await service.login(
            login="student",
            password=credential_input,
            client_identifier="127.0.0.1",
            request_id="request-1",
        )
    repository.find_user_by_login.assert_not_awaited()
    repository.audit.assert_awaited_once()


async def test_invalid_credentials_increment_both_persistent_throttles() -> None:
    credential_input = "untrusted input"
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=False)
    repository.find_user_by_login = AsyncMock(return_value=None)
    repository.register_failure = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())
    with pytest.raises(InvalidCredentialsError):
        await service.login(
            login="missing",
            password=credential_input,
            client_identifier="127.0.0.1",
            request_id="request-2",
        )
    call = repository.register_failure.await_args
    assert call is not None
    key_hashes = call.args[0]
    assert len(key_hashes) == 2
    assert all(len(value) == 64 for value in key_hashes)
    assert "missing" not in "".join(key_hashes)


async def test_malformed_login_uses_a_non_user_sentinel() -> None:
    credential_input = "untrusted input"
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=False)
    repository.find_user_by_login = AsyncMock(return_value=None)
    repository.register_failure = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(InvalidCredentialsError):
        await service.login(
            login="not a valid login",
            password=credential_input,
            client_identifier="127.0.0.1",
            request_id="request-invalid-login",
        )

    repository.find_user_by_login.assert_awaited_once_with("\x00invalid-login")


@pytest.mark.parametrize("role", list(Role))
async def test_valid_login_uses_only_repository_roles_for_every_role(role: Role) -> None:
    credential_input = "correct horse battery staple"
    passwords = PasswordManager()
    user = UserIdentity(
        id=uuid4(),
        login=role.value,
        display_name=role.value,
        password_hash=passwords.hash(credential_input),
        status=UserStatus.ACTIVE,
        roles=frozenset({role}),
    )
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=False)
    repository.find_user_by_login = AsyncMock(return_value=user)
    repository.clear_failures = AsyncMock()
    repository.create_session = AsyncMock()
    repository.mark_login = AsyncMock()
    repository.audit = AsyncMock()

    async def create_session(*_: object, **kwargs: object) -> object:
        from arduino_component_kb.auth.domain import Principal

        return Principal(
            user_id=user.id,
            login=user.login,
            display_name=user.display_name,
            roles=user.roles,
            session_id=uuid4(),
            csrf_hash=str(kwargs["csrf_hash"]),
            expires_at=cast(datetime, kwargs["expires_at"]),
        )

    repository.create_session.side_effect = create_session
    service = AuthService(repository, settings(), passwords)
    result = await service.login(
        login="Teacher",
        password=credential_input,
        client_identifier="127.0.0.1",
        request_id="request-3",
    )
    call = repository.create_session.await_args
    assert call is not None
    assert result.session_token not in str(call)
    assert result.csrf_token not in str(call)
    assert result.principal.roles == frozenset({role})
    assert len(call.kwargs["token_hash"]) == 64
    repository.audit.assert_awaited_once()


async def test_forged_session_cookie_cannot_supply_roles() -> None:
    repository = repository_mock()
    repository.resolve_session = AsyncMock(return_value=None)
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(AuthenticationRequiredError):
        await service.authenticate("administrator:forged-session")

    call = repository.resolve_session.await_args
    assert call is not None
    assert call.args[0] != "administrator:forged-session"


def test_repository_mock_is_not_a_real_database() -> None:
    assert datetime.now(UTC).tzinfo is UTC


def administrator_identity() -> UserIdentity:
    return UserIdentity(
        id=uuid4(),
        login="administrator",
        display_name="Administrator",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.ADMINISTRATOR}),
    )


def administrator_principal(user: UserIdentity) -> Principal:
    return Principal(
        user_id=user.id,
        login=user.login,
        display_name=user.display_name,
        roles=user.roles,
        session_id=uuid4(),
        csrf_hash="not-used",
        expires_at=datetime.now(UTC),
    )


async def test_public_registration_creates_only_student_and_starts_session() -> None:
    passwords = PasswordManager()
    credential_input = "safe-student-password"
    user = UserIdentity(
        id=uuid4(),
        login="new-student",
        display_name="new-student",
        password_hash=passwords.hash(credential_input),
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT}),
    )
    principal = Principal(
        user_id=user.id,
        login=user.login,
        display_name=user.display_name,
        roles=user.roles,
        session_id=uuid4(),
        csrf_hash="stored-csrf",
        expires_at=datetime.now(UTC) + timedelta(hours=1),
    )
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=False)
    repository.register_failure = AsyncMock()
    repository.lock_login = AsyncMock()
    repository.find_user_by_login = AsyncMock(return_value=None)
    repository.create_user = AsyncMock(return_value=user)
    repository.create_session = AsyncMock(return_value=principal)
    repository.mark_login = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), passwords)

    result = await service.register(
        login=" New-Student ",
        password=credential_input,
        client_identifier="127.0.0.1",
        request_id="request-register",
    )

    create_call = repository.create_user.await_args
    assert create_call is not None
    assert create_call.kwargs["login"] == "new-student"
    assert create_call.kwargs["display_name"] == "new-student"
    assert create_call.kwargs["roles"] == frozenset({Role.STUDENT})
    assert create_call.kwargs["actor_id"] is None
    assert result.principal.roles == frozenset({Role.STUDENT})
    repository.create_session.assert_awaited_once()
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.self_registered"
    assert audit_call.kwargs["details"] == {"roles": ["student"]}
    assert "password" not in str(audit_call)


async def test_public_registration_rejects_duplicate_login() -> None:
    existing = administrator_identity()
    credential_input = "safe-student-password"
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=False)
    repository.register_failure = AsyncMock()
    repository.lock_login = AsyncMock()
    repository.find_user_by_login = AsyncMock(return_value=existing)
    repository.create_user = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(UserAlreadyExistsError):
        await service.register(
            login=existing.login,
            password=credential_input,
            client_identifier="127.0.0.1",
            request_id="request-duplicate",
        )

    repository.create_user.assert_not_awaited()


async def test_public_registration_reuses_persistent_client_throttling() -> None:
    credential_input = "safe-student-password"
    repository = repository_mock()
    repository.is_blocked = AsyncMock(return_value=True)
    repository.register_failure = AsyncMock()
    repository.create_user = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(TooManyAttemptsError):
        await service.register(
            login="new-student",
            password=credential_input,
            client_identifier="127.0.0.1",
            request_id="request-register-throttled",
        )

    checked_keys = repository.is_blocked.await_args.args[0]
    assert len(checked_keys) == 1
    assert len(checked_keys[0]) == 64
    repository.register_failure.assert_not_awaited()
    repository.create_user.assert_not_awaited()
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["outcome"] == "blocked"


async def test_administrator_creation_assigns_role_only_on_server() -> None:
    actor = administrator_identity()
    created = UserIdentity(
        id=uuid4(),
        login="second-admin",
        display_name="second-admin",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.ADMINISTRATOR}),
    )
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.lock_login = AsyncMock()
    repository.find_user_by_login = AsyncMock(return_value=None)
    repository.create_user = AsyncMock(return_value=created)
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())
    credential_input = "safe-admin-password"

    result = await service.create_administrator(
        actor=administrator_principal(actor),
        login="Second-Admin",
        password=credential_input,
        request_id="request-create-admin",
    )

    create_call = repository.create_user.await_args
    assert create_call is not None
    assert create_call.kwargs["roles"] == frozenset({Role.ADMINISTRATOR})
    assert create_call.kwargs["display_name"] == "second-admin"
    assert result.roles == frozenset({Role.ADMINISTRATOR})
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.administrator_created"


async def test_administrator_password_reset_hashes_password_and_revokes_sessions() -> None:
    actor = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="student",
        display_name="student",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT}),
    )
    repository = repository_mock()
    repository.find_user = AsyncMock(return_value=target)
    repository.set_password = AsyncMock()
    repository.revoke_user_sessions = AsyncMock()
    repository.audit = AsyncMock()
    passwords = PasswordManager()
    service = AuthService(repository, settings(), passwords)
    credential_input = "replacement-password"

    await service.reset_password(
        actor=administrator_principal(actor),
        user_id=target.id,
        password=credential_input,
        request_id="request-password-reset",
    )

    password_call = repository.set_password.await_args
    assert password_call is not None
    stored_hash = password_call.args[1]
    assert stored_hash != credential_input
    assert passwords.verify(stored_hash, credential_input)
    repository.revoke_user_sessions.assert_awaited_once_with(target.id, password_call.args[2])
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.password_reset"
    assert "details" not in audit_call.kwargs
    assert credential_input not in str(audit_call)


async def test_removing_last_administrator_is_checked_under_global_lock() -> None:
    user = administrator_identity()
    call_order: list[str] = []

    def lock_administrators() -> None:
        call_order.append("lock")

    def find_user(_: object) -> UserIdentity:
        call_order.append("find")
        return user

    def count_administrators() -> int:
        call_order.append("count")
        return 1

    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock(side_effect=lock_administrators)
    repository.find_user = AsyncMock(side_effect=find_user)
    repository.count_active_administrators = AsyncMock(side_effect=count_administrators)
    repository.set_roles = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(LastAdministratorError):
        await service.set_roles(
            actor=administrator_principal(user),
            user_id=user.id,
            roles=frozenset({Role.TEACHER}),
            request_id="request-role-change",
        )

    assert call_order == ["lock", "find", "count"]
    repository.set_roles.assert_not_awaited()


async def test_disabling_last_administrator_is_checked_under_global_lock() -> None:
    user = administrator_identity()
    call_order: list[str] = []

    def lock_administrators() -> None:
        call_order.append("lock")

    def find_user(_: object) -> UserIdentity:
        call_order.append("find")
        return user

    def count_administrators() -> int:
        call_order.append("count")
        return 1

    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock(side_effect=lock_administrators)
    repository.find_user = AsyncMock(side_effect=find_user)
    repository.count_active_administrators = AsyncMock(side_effect=count_administrators)
    repository.disable_user = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(LastAdministratorError):
        await service.disable_user(
            actor=administrator_principal(user),
            user_id=user.id,
            request_id="request-disable-user",
        )

    assert call_order == ["lock", "find", "count"]
    repository.disable_user.assert_not_awaited()


@pytest.mark.parametrize(
    "editor_expires_at",
    [None, datetime(2020, 1, 1, tzinfo=UTC)],
)
async def test_editor_role_requires_a_future_expiration(
    editor_expires_at: datetime | None,
) -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT}),
    )
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.set_roles = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(RoleGrantPolicyError):
        await service.set_roles(
            actor=administrator_principal(administrator),
            user_id=target.id,
            roles=frozenset({Role.EDITOR}),
            request_id="request-editor-grant",
            editor_expires_at=editor_expires_at,
        )

    repository.set_roles.assert_not_awaited()


async def test_editor_role_requires_a_non_temporary_baseline_role() -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT}),
    )
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.set_roles = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(RoleGrantPolicyError):
        await service.set_roles(
            actor=administrator_principal(administrator),
            user_id=target.id,
            roles=frozenset({Role.EDITOR}),
            request_id="request-editor-without-baseline",
            editor_expires_at=datetime.now(UTC) + timedelta(days=7),
        )

    repository.set_roles.assert_not_awaited()


async def test_future_editor_role_is_persisted_and_sessions_are_revoked() -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT}),
    )
    expiry = datetime.now(UTC) + timedelta(days=7)
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.set_roles = AsyncMock()
    repository.revoke_user_sessions = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    await service.set_roles(
        actor=administrator_principal(administrator),
        user_id=target.id,
        roles=frozenset({Role.STUDENT, Role.EDITOR}),
        request_id="request-editor-grant",
        editor_expires_at=expiry,
    )

    call = repository.set_roles.await_args
    assert call is not None
    assert call.kwargs["editor_expires_at"] == expiry
    repository.revoke_user_sessions.assert_awaited_once()
    repository.audit.assert_awaited_once()


async def test_dedicated_editor_grant_preserves_baseline_and_records_audit() -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.TEACHER}),
    )
    expiry = datetime.now(UTC) + timedelta(days=14)
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.grant_editor = AsyncMock()
    repository.revoke_user_sessions = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    await service.grant_editor(
        actor=administrator_principal(administrator),
        user_id=target.id,
        expires_at=expiry,
        request_id="request-dedicated-editor-grant",
    )

    repository.grant_editor.assert_awaited_once()
    grant_call = repository.grant_editor.await_args
    assert grant_call is not None
    assert grant_call.args[0] == target.id
    assert grant_call.args[3] == expiry
    repository.revoke_user_sessions.assert_awaited_once_with(target.id, grant_call.args[2])
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.editor_granted"
    assert audit_call.kwargs["details"] == {"editor_expires_at": expiry.isoformat()}


async def test_dedicated_editor_renewal_records_expiry_change() -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.TEACHER, Role.EDITOR}),
    )
    expiry = datetime.now(UTC) + timedelta(days=21)
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.grant_editor = AsyncMock()
    repository.revoke_user_sessions = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    await service.grant_editor(
        actor=administrator_principal(administrator),
        user_id=target.id,
        expires_at=expiry,
        request_id="request-editor-renewal",
    )

    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.editor_expiry_changed"
    assert audit_call.kwargs["details"] == {"editor_expires_at": expiry.isoformat()}


async def test_dedicated_editor_grant_cannot_change_an_administrator() -> None:
    administrator = administrator_identity()
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=administrator)
    repository.grant_editor = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    with pytest.raises(RoleGrantPolicyError):
        await service.grant_editor(
            actor=administrator_principal(administrator),
            user_id=administrator.id,
            expires_at=datetime.now(UTC) + timedelta(days=7),
            request_id="request-admin-editor-grant",
        )

    repository.grant_editor.assert_not_awaited()


async def test_dedicated_editor_revoke_preserves_history_and_records_audit() -> None:
    administrator = administrator_identity()
    target = UserIdentity(
        id=uuid4(),
        login="target",
        display_name="Target",
        password_hash=uuid4().hex,
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.STUDENT, Role.EDITOR}),
    )
    repository = repository_mock()
    repository.lock_administrator_membership = AsyncMock()
    repository.find_user = AsyncMock(return_value=target)
    repository.revoke_editor = AsyncMock()
    repository.revoke_user_sessions = AsyncMock()
    repository.audit = AsyncMock()
    service = AuthService(repository, settings(), PasswordManager())

    await service.revoke_editor(
        actor=administrator_principal(administrator),
        user_id=target.id,
        request_id="request-editor-revoke",
    )

    repository.revoke_editor.assert_awaited_once()
    repository.revoke_user_sessions.assert_awaited_once()
    audit_call = repository.audit.await_args
    assert audit_call is not None
    assert audit_call.kwargs["action"] == "identity.editor_revoked"
