"""Phase 16.4 fixture-driven OddsPapi parser and fail-closed regressions."""

from __future__ import annotations

import asyncio
from datetime import UTC, datetime
from decimal import Decimal

from arbiscan.domain import Sport
from arbiscan.providers import ProviderError, ProviderErrorKind
from arbiscan.providers.oddspapi import OddsPapiConfig, OddsPapiProvider
from tests.support.oddspapi import FIXTURE_ROOT, FixtureHttpTransport

NOW = datetime(2026, 9, 17, 10, 30, tzinfo=UTC)
EVENT_ID = "id1000001761301153"


def _provider(transport: FixtureHttpTransport) -> OddsPapiProvider:
    return OddsPapiProvider(
        config=OddsPapiConfig(api_key="fixture-only"),
        transport=transport,
        clock=lambda: NOW,
    )


async def _discover_event(provider: OddsPapiProvider) -> None:
    competitions = await provider.discover_competitions(Sport.FOOTBALL)
    assert tuple(value.external_id for value in competitions) == ("17",)
    events = await provider.discover_events("17")
    assert tuple(value.external_id for value in events) == (EVENT_ID,)


def test_reusable_fixtures_ignore_unsupported_market_family_fail_closed() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport()
        provider = _provider(transport)
        await _discover_event(provider)

        snapshot = await provider.fetch_odds(EVENT_ID)

        assert snapshot is not None
        assert len(snapshot.markets) == 3
        assert {market.selections[0].label for market in snapshot.markets} == {"1", "X", "2"}
        assert all(":104:" not in market.external_market_id for market in snapshot.markets)

    asyncio.run(scenario())


def test_unknown_fixture_status_is_rejected_as_malformed_response() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport(fixture_overrides={"/odds": "odds_unknown_status.json"})
        provider = _provider(transport)
        await _discover_event(provider)

        try:
            await provider.fetch_odds(EVENT_ID)
        except ProviderError as exc:
            assert exc.kind is ProviderErrorKind.MALFORMED_RESPONSE
            assert not exc.retryable
        else:
            raise AssertionError("unknown fixture status must fail closed")

    asyncio.run(scenario())


def test_odds_identity_drift_is_rejected_before_quotes_are_emitted() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport(fixture_overrides={"/odds": "odds_identity_mismatch.json"})
        provider = _provider(transport)
        await _discover_event(provider)

        try:
            await provider.fetch_odds(EVENT_ID)
        except ProviderError as exc:
            assert exc.kind is ProviderErrorKind.MALFORMED_RESPONSE
        else:
            raise AssertionError("odds identity drift must fail closed")

    asyncio.run(scenario())


def test_invalid_json_is_translated_to_shared_malformed_response_error() -> None:
    transport = FixtureHttpTransport(body_overrides={"/sports": b"{"})
    provider = _provider(transport)

    try:
        asyncio.run(provider.supported_sports())
    except ProviderError as exc:
        assert exc.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert not exc.retryable
    else:
        raise AssertionError("invalid JSON must fail through the shared error taxonomy")


def test_fixture_corpus_contains_no_live_credentials_or_captured_account_secret() -> None:
    fixture_text = "\n".join(
        path.read_text(encoding="utf-8")
        for path in sorted(FIXTURE_ROOT.glob("*"))
        if path.is_file()
    )

    assert "fixture-only" not in fixture_text
    assert "api_key" not in fixture_text.casefold()
    assert "authorization" not in fixture_text.casefold()


def test_phase17_2_totals_preserve_catalog_line_and_outcome_identity() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport(
            fixture_overrides={
                "/markets": "markets_phase17_2.json",
                "/odds": "odds_fixture_phase17_2_totals.json",
            }
        )
        provider = _provider(transport)
        await _discover_event(provider)

        snapshot = await provider.fetch_odds(EVENT_ID)

        assert snapshot is not None
        assert len(snapshot.markets) == 4
        assert {market.line for market in snapshot.markets} == {Decimal("2.5")}
        assert {market.selections[0].label for market in snapshot.markets} == {
            "Over",
            "Under",
        }
        assert {
            market.price_provider.id.value
            for market in snapshot.markets
            if market.price_provider is not None
        } == {
            "bookmaker:the-odds-api:pinnacle",
            "bookmaker:the-odds-api:betfair",
        }

    asyncio.run(scenario())


def test_phase17_2_integer_total_is_structurally_preserved_for_later_fail_closed_gate() -> None:
    async def scenario() -> None:
        transport = FixtureHttpTransport(
            fixture_overrides={
                "/markets": "markets_phase17_2.json",
                "/odds": "odds_fixture_phase17_2_integer_total.json",
            }
        )
        provider = _provider(transport)
        await _discover_event(provider)

        snapshot = await provider.fetch_odds(EVENT_ID)

        assert snapshot is not None
        assert len(snapshot.markets) == 2
        assert {market.line for market in snapshot.markets} == {Decimal("3")}

    asyncio.run(scenario())
