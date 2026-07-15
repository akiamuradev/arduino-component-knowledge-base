"""Argon2id password policy tests."""

from __future__ import annotations

import pytest

from arduino_component_kb.auth.domain import PasswordPolicyError
from arduino_component_kb.auth.passwords import PasswordManager


def test_passwords_use_argon2id_and_verify() -> None:
    manager = PasswordManager()
    value = "correct horse battery staple"
    encoded = manager.hash(value)
    assert encoded.startswith("$argon2id$")
    assert manager.verify(encoded, value) is True
    assert manager.verify(encoded, "incorrect value") is False


@pytest.mark.parametrize("value", ["short", "x" * 129])
def test_password_policy_is_bounded(value: str) -> None:
    with pytest.raises(PasswordPolicyError):
        PasswordManager().hash(value)


def test_unknown_user_path_performs_a_real_hash_verification() -> None:
    manager = PasswordManager()
    assert manager.verify(None, "untrusted input") is False


def test_malformed_stored_hash_is_an_invalid_credential_not_an_exception() -> None:
    assert not PasswordManager().verify("not-an-argon2-hash", "untrusted credential input")
