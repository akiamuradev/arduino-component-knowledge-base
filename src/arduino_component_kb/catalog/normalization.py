"""Stable exact-match normalization shared by manual and imported catalog data."""

from __future__ import annotations

import unicodedata


def normalize_exact_identity(value: str | None) -> str | None:
    """Return a compact Unicode identity key or None for missing input."""
    if value is None:
        return None
    normalized = unicodedata.normalize("NFKC", value).casefold()
    result = "".join(character for character in normalized if character.isalnum())
    return result or None
