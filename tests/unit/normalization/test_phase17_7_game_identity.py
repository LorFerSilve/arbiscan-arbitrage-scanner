"""Phase 17.7 fail-closed regressions for nested tennis game identity."""

from __future__ import annotations

from dataclasses import replace
from datetime import UTC, datetime, timedelta

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
from arbiscan.normalization import NormalizationIssueCode, normalize_source_snapshot
from arbiscan.providers import (
    OddsSnapshot,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)

NOW = datetime(2026, 9, 18, 11, 20, tzinfo=UTC)
PROVIDER = Provider(
    id=ProviderId("provider:phase17-7"),
    name="Phase 17.7 Fixture",
    kind=ProviderKind.SYNTHETIC,
)
EVENT_ID = EventId("event:phase17-7:sinner-alcaraz")
MARKET_ID = MarketId("market:phase17-7:set1:game3:winner")
SINNER_ID = ParticipantId("participant:phase17-7:sinner")
ALCARAZ_ID = ParticipantId("participant:phase17-7:alcaraz")
SINNER_SELECTION_ID = SelectionId("selection:phase17-7:sinner")
ALCARAZ_SELECTION_ID = SelectionId("selection:phase17-7:alcaraz")


def _context() -> tuple[
    SourceEvent,
    OddsSnapshot,
    CanonicalRegistry,
    StaticCanonicalIdHooks,
]:
    competition = Competition(
        id=CompetitionId("competition:phase17-7:us-open"),
        sport=Sport.TENNIS,
        name="US Open",
    )
    sinner = Participant(
        id=SINNER_ID,
        sport=Sport.TENNIS,
        name="Jannik Sinner",
        kind=ParticipantKind.INDIVIDUAL,
    )
    alcaraz = Participant(
        id=ALCARAZ_ID,
        sport=Sport.TENNIS,
        name="Carlos Alcaraz",
        kind=ParticipantKind.INDIVIDUAL,
    )
    event = Event(
        id=EVENT_ID,
        sport=Sport.TENNIS,
        competition=competition,
        participants=(sinner, alcaraz),
        scheduled_start=datetime(2026, 9, 18, 15, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )
    market = Market(
        id=MARKET_ID,
        event_id=EVENT_ID,
        kind=MarketKind.GAME_WINNER,
        period=MarketPeriod.GAME,
        period_index=3,
        set_index=1,
    )
    selections = (
        Selection(
            id=SINNER_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=SINNER_ID,
        ),
        Selection(
            id=ALCARAZ_SELECTION_ID,
            market_id=MARKET_ID,
            kind=SelectionKind.PARTICIPANT,
            participant_id=ALCARAZ_ID,
        ),
    )
    registry = CanonicalRegistry(
        competitions=(competition,),
        participants=(sinner, alcaraz),
        events=(event,),
        markets=(market,),
        selections=selections,
    )

    source_event = SourceEvent(
        external_id="source-event",
        sport=Sport.TENNIS,
        competition_external_id="source-competition",
        participants=(
            SourceParticipant(external_id="sinner", name="Jannik Sinner"),
            SourceParticipant(external_id="alcaraz", name="Carlos Alcaraz"),
        ),
        scheduled_start=event.scheduled_start,
        source_status="scheduled",
    )
    source_market = SourceMarket(
        external_event_id=source_event.external_id,
        external_market_id="source-game-market",
        label="Structured Game Winner",
        selections=(
            SourceSelectionQuote(
                external_selection_id="sinner",
                label="Jannik Sinner",
                price="2.05",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="alcaraz",
                label="Carlos Alcaraz",
                price="1.90",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
        ),
        source_timestamp=NOW - timedelta(seconds=5),
        period_index=3,
        set_index=1,
    )
    snapshot = OddsSnapshot(
        provider_id=PROVIDER.id,
        external_event_id=source_event.external_id,
        markets=(source_market,),
        ingested_at=NOW,
        trace_id="phase17-7-game-identity",
    )
    hooks = StaticCanonicalIdHooks(
        event_ids={source_event.external_id: EVENT_ID},
        market_ids={source_market.external_market_id: MARKET_ID},
        selection_ids={
            (source_market.external_market_id, "sinner"): SINNER_SELECTION_ID,
            (source_market.external_market_id, "alcaraz"): ALCARAZ_SELECTION_ID,
        },
    )
    return source_event, snapshot, registry, hooks


def _normalize(
    event: SourceEvent,
    snapshot: OddsSnapshot,
    registry: CanonicalRegistry,
    hooks: StaticCanonicalIdHooks,
):
    return normalize_source_snapshot(
        provider=PROVIDER,
        hooks=hooks,
        event=event,
        snapshot=snapshot,
        registry=registry,
        as_of=NOW,
        freshness_window=timedelta(minutes=1),
    )


def test_exact_nested_game_identity_still_fails_closed_at_support_gate() -> None:
    event, snapshot, registry, hooks = _context()

    result = _normalize(event, snapshot, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.UNSUPPORTED_MARKET_VARIANT,
    )


def test_wrong_source_set_index_fails_before_market_support_gate() -> None:
    event, snapshot, registry, hooks = _context()
    source_market = replace(snapshot.markets[0], set_index=2)
    modified = replace(snapshot, markets=(source_market,))

    result = _normalize(event, modified, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH,
    )
    assert "source set_index=2" in result.issues[0].detail
    assert "canonical set_index=1" in result.issues[0].detail


def test_wrong_source_game_index_fails_before_market_support_gate() -> None:
    event, snapshot, registry, hooks = _context()
    source_market = replace(snapshot.markets[0], period_index=4)
    modified = replace(snapshot, markets=(source_market,))

    result = _normalize(event, modified, registry, hooks)

    assert result.quotes == ()
    assert tuple(issue.code for issue in result.issues) == (
        NormalizationIssueCode.MARKET_PARAMETER_MISMATCH,
    )
    assert "source period_index=4" in result.issues[0].detail
    assert "canonical period_index=3" in result.issues[0].detail
