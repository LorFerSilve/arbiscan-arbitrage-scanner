"""Unit tests for the first real odds-data provider adapter."""

from __future__ import annotations

import asyncio
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import ProviderId, Sport
from arbiscan.observability.provider import InMemoryProviderTelemetry, ProviderTelemetryOutcome
from arbiscan.providers import ProviderError, ProviderErrorKind, ProviderHealthState
from arbiscan.providers.http import HttpResponse
from arbiscan.providers.the_odds_api import TheOddsApiConfig, TheOddsApiProvider
from tests.support.the_odds_api import FixtureHttpTransport

NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)
FIXTURE_KEY = "fixture"


def _build(
    *,
    transport: FixtureHttpTransport | None = None,
) -> tuple[TheOddsApiProvider, FixtureHttpTransport, InMemoryProviderTelemetry]:
    fixture_transport = transport or FixtureHttpTransport()
    telemetry = InMemoryProviderTelemetry()
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY),
        transport=fixture_transport,
        telemetry=telemetry,
        clock=lambda: NOW,
    )
    return provider, fixture_transport, telemetry


def test_config_repr_hides_credential() -> None:
    config = TheOddsApiConfig(api_key=FIXTURE_KEY)

    assert FIXTURE_KEY not in repr(config)


def test_discovery_maps_only_supported_canonical_sports() -> None:
    provider, _transport, _telemetry = _build()

    sports = asyncio.run(provider.supported_sports())
    football = asyncio.run(provider.discover_competitions(Sport.FOOTBALL))
    tennis = asyncio.run(provider.discover_competitions(Sport.TENNIS))

    assert sports == (Sport.BASKETBALL, Sport.FOOTBALL, Sport.TENNIS)
    assert tuple(value.external_id for value in football) == ("soccer_epl",)
    assert tuple(value.external_id for value in tennis) == ("tennis_atp_us_open",)


def test_event_and_odds_preserve_bookmaker_origin_and_freshness() -> None:
    provider, transport, telemetry = _build()

    events = asyncio.run(provider.discover_events("soccer_epl"))
    assert len(events) == 1
    event = events[0]
    assert event.external_id == "epl-arsenal-chelsea-20260920"
    assert tuple(value.name for value in event.participants) == ("Arsenal", "Chelsea")

    snapshot = asyncio.run(provider.fetch_odds(event.external_id))
    assert snapshot is not None
    assert snapshot.provider_id == ProviderId("provider:the-odds-api")
    assert len(snapshot.markets) == 2
    assert {
        market.price_provider.id for market in snapshot.markets if market.price_provider is not None
    } == {
        ProviderId("bookmaker:the-odds-api:pinnacle"),
        ProviderId("bookmaker:the-odds-api:unibet_eu"),
    }
    assert {market.source_timestamp for market in snapshot.markets} == {
        datetime(2026, 9, 20, 11, 4, tzinfo=UTC),
        datetime(2026, 9, 20, 11, 4, 30, tzinfo=UTC),
    }

    rate_limit = asyncio.run(provider.rate_limit())
    assert rate_limit is not None
    assert rate_limit.limit == 500
    assert rate_limit.remaining == 487

    request = transport.requests[-1]
    assert request.query["apiKey"] == FIXTURE_KEY
    assert request.query["regions"] == "eu"
    assert request.query["markets"] == "h2h"
    assert request.query["oddsFormat"] == "decimal"
    assert FIXTURE_KEY not in repr(telemetry.events)
    assert telemetry.events[-1].outcome is ProviderTelemetryOutcome.SUCCESS
    assert telemetry.events[-1].request_cost == 1


def test_rate_limit_response_becomes_retryable_structured_error() -> None:
    provider, _transport, telemetry = _build(
        transport=FixtureHttpTransport(status_code=429, retry_after="7")
    )

    try:
        asyncio.run(provider.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.RATE_LIMITED
        assert error.retryable
        assert error.retry_after == timedelta(seconds=7)
        assert FIXTURE_KEY not in str(error)
    else:
        raise AssertionError("expected rate-limit ProviderError")

    rate_limit = asyncio.run(provider.rate_limit())
    assert rate_limit is not None
    assert rate_limit.retry_after == timedelta(seconds=7)
    assert telemetry.events[-1].outcome is ProviderTelemetryOutcome.FAILURE
    assert telemetry.events[-1].error_kind == ProviderErrorKind.RATE_LIMITED.value


def test_health_degrades_without_leaking_credential() -> None:
    provider, _transport, _telemetry = _build(transport=FixtureHttpTransport(status_code=401))

    health = asyncio.run(provider.health())

    assert health.state is ProviderHealthState.UNAVAILABLE
    assert health.detail is not None
    assert "authentication" in health.detail
    assert FIXTURE_KEY not in health.detail


def test_malformed_payload_fails_closed() -> None:
    class MalformedTransport:
        async def get(
            self,
            *,
            url: str,
            query: Mapping[str, str],
            timeout_seconds: float,
        ) -> HttpResponse:
            _ = (url, query, timeout_seconds)
            return HttpResponse(status_code=200, headers={}, body=b'{"unexpected":true}')

    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY),
        transport=MalformedTransport(),
        clock=lambda: NOW,
    )

    try:
        asyncio.run(provider.supported_sports())
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert not error.retryable
    else:
        raise AssertionError("expected malformed-response ProviderError")


def test_configured_advanced_markets_preserve_structured_point_parameters() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={"odds": "odds_event_phase17_1_parameters.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(
            api_key=FIXTURE_KEY,
            markets=("totals", "spreads"),
        ),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))
    assert snapshot is not None

    totals = next(market for market in snapshot.markets if market.label.endswith(" totals"))
    spread = next(market for market in snapshot.markets if market.label.endswith(" spreads"))

    assert totals.line == Decimal("2.5")
    assert totals.period_index is None
    assert {selection.handicap for selection in totals.selections} == {None}

    assert spread.line == Decimal("-1.5")
    assert {selection.handicap for selection in spread.selections} == {
        Decimal("-1.5"),
        Decimal("1.5"),
    }
    assert transport.requests[-1].query["markets"] == "totals,spreads"


def test_inconsistent_totals_points_fail_closed_at_adapter_boundary() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={"odds": "odds_event_phase17_1_bad_totals.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("totals",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "must share one point" in str(error)
    else:
        raise AssertionError("inconsistent totals points must fail closed")


def test_totals_require_exact_over_under_outcome_pair() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={"odds": "odds_event_phase17_2_bad_total_outcomes.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("totals",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "exactly one Over and one Under" in str(error)
    else:
        raise AssertionError("invalid totals outcomes must fail closed")


def test_spreads_require_exact_opposite_home_away_points() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={"odds": "odds_event_phase17_3_bad_spread_points.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("spreads",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "exact opposites" in str(error)
    else:
        raise AssertionError("non-opposite spread points must fail closed")


def test_spreads_require_exact_event_participant_labels() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={"odds": "odds_event_phase17_3_bad_spread_participants.json"}
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("spreads",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "home and away participants" in str(error)
    else:
        raise AssertionError("spread participant drift must fail closed")


def test_phase17_4_btts_preserves_exact_yes_no_semantics() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_4_btts.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("btts",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert snapshot is not None
    assert len(snapshot.markets) == 2
    assert {market.line for market in snapshot.markets} == {None}
    assert all(
        {selection.label for selection in market.selections} == {"Yes", "No"}
        for market in snapshot.markets
    )
    assert all(
        {selection.handicap for selection in market.selections} == {None}
        for market in snapshot.markets
    )
    assert transport.requests[-1].query["markets"] == "btts"


def test_phase17_4_btts_requires_exact_yes_no_outcome_pair() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_4_bad_btts_outcomes.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("btts",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "exactly one Yes and one No" in str(error)
    else:
        raise AssertionError("invalid BTTS outcomes must fail closed")


def test_phase17_4_btts_rejects_unexpected_point_semantics() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_4_bad_btts_point.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("btts",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "must not carry point" in str(error)
    else:
        raise AssertionError("BTTS point parameters must fail closed")


def test_phase17_5_draw_no_bet_maps_to_handicap_zero_semantics() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_5_dnb.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("draw_no_bet",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert snapshot is not None
    assert len(snapshot.markets) == 2
    assert {market.line for market in snapshot.markets} == {Decimal("0")}
    assert all(
        {selection.label for selection in market.selections}
        == {"Liverpool FC", "Manchester United"}
        for market in snapshot.markets
    )
    assert all(
        {selection.handicap for selection in market.selections} == {Decimal("0")}
        for market in snapshot.markets
    )
    assert transport.requests[-1].query["markets"] == "draw_no_bet"


def test_phase17_5_draw_no_bet_requires_exact_event_participants() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_5_bad_dnb_participants.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("draw_no_bet",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "home and away participants" in str(error)
    else:
        raise AssertionError("Draw No Bet participant drift must fail closed")


def test_phase17_5_draw_no_bet_rejects_unexpected_point_semantics() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_soccer_epl_phase16_5.json",
            "odds": "odds_event_phase17_5_bad_dnb_point.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("draw_no_bet",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("soccer_epl"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "must not carry point" in str(error)
    else:
        raise AssertionError("Draw No Bet point parameters must fail closed")


def test_phase17_8_tennis_set_moneylines_preserve_structured_set_index() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_tennis_atp_us_open_phase16_5.json",
            "odds": "odds_event_phase17_8_tennis_sets.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(
            api_key=FIXTURE_KEY,
            markets=("h2h_s1", "h2h_s2"),
        ),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("tennis_atp_us_open"))[0]
    snapshot = asyncio.run(provider.fetch_odds(event.external_id))

    assert snapshot is not None
    assert len(snapshot.markets) == 4
    assert {market.period_index for market in snapshot.markets} == {1, 2}
    assert {market.line for market in snapshot.markets} == {None}
    assert all(
        {selection.label for selection in market.selections} == {"Jannik Sinner", "Carlos Alcaraz"}
        for market in snapshot.markets
    )
    assert all(
        {selection.handicap for selection in market.selections} == {None}
        for market in snapshot.markets
    )
    by_key = {market.label.rsplit(" ", 1)[1]: market.period_index for market in snapshot.markets}
    assert by_key == {"h2h_s1": 1, "h2h_s2": 2}
    assert transport.requests[-1].query["markets"] == "h2h_s1,h2h_s2"


def test_phase17_8_tennis_set_moneyline_requires_exact_event_participants() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_tennis_atp_us_open_phase16_5.json",
            "odds": "odds_event_phase17_8_bad_set_participants.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("h2h_s1",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("tennis_atp_us_open"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "home and away participants" in str(error)
    else:
        raise AssertionError("tennis set participant drift must fail closed")


def test_phase17_8_tennis_set_moneyline_rejects_unexpected_point_semantics() -> None:
    transport = FixtureHttpTransport(
        fixture_overrides={
            "events": "events_tennis_atp_us_open_phase16_5.json",
            "odds": "odds_event_phase17_8_bad_set_point.json",
        }
    )
    provider = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=FIXTURE_KEY, markets=("h2h_s2",)),
        transport=transport,
        clock=lambda: NOW,
    )

    event = asyncio.run(provider.discover_events("tennis_atp_us_open"))[0]
    try:
        asyncio.run(provider.fetch_odds(event.external_id))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "must not carry point" in str(error)
    else:
        raise AssertionError("tennis set point parameters must fail closed")
