"""Database-independent smoke test for Argon2id, RBAC, and CSRF policies."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime, timedelta
from uuid import uuid4

from fastapi import HTTPException

from arduino_component_kb.api.dependencies import csrf_principal, require_roles
from arduino_component_kb.auth.domain import Principal, Role
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.service import token_hash


async def smoke() -> None:
    passwords = PasswordManager()
    password_hash = passwords.hash("smoke-test-credential")
    assert password_hash.startswith("$argon2id$")
    assert passwords.verify(password_hash, "smoke-test-credential")

    principal = Principal(
        user_id=uuid4(),
        login="smoke-admin",
        display_name="Smoke Administrator",
        roles=frozenset({Role.ADMINISTRATOR}),
        session_id=uuid4(),
        csrf_hash=token_hash("smoke-csrf"),
        expires_at=datetime.now(UTC) + timedelta(minutes=5),
    )
    assert await require_roles(Role.ADMINISTRATOR)(principal) is principal
    assert await csrf_principal(principal, "smoke-csrf", "smoke-csrf") is principal

    try:
        await require_roles(Role.TEACHER)(principal)
    except HTTPException as error:
        assert error.status_code == 403
    else:
        raise AssertionError("RBAC must deny an ungranted role")


def main() -> int:
    asyncio.run(smoke())
    print("Authentication policy smoke test passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
