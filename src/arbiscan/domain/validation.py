"""Reusable validation helpers for canonical domain objects."""

from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain.errors import DomainValidationError


def normalize_text(value: str, *, field: str, max_length: int = 256) -> str:
    """Trim and validate a non-empty textual value."""
    if not isinstance(value, str):
        raise DomainValidationError(f"{field} must be a string")
    normalized = value.strip()
    if not normalized:
        raise DomainValidationError(f"{field} must not be empty")
    if len(normalized) > max_length:
        raise DomainValidationError(f"{field} exceeds maximum length {max_length}")
    if any(ord(char) < 32 and char not in "\t" for char in normalized):
        raise DomainValidationError(f"{field} contains control characters")
    return normalized


def normalize_optional_text(
    value: str | None,
    *,
    field: str,
    max_length: int = 256,
) -> str | None:
    """Validate optional textual data."""
    if value is None:
        return None
    return normalize_text(value, field=field, max_length=max_length)


def normalize_datetime(value: datetime, *, field: str) -> datetime:
    """Require an aware timestamp and normalize it to UTC."""
    if not isinstance(value, datetime):
        raise DomainValidationError(f"{field} must be a datetime")
    if value.tzinfo is None or value.utcoffset() is None:
        raise DomainValidationError(f"{field} must be timezone-aware")
    return value.astimezone(UTC)


def normalize_optional_datetime(value: datetime | None, *, field: str) -> datetime | None:
    """Validate and normalize an optional timestamp."""
    if value is None:
        return None
    return normalize_datetime(value, field=field)


def require_decimal(value: Decimal, *, field: str) -> Decimal:
    """Require an exact finite Decimal value."""
    if not isinstance(value, Decimal):
        raise DomainValidationError(f"{field} must be Decimal, not {type(value).__name__}")
    if not value.is_finite():
        raise DomainValidationError(f"{field} must be finite")
    return value


def require_positive_decimal(value: Decimal, *, field: str) -> Decimal:
    """Require a strictly positive finite Decimal."""
    value = require_decimal(value, field=field)
    if value <= 0:
        raise DomainValidationError(f"{field} must be greater than zero")
    return value


def normalize_currency(value: str) -> str:
    """Validate an ISO-4217-style three-letter currency code."""
    normalized = normalize_text(value, field="currency", max_length=3).upper()
    if len(normalized) != 3 or not normalized.isascii() or not normalized.isalpha():
        raise DomainValidationError("currency must be a three-letter ASCII code")
    return normalized
