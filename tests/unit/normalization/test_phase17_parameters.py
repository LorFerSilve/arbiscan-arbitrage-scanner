"""Phase 17.1 fail-closed guards for structured market parameters."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    Participant,
    ParticipantId,
    ParticipantKind,
    Provider,
    ProviderId,
    ProviderKind,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching import CanonicalRegistry, StaticCanonicalIdHooks
from arbiscan.normalization import (
    NormalizationIssueCode,
    NormalizationResult,
    normalize_source_snapshot,
)
from arbiscan.providers import (
    OddsSnapshot,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)

NOW = datetime(2026, 9, 20, 11, 5, tzinfo=UTC)
EVENT_ID = EventId("event:phase17:arsenal-chelsea")
TOTAL_MARKET_ID = MarketId("market:phase17:totals:2.5")
OVER_ID = SelectionId("selection:phase17:over")
UNDER_ID = SelectionId("selection:phase17:under")
PROVIDER = Provider(
    id=ProviderId("provider:phase17"),
    name="Phase 17 Fixture",
    kind=ProviderKind.SYNTHETIC,
)


def _total_context(
    *,
    source_line: Decimal | None = Decimal("2.5"),
) -> tuple[SourceEvent, OddsSnapshot, CanonicalRegistry, StaticCanonicalIdHooks]:
    competition = Competition(
        id=CompetitionId("competition:phase17:epl"),
        sport=Sport.FOOTBALL,
        name="Premier League",
    )
    arsenal = Participant(
        id=ParticipantId("participant:phase17:arsenal"),
        sport=Sport.FOOTBALL,
        name="Arsenal",
        kind=ParticipantKind.TEAM,
    )
    chelsea = Participant(
        id=ParticipantId("participant:phase17:chelsea"),
        sport=Sport.FOOTBALL,
        name="Chelsea",
        kind=ParticipantKind.TEAM,
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.FOOTBALL,
        competition=competition,
        participants=(arsenal, chelsea),
        scheduled_start=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=TOTAL_MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.REGULATION,
        line=Decimal("2.5"),
    )
    selections = (
        Selection(id=OVER_ID, market_id=TOTAL_MARKET_ID, kind=SelectionKind.OVER),
        Selection(id=UNDER_ID, market_id=TOTAL_MARKET_ID, kind=SelectionKind.UNDER),
    )
    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=(arsenal, chelsea),
        events=(event,),
        markets=(market,),
        selections=selections,
    )

    source_event = SourceEvent(
        external_id="source-event",
        sport=Sport.FOOTBALL,
        competition_external_id="source-competition",
        participants=(
            SourceParticipant(external_id="arsenal", name="Arsenal", role="home"),
            SourceParticipant(external_id="chelsea", name="Chelsea", role="away"),
        ),
        scheduled_start=event.scheduled_start,
        source_status="scheduled",
    )
    source_market = SourceMarket(
        external_event_id=source_event.external_id,
        external_market_id="source-market",
        label="Totals",
        selections=(
            SourceSelectionQuote(
                external_selection_id="over",
                label="Over",
                price="2.10",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="under",
                label="Under",
                price="1.90",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
        ),
        source_timestamp=NOW - timedelta(seconds=5),
        line=source_line,
    )
    snapshot = OddsSnapshot(
        provider_id=PROVIDER.id,
        external_event_id=source_event.external_id,
        markets=(source_market,),
        ingested_at=NOW,
        trace_id="phase17-parameters",
    )
    hooks = StaticCanonicalIdHooks(
        event_ids={source_event.external_id: EVENT_ID},
        market_ids={source_market.external_market_id: TOTAL_MARKET_ID},
        selection_ids={
            (source_market.external_market_id, "over"): OVER_ID,
            (source_market.external_market_id, "under"): UNDER_ID,
        },
    )
    return source_event, snapshot, registry, hooks


def _normalize(
    event: SourceEvent,
    snapshot: OddsSnapshot,
    registry: CanonicalRegistry,
    hooks: StaticCanonicalIdHooks,
) -> NormalizationResult:
    return normalize_source_snapshot(
        provider=PROVIDER,
        hooks=hooks,
        event=event,
        snapshot=snapshot,
        registry=registry,
        as_of=NOW,
        freshness_window=timedelta(minutes=1),
    )


def test_exact_source_line_matches_canonical_total_line() -> None:
    event, snapshot, registry, hooks = _total_context()

    result = _normalize(event, snapshot, registry, hooks)

    assert len(result.quotes) == 2
    assert result.issues == ()


def test_wrong_source_line_is_rejected_before_quote_creation() -> None:
    event, snapshot, registry, hooks = _total_context(source_line=Decimal("3.5"))

    result = _normalize(event, snapshot, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH,
    )


def test_missing_required_source_line_is_rejected_before_quote_creation() -> None:
    event, snapshot, registry, hooks = _total_context(source_line=None)

    result = _normalize(event, snapshot, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH,
    )


def test_unexpected_selection_handicap_is_rejected_fail_closed() -> None:
    event, snapshot, registry, hooks = _total_context()
    market = snapshot.markets[0]
    over = replace(market.selections[0], handicap=Decimal("-0.5"))
    modified_market = replace(market, selections=(over, market.selections[1]))
    modified_snapshot = replace(snapshot, markets=(modified_market,))

    result = _normalize(event, modified_snapshot, registry, hooks)

    assert len(result.quotes) == 1
    assert result.quotes[0].selection_id == UNDER_ID
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.SELECTION_PARAMETER_MISMATCH,
    )


def test_unexpected_period_index_is_rejected_before_quote_creation() -> None:
    event, snapshot, registry, hooks = _total_context()
    modified_market = replace(snapshot.markets[0], period_index=1)
    modified_snapshot = replace(snapshot, markets=(modified_market,))

    result = _normalize(event, modified_snapshot, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH,
    )
