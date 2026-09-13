"""Round-trip tests for the versioned canonical domain serializer."""

from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime
from decimal import Decimal

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
    Provider,
    ProviderEventReference,
    ProviderId,
    ProviderKind,
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
    dumps,
    loads,
)


def expect_validation_error(action: Callable[[], object]) -> None:
    try:
        action()
    except DomainValidationError:
        return
    raise AssertionError("expected DomainValidationError")


def build_event() -> Event:
    competition = Competition(
        id=CompetitionId("competition:atp:antwerp:2026"),
        sport=Sport.TENNIS,
        name="European Open",
        region="Belgium",
        season="2026",
    )
    participants = (
        Participant(
            id=ParticipantId("participant:player-a"),
            sport=Sport.TENNIS,
            name="Player A",
            kind=ParticipantKind.INDIVIDUAL,
        ),
        Participant(
            id=ParticipantId("participant:player-b"),
            sport=Sport.TENNIS,
            name="Player B",
            kind=ParticipantKind.INDIVIDUAL,
        ),
    )
    return Event(
        id=EventId("event:atp-antwerp:a-b"),
        sport=Sport.TENNIS,
        competition=competition,
        participants=participants,
        scheduled_start=datetime(2026, 10, 20, 12, 30, tzinfo=UTC),
        status=EventStatus.SCHEDULED,
        provider_references=(
            ProviderEventReference(ProviderId("provider:a"), "tennis-100"),
            ProviderEventReference(ProviderId("provider:b"), "evt-b-200"),
        ),
    )


def test_event_round_trip_preserves_nested_types() -> None:
    event = build_event()

    restored = loads(dumps(event), Event)

    assert restored == event
    assert isinstance(restored.id, EventId)
    assert isinstance(restored.competition.id, CompetitionId)
    assert isinstance(restored.participants[0].id, ParticipantId)
    assert restored.scheduled_start.tzinfo is UTC


def test_provider_round_trip_preserves_provider_semantics() -> None:
    provider = Provider(
        id=ProviderId("provider:aggregator-a"),
        name="Aggregator A",
        kind=ProviderKind.AGGREGATOR,
    )

    assert loads(dumps(provider), Provider) == provider


def test_market_selection_and_quote_round_trip_preserve_decimal_precision() -> None:
    market = Market(
        id=MarketId("market:total-games:22.5"),
        event_id=EventId("event:atp-antwerp:a-b"),
        kind=MarketKind.TOTAL_POINTS,
        period=MarketPeriod.FULL_EVENT,
        line=Decimal("22.500000000000000001"),
        provider_references=(
            ProviderMarketReference(
                ProviderId("provider:a"),
                "tennis-100",
                "total-games-22.5",
            ),
        ),
    )
    selection = Selection(
        id=SelectionId("selection:over"),
        market_id=market.id,
        kind=SelectionKind.OVER,
    )
    quote = OddsQuote(
        id=QuoteId("quote:over:a"),
        provider_id=ProviderId("provider:a"),
        event_id=market.event_id,
        market_id=market.id,
        selection_id=selection.id,
        decimal_price=Decimal("1.950000000000000003"),
        source_event_id="tennis-100",
        source_market_id="total-games-22.5",
        source_selection_id="over",
        source_timestamp=datetime(2026, 10, 20, 11, 0, 0, tzinfo=UTC),
        ingested_at=datetime(2026, 10, 20, 11, 0, 1, tzinfo=UTC),
        status=QuoteStatus.ACTIVE,
        raw_source_reference="fixture://provider-a/tennis-100",
    )

    assert loads(dumps(market), Market) == market
    assert loads(dumps(selection), Selection) == selection
    restored_quote = loads(dumps(quote), OddsQuote)
    assert restored_quote == quote
    assert restored_quote.decimal_price.as_tuple() == quote.decimal_price.as_tuple()


def test_opportunity_and_stake_plan_round_trip() -> None:
    opportunity = Opportunity(
        id=OpportunityId("opportunity:serialized"),
        event_id=EventId("event:1"),
        market_id=MarketId("market:1"),
        quote_ids=(QuoteId("quote:a"), QuoteId("quote:b")),
        implied_probability_sum=Decimal("0.975"),
        theoretical_profit_margin=Decimal("0.025641025641025641"),
        detected_at=datetime(2026, 9, 13, 18, 0, tzinfo=UTC),
    )
    plan = StakePlan(
        id=StakePlanId("stake-plan:serialized"),
        opportunity_id=opportunity.id,
        currency="EUR",
        bankroll=Decimal("200"),
        allocations=(
            StakeAllocation(
                quote_id=QuoteId("quote:a"),
                selection_id=SelectionId("selection:a"),
                provider_id=ProviderId("provider:a"),
                amount=Decimal("95"),
                expected_payout=Decimal("205"),
            ),
            StakeAllocation(
                quote_id=QuoteId("quote:b"),
                selection_id=SelectionId("selection:b"),
                provider_id=ProviderId("provider:b"),
                amount=Decimal("105"),
                expected_payout=Decimal("205.20"),
            ),
        ),
        guaranteed_payout=Decimal("205"),
        guaranteed_profit=Decimal("5"),
        created_at=datetime(2026, 9, 13, 18, 0, 1, tzinfo=UTC),
    )

    assert loads(dumps(opportunity), Opportunity) == opportunity
    assert loads(dumps(plan), StakePlan) == plan


def test_serialization_is_deterministic() -> None:
    event = build_event()
    assert dumps(event) == dumps(event)


def test_decoder_rejects_unknown_types_versions_and_root_type_mismatch() -> None:
    expect_validation_error(
        lambda: loads('{"schema_version":1,"payload":{"$type":"os.system"}}', Event)
    )
    expect_validation_error(
        lambda: loads('{"schema_version":999,"payload":{"$type":"Event"}}', Event)
    )
    expect_validation_error(lambda: loads(dumps(build_event()), Market))


def test_decoder_rejects_missing_defaulted_model_fields() -> None:
    missing_period = (
        '{"schema_version":1,"payload":{'
        '"$type":"Market",'
        '"id":{"$type":"MarketId","value":"market:1"},'
        '"event_id":{"$type":"EventId","value":"event:1"},'
        '"kind":{"$enum":"MarketKind","value":"match_winner_2_way"},'
        '"line":null,'
        '"period_index":null,'
        '"provider_references":{"$tuple":[]}'
        '}}'
    )

    expect_validation_error(lambda: loads(missing_period, Market))


def test_decoder_rejects_unexpected_model_fields() -> None:
    unexpected_field = (
        '{"schema_version":1,"payload":{'
        '"$type":"Market",'
        '"id":{"$type":"MarketId","value":"market:1"},'
        '"event_id":{"$type":"EventId","value":"event:1"},'
        '"kind":{"$enum":"MarketKind","value":"match_winner_2_way"},'
        '"period":{"$enum":"MarketPeriod","value":"full_event"},'
        '"line":null,'
        '"period_index":null,'
        '"provider_references":{"$tuple":[]},'
        '"provider_label":"Home/Away"'
        '}}'
    )

    expect_validation_error(lambda: loads(unexpected_field, Market))
