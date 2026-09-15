"""Tests for exact odds-format normalization."""

from decimal import Decimal

from arbiscan.normalization import OddsNormalizationError, normalize_odds
from arbiscan.providers.models import SourceOddsFormat


def _assert_invalid(price: str, odds_format: SourceOddsFormat) -> None:
    try:
        normalize_odds(price, odds_format)
    except OddsNormalizationError:
        return
    raise AssertionError("expected OddsNormalizationError")


def test_equivalent_formats_produce_identical_decimal_odds() -> None:
    expected = Decimal("2.5")
    assert normalize_odds("2.5", SourceOddsFormat.DECIMAL) == expected
    assert normalize_odds("3/2", SourceOddsFormat.FRACTIONAL) == expected
    assert normalize_odds("+150", SourceOddsFormat.AMERICAN) == expected
    assert normalize_odds("0.4", SourceOddsFormat.IMPLIED_PROBABILITY) == expected


def test_negative_american_odds_are_exact() -> None:
    assert normalize_odds("-200", SourceOddsFormat.AMERICAN) == Decimal("1.5")


def test_fractional_odds_require_positive_parts() -> None:
    _assert_invalid("0/1", SourceOddsFormat.FRACTIONAL)
    _assert_invalid("1/0", SourceOddsFormat.FRACTIONAL)
    _assert_invalid("3", SourceOddsFormat.FRACTIONAL)


def test_implied_probability_does_not_guess_percentage_units() -> None:
    _assert_invalid("40", SourceOddsFormat.IMPLIED_PROBABILITY)
    _assert_invalid("0", SourceOddsFormat.IMPLIED_PROBABILITY)
    _assert_invalid("1", SourceOddsFormat.IMPLIED_PROBABILITY)


def test_non_finite_or_non_profitable_prices_are_rejected() -> None:
    _assert_invalid("NaN", SourceOddsFormat.DECIMAL)
    _assert_invalid("Infinity", SourceOddsFormat.DECIMAL)
    _assert_invalid("1", SourceOddsFormat.DECIMAL)
