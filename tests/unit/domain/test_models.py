"""Unit tests for canonical domain entities and invariants."""

from __future__ import annotations

from dataclasses import FrozenInstanceError
from datetime import UTC, datetime, timedelta, timezone
from decimal import Decimal
from typing import Callable

from arbiscan.domain import (
    Competition,
    CompetitionId,
    DomainValidationError,
    Event,
    EventId,
    EventStatus,
    Market,
    MarketId,
    MarketKind,
    MarketPeriod,
    OddsQuote,
    Opportunity,
    OpportunityId,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderEventReference,
    ProviderId,
    ProviderMarketReference,
    QuoteId,
    QuoteStatus,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
    StakeAllocation,
    StakePlan,
    StakePlanId,
)


def expect_validation_error(action: Callable[[], object]) -> None:
    """Assert that an action violates a canonical domain invariant."""
    try:
        action()
    except DomainValidationError:
        return
    raise AssertionError("expected DomainValidationError")


def football_competition() -> Competition:
    return Competition(
        id=CompetitionId("competition:premier-league:2026"),
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )


def team(identifier: str, name: str) -> Participant:
    return Participant(
        id=ParticipantId(identifier),
        sport=Sport.FOOTBALL,
        name=name,
        kind=ParticipantKind.TEAM,
    )


def test_identifiers_are_opaque_and_type_sensitive() -> None:
    event_id = EventId("shared-value")
    market_id = MarketId("shared-value")

    assert str(event_id) == "shared-value"
    assert event_id != market_id
    assert EventId(" shared-value ") == event_id
    expect_validation_error(lambda: EventId("   "))


def test_event_normalizes_time_to_utc_and_is_immutable() -> None:
    brussels = timezone(timedelta(hours=2))
    event = Event(
        id=EventId("event:arsenal-chelsea:2026-09-13"),
        sport=Sport.FOOTBALL,
        competition=football_competition(),
        participants=(
            team("participant:arsenal", "Arsenal"),
            team("participant:chelsea", "Chelsea"),
        ),
        scheduled_start=datetime(2026, 9, 13, 20, 45, tzinfo=brussels),
        status=EventStatus.SCHEDULED,
        provider_references=(
            ProviderEventReference(ProviderId("provider:a"), "source-event-10"),
            ProviderEventReference(ProviderId("provider:b"), "event-900"),
        ),
    )

    assert event.scheduled_start == datetime(2026, 9, 13, 18, 45, tzinfo=UTC)
    try:
        event.status = EventStatus.LIVE  # type: ignore[misc]
    except FrozenInstanceError:
        pass
    else:
        raise AssertionError("canonical entities must be immutable")


def test_event_supports_non_team_multi_participant_sports() -> None:
    competition = Competition(
        id=CompetitionId("competition:f1:belgium:2027"),
        sport=Sport.MOTORSPORT,
        name="Belgian Grand Prix",
    )
    participants = tuple(
        Participant(
            id=ParticipantId(f"driver:{index}"),
            sport=Sport.MOTORSPORT,
            name=f"Driver {index}",
            kind=ParticipantKind.DRIVER,
        )
        for index in range(1, 21)
    )

    event = Event(
        id=EventId("event:f1:belgium:2027"),
        sport=Sport.MOTORSPORT,
        competition=competition,
        participants=participants,
        scheduled_start=datetime(2027, 7, 25, 13, 0, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
    )

    assert len(event.participants) == 20


def test_event_rejects_sport_mismatch_duplicate_participants_and_naive_time() -> None:
    competition = football_competition()
    arsenal = team("participant:arsenal", "Arsenal")

    expect_validation_error(
        lambda: Event(
            id=EventId("event:bad-time"),
            sport=Sport.FOOTBALL,
            competition=competition,
            participants=(arsenal,),
            scheduled_start=datetime(2026, 9, 13, 20, 45),
            status=EventStatus.SCHEDULED,
        )
    )
    expect_validation_error(
        lambda: Event(
            id=EventId("event:duplicate"),
            sport=Sport.FOOTBALL,
            competition=competition,
            participants=(arsenal, arsenal),
            scheduled_start=datetime(2026, 9, 13, 18, 45, tzinfo=UTC),
            status=EventStatus.SCHEDULED,
        )
    )

    tennis_player = Participant(
        id=ParticipantId("participant:tennis-player"),
        sport=Sport.TENNIS,
        name="Player",
        kind=ParticipantKind.INDIVIDUAL,
    )
    expect_validation_error(
        lambda: Event(
            id=EventId("event:sport-mismatch"),
            sport=Sport.FOOTBALL,
            competition=competition,
            participants=(tennis_player,),
            scheduled_start=datetime(2026, 9, 13, 18, 45, tzinfo=UTC),
            status=EventStatus.SCHEDULED,
        )
    )


def test_market_semantics_require_explicit_parameters() -> None:
    event_id = EventId("event:1")

    total = Market(
        id=MarketId("market:total:2.5"),
        event_id=event_id,
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.REGULATION,
        line=Decimal("2.5"),
    )
    assert total.line == Decimal("2.5")

    expect_validation_error(
        lambda: Market(
            id=MarketId("market:missing-line"),
            event_id=event_id,
            kind=MarketKind.TOTAL_POINTS,
        )
    )
    expect_validation_error(
        lambda: Market(
            id=MarketId("market:unexpected-line"),
            event_id=event_id,
            kind=MarketKind.MATCH_WINNER_3_WAY,
            line=Decimal("2.5"),
        )
    )
    expect_validation_error(
        lambda: Market(
            id=MarketId("market:set-without-index"),
            event_id=event_id,
            kind=MarketKind.SET_WINNER,
            period=MarketPeriod.SET,
        )
    )


def test_provider_market_references_are_unique_per_provider() -> None:
    provider_id = ProviderId("provider:a")
    expect_validation_error(
        lambda: Market(
            id=MarketId("market:duplicate-provider"),
            event_id=EventId("event:1"),
            kind=MarketKind.MATCH_WINNER_2_WAY,
            provider_references=(
                ProviderMarketReference(provider_id, "event-a", "market-a"),
                ProviderMarketReference(provider_id, "event-a", "market-b"),
            ),
        )
    )


def test_selection_encodes_semantics_instead_of_provider_labels() -> None:
    market_id = MarketId("market:1x2")
    arsenal_id = ParticipantId("participant:arsenal")
    participant = Selection(
        id=SelectionId("selection:arsenal"),
        market_id=market_id,
        kind=SelectionKind.PARTICIPANT,
        participant_id=arsenal_id,
    )
    draw = Selection(
        id=SelectionId("selection:draw"),
        market_id=market_id,
        kind=SelectionKind.DRAW,
    )

    assert participant.participant_id == arsenal_id
    assert draw.participant_id is None
    expect_validation_error(
        lambda: Selection(
            id=SelectionId("selection:invalid"),
            market_id=market_id,
            kind=SelectionKind.DRAW,
            participant_id=arsenal_id,
        )
    )


def test_quote_preserves_decimal_precision_and_complete_provenance() -> None:
    source_timezone = timezone(timedelta(hours=-4))
    quote = OddsQuote(
        id=QuoteId("quote:1"),
        provider_id=ProviderId("provider:a"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        selection_id=SelectionId("selection:1"),
        decimal_price=Decimal("2.375000000000000001"),
        source_event_id=" ext-event ",
        source_market_id="ext-market",
        source_selection_id="ext-selection",
        source_timestamp=datetime(2026, 9, 13, 14, 0, tzinfo=source_timezone),
        ingested_at=datetime(2026, 9, 13, 18, 0, 1, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        trace_id="trace-1",
        raw_source_reference="fixture://provider-a/event-1",
    )

    assert quote.decimal_price == Decimal("2.375000000000000001")
    assert quote.source_event_id == "ext-event"
    assert quote.source_timestamp == datetime(2026, 9, 13, 18, 0, tzinfo=UTC)

    expect_validation_error(
        lambda: OddsQuote(
            id=QuoteId("quote:float"),
            provider_id=ProviderId("provider:a"),
            event_id=EventId("event:1"),
            market_id=MarketId("market:1"),
            selection_id=SelectionId("selection:1"),
            decimal_price=2.5,  # type: ignore[arg-type]
            source_event_id="event",
            source_market_id="market",
            source_selection_id="selection",
            ingested_at=datetime.now(UTC),
            status=QuoteStatus.ACTIVE,
        )
    )
    expect_validation_error(
        lambda: OddsQuote(
            id=QuoteId("quote:bad-odds"),
            provider_id=ProviderId("provider:a"),
            event_id=EventId("event:1"),
            market_id=MarketId("market:1"),
            selection_id=SelectionId("selection:1"),
            decimal_price=Decimal("1"),
            source_event_id="event",
            source_market_id="market",
            source_selection_id="selection",
            ingested_at=datetime.now(UTC),
            status=QuoteStatus.ACTIVE,
        )
    )


def test_opportunity_and_stake_plan_encode_only_canonical_references() -> None:
    opportunity = Opportunity(
        id=OpportunityId("opportunity:1"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        quote_ids=(QuoteId("quote:a"), QuoteId("quote:b")),
        implied_probability_sum=Decimal("0.98"),
        theoretical_profit_margin=Decimal("0.020408163265306122"),
        detected_at=datetime(2026, 9, 13, 18, 1, tzinfo=UTC),
    )

    allocations = (
        StakeAllocation(
            quote_id=QuoteId("quote:a"),
            selection_id=SelectionId("selection:a"),
            provider_id=ProviderId("provider:a"),
            amount=Decimal("49.00"),
            expected_payout=Decimal("102.00"),
        ),
        StakeAllocation(
            quote_id=QuoteId("quote:b"),
            selection_id=SelectionId("selection:b"),
            provider_id=ProviderId("provider:b"),
            amount=Decimal("51.00"),
            expected_payout=Decimal("102.10"),
        ),
    )
    plan = StakePlan(
        id=StakePlanId("stake-plan:1"),
        opportunity_id=opportunity.id,
        currency="eur",
        bankroll=Decimal("100"),
        allocations=allocations,
        guaranteed_payout=Decimal("102.00"),
        guaranteed_profit=Decimal("2.00"),
        created_at=datetime(2026, 9, 13, 18, 1, 1, tzinfo=UTC),
    )

    assert plan.currency == "EUR"
    assert sum((allocation.amount for allocation in plan.allocations), Decimal("0")) == Decimal(
        "100.00"
    )

    expect_validation_error(
        lambda: Opportunity(
            id=OpportunityId("opportunity:not-arbitrage"),
            event_id=EventId("event:1"),
            market_id=MarketId("market:1"),
            quote_ids=(QuoteId("quote:a"), QuoteId("quote:b")),
            implied_probability_sum=Decimal("1.00"),
            theoretical_profit_margin=Decimal("0.01"),
            detected_at=datetime.now(UTC),
        )
    )
