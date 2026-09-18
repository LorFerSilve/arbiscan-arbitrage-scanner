"""Tests for exact market semantic normalization."""

from decimal import Decimal

from arbiscan.domain import MarketKind, MarketPeriod, ProviderId, Sport
from arbiscan.normalization import MarketAlias, MarketNormalizer, ResolutionStatus


def _normalizer() -> MarketNormalizer:
    the_odds_api = ProviderId("provider:the-odds-api")
    return MarketNormalizer(
        (
            MarketAlias(
                "Full Time Result",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
            ),
            MarketAlias(
                "1X2",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
            ),
            MarketAlias(
                "First Half Result",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.FIRST_HALF,
            ),
            MarketAlias(
                "To Qualify",
                Sport.FOOTBALL,
                MarketKind.QUALIFICATION_WINNER,
                MarketPeriod.FULL_EVENT,
            ),
            MarketAlias(
                "Match Winner",
                Sport.TENNIS,
                MarketKind.MATCH_WINNER_2_WAY,
                MarketPeriod.FULL_EVENT,
            ),
            MarketAlias(
                "Totals",
                Sport.FOOTBALL,
                MarketKind.TOTAL_POINTS,
                MarketPeriod.REGULATION,
                requires_line=True,
            ),
            MarketAlias(
                "Handicap",
                Sport.FOOTBALL,
                MarketKind.HANDICAP,
                MarketPeriod.REGULATION,
                requires_line=True,
            ),
            MarketAlias(
                "Set Winner",
                Sport.TENNIS,
                MarketKind.SET_WINNER,
                MarketPeriod.SET,
                requires_period_index=True,
            ),
            MarketAlias(
                "Game Winner",
                Sport.TENNIS,
                MarketKind.GAME_WINNER,
                MarketPeriod.GAME,
                requires_period_index=True,
                requires_set_index=True,
            ),
            MarketAlias(
                "h2h",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
                provider_id=the_odds_api,
            ),
            MarketAlias(
                "Winner",
                Sport.FOOTBALL,
                MarketKind.MATCH_WINNER_3_WAY,
                MarketPeriod.REGULATION,
            ),
            MarketAlias(
                "Winner",
                Sport.FOOTBALL,
                MarketKind.QUALIFICATION_WINNER,
                MarketPeriod.FULL_EVENT,
            ),
        )
    )


def test_regulation_and_qualification_winner_are_not_equivalent() -> None:
    normalizer = _normalizer()
    result = normalizer.resolve("Full Time Result", sport=Sport.FOOTBALL)
    qualify = normalizer.resolve("To Qualify", sport=Sport.FOOTBALL)

    assert result.value is not None
    assert result.value.kind is MarketKind.MATCH_WINNER_3_WAY
    assert result.value.period is MarketPeriod.REGULATION
    assert qualify.value is not None
    assert qualify.value.kind is MarketKind.QUALIFICATION_WINNER
    assert qualify.value.period is MarketPeriod.FULL_EVENT
    assert result.value != qualify.value


def test_first_half_is_not_collapsed_into_full_time() -> None:
    semantic = _normalizer().resolve("First Half Result", sport=Sport.FOOTBALL).value
    assert semantic is not None
    assert semantic.period is MarketPeriod.FIRST_HALF


def test_total_lines_are_part_of_canonical_semantics() -> None:
    normalizer = _normalizer()
    total_25 = normalizer.resolve("Totals", sport=Sport.FOOTBALL, line="2.5").value
    total_35 = normalizer.resolve("Totals", sport=Sport.FOOTBALL, line=Decimal("3.5")).value

    assert total_25 is not None and total_35 is not None
    assert total_25.line == Decimal("2.5")
    assert total_35.line == Decimal("3.5")
    assert total_25 != total_35


def test_handicap_lines_are_not_rounded_or_collapsed() -> None:
    normalizer = _normalizer()
    minus_one = normalizer.resolve("Handicap", sport=Sport.FOOTBALL, line="-1.0").value
    minus_one_half = normalizer.resolve("Handicap", sport=Sport.FOOTBALL, line="-1.5").value

    assert minus_one is not None and minus_one_half is not None
    assert minus_one.line == Decimal("-1.0")
    assert minus_one_half.line == Decimal("-1.5")
    assert minus_one != minus_one_half


def test_parameterized_and_indexed_markets_require_structured_context() -> None:
    normalizer = _normalizer()
    assert normalizer.resolve("Totals", sport=Sport.FOOTBALL).status is ResolutionStatus.UNKNOWN
    assert normalizer.resolve("Set Winner", sport=Sport.TENNIS).status is ResolutionStatus.UNKNOWN

    set_one = normalizer.resolve("Set Winner", sport=Sport.TENNIS, period_index=1).value
    assert set_one is not None
    assert set_one.period is MarketPeriod.SET
    assert set_one.period_index == 1

    assert (
        normalizer.resolve(
            "Game Winner",
            sport=Sport.TENNIS,
            period_index=3,
        ).status
        is ResolutionStatus.UNKNOWN
    )
    game = normalizer.resolve(
        "Game Winner",
        sport=Sport.TENNIS,
        period_index=3,
        set_index=2,
    ).value
    assert game is not None
    assert game.kind is MarketKind.GAME_WINNER
    assert game.period is MarketPeriod.GAME
    assert game.period_index == 3
    assert game.set_index == 2


def test_provider_specific_market_alias_needs_provider_context() -> None:
    normalizer = _normalizer()
    provider = ProviderId("provider:the-odds-api")
    assert normalizer.resolve("h2h", sport=Sport.FOOTBALL).status is ResolutionStatus.UNKNOWN
    resolved = normalizer.resolve("h2h", sport=Sport.FOOTBALL, provider_id=provider)
    assert resolved.value is not None
    assert resolved.value.kind is MarketKind.MATCH_WINNER_3_WAY


def test_semantically_ambiguous_market_alias_fails_closed() -> None:
    result = _normalizer().resolve("Winner", sport=Sport.FOOTBALL)
    assert result.status is ResolutionStatus.AMBIGUOUS
    assert len(result.candidates) == 2


def test_unknown_market_alias_is_not_guessed() -> None:
    assert (
        _normalizer().resolve("Result-ish", sport=Sport.FOOTBALL).status is ResolutionStatus.UNKNOWN
    )
