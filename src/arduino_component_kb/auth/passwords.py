"""Argon2id password hashing with bounded inputs and timing equalization."""

from __future__ import annotations

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerificationError

from arduino_component_kb.auth.domain import PasswordPolicyError


class PasswordManager:
    """Hash and verify passwords using an explicit Argon2id policy."""

    def __init__(self) -> None:
        self._hasher = PasswordHasher(
            time_cost=3,
            memory_cost=65_536,
            parallelism=4,
            hash_len=32,
            salt_len=16,
            type=Type.ID,
        )
        self._dummy_hash: str | None = None

    @staticmethod
    def validate(password: str) -> None:
        """Bound CPU input and require a minimally useful passphrase."""
        if not 12 <= len(password) <= 128:
            raise PasswordPolicyError("password must contain 12 to 128 characters")

    def hash(self, password: str) -> str:
        """Validate and hash one password."""
        self.validate(password)
        return self._hasher.hash(password)

    def verify(self, encoded_hash: str | None, password: str) -> bool:
        """Verify a real or timing-only hash without propagating malformed PHC data."""
        candidate_hash = encoded_hash or self._timing_hash()
        try:
            return self._hasher.verify(candidate_hash, password)
        except (InvalidHashError, VerificationError):
            return False

    def needs_rehash(self, encoded_hash: str) -> bool:
        """Report whether a successful login should upgrade its Argon2 parameters."""
        return self._hasher.check_needs_rehash(encoded_hash)

    def _timing_hash(self) -> str:
        if self._dummy_hash is None:
            self._dummy_hash = self._hasher.hash("timing-only-placeholder-value")
        return self._dummy_hash
