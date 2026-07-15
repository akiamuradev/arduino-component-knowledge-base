"""One-time interactive bootstrap for the first local administrator."""

from __future__ import annotations

import argparse
import asyncio
import getpass
from datetime import UTC, datetime

from arduino_component_kb.auth.domain import Role, normalize_login
from arduino_component_kb.auth.passwords import PasswordManager
from arduino_component_kb.auth.repository import AuthRepository
from arduino_component_kb.config import Settings
from arduino_component_kb.db import Database


async def bootstrap(login: str, display_name: str, credential: str, settings: Settings) -> None:
    """Create the first administrator only when none exists."""
    cleaned_display_name = display_name.strip()
    if not cleaned_display_name:
        raise ValueError("display name must not be blank")
    database = Database(settings)
    try:
        async with database.sessions() as session, session.begin():
            repository = AuthRepository(session)
            await repository.lock_login("__initial_administrator_bootstrap__")
            if await repository.count_active_administrators() != 0:
                raise RuntimeError("an active administrator already exists")
            normalized = normalize_login(login)
            await repository.lock_login(normalized)
            if await repository.find_user_by_login(normalized) is not None:
                raise RuntimeError("the requested login already exists")
            now = datetime.now(UTC)
            user = await repository.create_user(
                login=normalized,
                display_name=cleaned_display_name,
                password_hash=PasswordManager().hash(credential),
                roles=frozenset({Role.ADMINISTRATOR}),
                actor_id=None,
                now=now,
            )
            await repository.audit(
                now=now,
                actor_user_id=None,
                action="identity.initial_administrator_created",
                object_type="user",
                object_id=user.id,
                request_id=None,
                outcome="success",
            )
    finally:
        await database.dispose()


def main() -> int:
    """Read the credential from a TTY so it never appears in shell history."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--login", required=True)
    parser.add_argument("--display-name", required=True)
    args = parser.parse_args()
    first = getpass.getpass("Administrator password: ")
    second = getpass.getpass("Repeat password: ")
    if first != second:
        parser.error("passwords do not match")
    asyncio.run(bootstrap(args.login, args.display_name, first, Settings()))
    print("Initial administrator created.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
