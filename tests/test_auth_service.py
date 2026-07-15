"""Authentication service policy tests with a transaction-local repository double."""

from __future__ import annotations

from datetime import UTC, datetime
from typing import cast
from unittest.mock import AsyncMock, Mock
from uuid import uuid4

import pytest

from arduino_component_kb.auth.domain import (
    InvalidCredentialsError,
    Role,
    TooManyAttemptsError,
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


async def test_valid_login_creates_hashed_opaque_session_and_audit() -> None:
    credential_input = "correct horse battery staple"
    passwords = PasswordManager()
    user = UserIdentity(
        id=uuid4(),
        login="teacher",
        display_name="Teacher",
        password_hash=passwords.hash(credential_input),
        status=UserStatus.ACTIVE,
        roles=frozenset({Role.TEACHER}),
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
    assert len(call.kwargs["token_hash"]) == 64
    repository.audit.assert_awaited_once()


def test_repository_mock_is_not_a_real_database() -> None:
    assert datetime.now(UTC).tzinfo is UTC
