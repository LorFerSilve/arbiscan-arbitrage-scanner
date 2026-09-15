"""Deterministic text-key normalization used by explicit alias catalogs."""

from __future__ import annotations

import unicodedata


def normalize_alias_key(value: str, *, field_name: str = "alias") -> str:
    """Return a conservative canonical key for explicit alias lookup.

    The function deliberately does not remove accents, punctuation, club suffixes,
    gender markers, age categories, or other semantic text. Those transformations
    can collapse distinct sporting entities and therefore belong in explicit alias
    data rather than in a generic normalizer.
    """
    if not isinstance(value, str):
        raise ValueError(f"{field_name} must be text")
    if len(value) > 512:
        raise ValueError(f"{field_name} exceeds maximum length 512")

    normalized = unicodedata.normalize("NFKC", value).casefold()
    normalized = " ".join(normalized.split())
    if not normalized:
        raise ValueError(f"{field_name} must not be empty")
    if any(ord(char) < 32 for char in normalized):
        raise ValueError(f"{field_name} contains control characters")
    return normalized


def normalize_optional_alias_key(
    value: str | None,
    *,
    field_name: str,
) -> str | None:
    """Normalize an optional explicit alias context value."""
    if value is None:
        return None
    return normalize_alias_key(value, field_name=field_name)
