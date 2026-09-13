"""Exact provider-odds conversion into canonical decimal odds."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation

from arbiscan.providers.models import SourceOddsFormat

_ONE = Decimal("1")
_HUNDRED = Decimal("100")


class OddsNormalizationError(ValueError):
    """Raised when a source price cannot be normalized without guessing."""


def _parse_decimal(value: str, *, field_name: str) -> Decimal:
    try:
        parsed = Decimal(value)
    except InvalidOperation as exc:
        raise OddsNormalizationError(f"{field_name} must be numeric") from exc
    if not parsed.is_finite():
        raise OddsNormalizationError(f"{field_name} must be finite")
    return parsed


def normalize_odds(price: str, odds_format: SourceOddsFormat) -> Decimal:
    """Convert a supported source price to exact decimal odds.

    Implied probability input is deliberately interpreted as a probability in the
    open interval ``(0, 1)``. Percentage-looking inputs such as ``40`` are rejected
    instead of being silently interpreted as ``40%``.
    """
    if not isinstance(price, str) or not price.strip():
        raise OddsNormalizationError("price must be non-empty text")
    if not isinstance(odds_format, SourceOddsFormat):
        raise OddsNormalizationError("odds_format must be SourceOddsFormat")

    raw = price.strip()
    decimal_price: Decimal

    if odds_format is SourceOddsFormat.DECIMAL:
        decimal_price = _parse_decimal(raw, field_name="decimal odds")
    elif odds_format is SourceOddsFormat.FRACTIONAL:
        parts = raw.split("/")
        if len(parts) != 2 or any(not part.strip() for part in parts):
            raise OddsNormalizationError("fractional odds must use numerator/denominator")
        numerator = _parse_decimal(parts[0].strip(), field_name="fractional numerator")
        denominator = _parse_decimal(parts[1].strip(), field_name="fractional denominator")
        if numerator <= 0 or denominator <= 0:
            raise OddsNormalizationError("fractional numerator and denominator must be positive")
        decimal_price = _ONE + (numerator / denominator)
    elif odds_format is SourceOddsFormat.AMERICAN:
        american = _parse_decimal(raw, field_name="American odds")
        if american == 0:
            raise OddsNormalizationError("American odds must be non-zero")
        if american > 0:
            decimal_price = _ONE + (american / _HUNDRED)
        else:
            decimal_price = _ONE + (_HUNDRED / abs(american))
    elif odds_format is SourceOddsFormat.IMPLIED_PROBABILITY:
        probability = _parse_decimal(raw, field_name="implied probability")
        if not 0 < probability < _ONE:
            raise OddsNormalizationError("implied probability must be strictly between 0 and 1")
        decimal_price = _ONE / probability
    else:
        raise OddsNormalizationError(f"unsupported odds format: {odds_format!r}")

    if not decimal_price.is_finite() or decimal_price <= _ONE:
        raise OddsNormalizationError("normalized decimal odds must be finite and greater than 1")
    return decimal_price
