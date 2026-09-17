"""Immutable provider-independent canonical domain entities."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal

from arbiscan.domain.enums import (
    EventStatus,
    MarketKind,
    MarketPeriod,
    OpportunityStatus,
    ParticipantKind,
    ProviderKind,
    QuoteStatus,
    SelectionKind,
    Sport,
)
from arbiscan.domain.errors import DomainValidationError
from arbiscan.domain.identifiers import (
    CompetitionId,
    EventId,
    MarketId,
    OpportunityId,
    ParticipantId,
    ProviderId,
    QuoteId,
    SelectionId,
    StakePlanId,
)
from arbiscan.domain.validation import (
    normalize_currency,
    normalize_datetime,
    normalize_optional_datetime,
    normalize_optional_text,
    normalize_text,
    require_decimal,
    require_instance,
    require_positive_decimal,
)


@dataclass(frozen=True, slots=True)
class Provider:
    """Canonical odds-data provider metadata without credentials or API details."""

    id: ProviderId
    name: str
    kind: ProviderKind

    def __post_init__(self) -> None:
        require_instance(self.id, ProviderId, field="provider.id")
        require_instance(self.kind, ProviderKind, field="provider.kind")
        object.__setattr__(self, "name", normalize_text(self.name, field="provider.name"))


@dataclass(frozen=True, slots=True)
class Competition:
    """Canonical competition or tournament."""

    id: CompetitionId
    sport: Sport
    name: str
    region: str | None = None
    season: str | None = None

    def __post_init__(self) -> None:
        require_instance(self.id, CompetitionId, field="competition.id")
        require_instance(self.sport, Sport, field="competition.sport")
        object.__setattr__(self, "name", normalize_text(self.name, field="competition.name"))
        object.__setattr__(
            self,
            "region",
            normalize_optional_text(self.region, field="competition.region"),
        )
        object.__setattr__(
            self,
            "season",
            normalize_optional_text(self.season, field="competition.season"),
        )


@dataclass(frozen=True, slots=True)
class Participant:
    """Canonical event participant, including teams, players, drivers, or constructors."""

    id: ParticipantId
    sport: Sport
    name: str
    kind: ParticipantKind

    def __post_init__(self) -> None:
        require_instance(self.id, ParticipantId, field="participant.id")
        require_instance(self.sport, Sport, field="participant.sport")
        require_instance(self.kind, ParticipantKind, field="participant.kind")
        object.__setattr__(self, "name", normalize_text(self.name, field="participant.name"))


@dataclass(frozen=True, slots=True)
class ProviderEventReference:
    """Provider-local identifier for one canonical event."""

    provider_id: ProviderId
    external_event_id: str

    def __post_init__(self) -> None:
        require_instance(
            self.provider_id,
            ProviderId,
            field="provider_event_reference.provider_id",
        )
        object.__setattr__(
            self,
            "external_event_id",
            normalize_text(
                self.external_event_id,
                field="provider_event_reference.external_event_id",
                max_length=512,
            ),
        )


@dataclass(frozen=True, slots=True)
class ProviderMarketReference:
    """Provider-local identifier for a market within a provider event."""

    provider_id: ProviderId
    external_event_id: str
    external_market_id: str

    def __post_init__(self) -> None:
        require_instance(
            self.provider_id,
            ProviderId,
            field="provider_market_reference.provider_id",
        )
        object.__setattr__(
            self,
            "external_event_id",
            normalize_text(
                self.external_event_id,
                field="provider_market_reference.external_event_id",
                max_length=512,
            ),
        )
        object.__setattr__(
            self,
            "external_market_id",
            normalize_text(
                self.external_market_id,
                field="provider_market_reference.external_market_id",
                max_length=512,
            ),
        )


@dataclass(frozen=True, slots=True)
class Event:
    """Canonical sporting event shared by all provider adapters."""

    id: EventId
    sport: Sport
    competition: Competition
    participants: tuple[Participant, ...]
    scheduled_start: datetime
    status: EventStatus
    provider_references: tuple[ProviderEventReference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_instance(self.id, EventId, field="event.id")
        require_instance(self.sport, Sport, field="event.sport")
        require_instance(self.competition, Competition, field="event.competition")
        require_instance(self.status, EventStatus, field="event.status")

        participants = tuple(self.participants)
        references = tuple(self.provider_references)
        for participant in participants:
            require_instance(participant, Participant, field="event.participants[]")
        for reference in references:
            require_instance(
                reference,
                ProviderEventReference,
                field="event.provider_references[]",
            )
        object.__setattr__(self, "participants", participants)
        object.__setattr__(self, "provider_references", references)
        object.__setattr__(
            self,
            "scheduled_start",
            normalize_datetime(self.scheduled_start, field="event.scheduled_start"),
        )

        if self.competition.sport is not self.sport:
            raise DomainValidationError("event sport must match competition sport")
        if not participants:
            raise DomainValidationError("event must contain at least one participant")
        if any(participant.sport is not self.sport for participant in participants):
            raise DomainValidationError("every event participant must match the event sport")

        participant_ids = [participant.id for participant in participants]
        if len(set(participant_ids)) != len(participant_ids):
            raise DomainValidationError("event participant IDs must be unique")

        provider_ids = [reference.provider_id for reference in references]
        if len(set(provider_ids)) != len(provider_ids):
            raise DomainValidationError("event may have at most one reference per provider")


@dataclass(frozen=True, slots=True)
class Market:
    """Canonical market with explicit settlement semantics and parameters."""

    id: MarketId
    event_id: EventId
    kind: MarketKind
    period: MarketPeriod = MarketPeriod.FULL_EVENT
    line: Decimal | None = None
    period_index: int | None = None
    provider_references: tuple[ProviderMarketReference, ...] = field(default_factory=tuple)

    def __post_init__(self) -> None:
        require_instance(self.id, MarketId, field="market.id")
        require_instance(self.event_id, EventId, field="market.event_id")
        require_instance(self.kind, MarketKind, field="market.kind")
        require_instance(self.period, MarketPeriod, field="market.period")

        references = tuple(self.provider_references)
        for reference in references:
            require_instance(
                reference,
                ProviderMarketReference,
                field="market.provider_references[]",
            )
        object.__setattr__(self, "provider_references", references)

        if self.line is not None:
            object.__setattr__(self, "line", require_decimal(self.line, field="market.line"))

        parameterized = {MarketKind.TOTAL_POINTS, MarketKind.HANDICAP}
        if self.kind in parameterized and self.line is None:
            raise DomainValidationError(f"{self.kind.value} requires market.line")
        if self.kind not in parameterized and self.line is not None:
            raise DomainValidationError(f"{self.kind.value} does not accept market.line")

        if self.period_index is not None and type(self.period_index) is not int:
            raise DomainValidationError("market.period_index must be an integer")
        indexed_periods = {MarketPeriod.SET, MarketPeriod.PERIOD, MarketPeriod.QUARTER}
        if self.period in indexed_periods:
            if self.period_index is None or self.period_index < 1:
                raise DomainValidationError("indexed market periods require period_index >= 1")
        elif self.period_index is not None:
            raise DomainValidationError("period_index is only valid for indexed market periods")

        if self.kind is MarketKind.SET_WINNER and self.period is not MarketPeriod.SET:
            raise DomainValidationError("set-winner markets must use MarketPeriod.SET")

        provider_ids = [reference.provider_id for reference in references]
        if len(set(provider_ids)) != len(provider_ids):
            raise DomainValidationError("market may have at most one reference per provider")


@dataclass(frozen=True, slots=True)
class Selection:
    """Canonical mutually-exclusive outcome within a market."""

    id: SelectionId
    market_id: MarketId
    kind: SelectionKind
    participant_id: ParticipantId | None = None
    handicap: Decimal | None = None

    def __post_init__(self) -> None:
        require_instance(self.id, SelectionId, field="selection.id")
        require_instance(self.market_id, MarketId, field="selection.market_id")
        require_instance(self.kind, SelectionKind, field="selection.kind")
        if self.participant_id is not None:
            require_instance(
                self.participant_id,
                ParticipantId,
                field="selection.participant_id",
            )

        if self.kind is SelectionKind.PARTICIPANT:
            if self.participant_id is None:
                raise DomainValidationError("participant selection requires participant_id")
        elif self.participant_id is not None:
            raise DomainValidationError("only participant selections may carry participant_id")

        if self.handicap is not None:
            if self.kind is not SelectionKind.PARTICIPANT:
                raise DomainValidationError("only participant selections may carry a handicap")
            object.__setattr__(
                self,
                "handicap",
                require_decimal(self.handicap, field="selection.handicap"),
            )


@dataclass(frozen=True, slots=True)
class OddsQuote:
    """One executable price observation with canonical and transport provenance.

    ``provider_id`` is the price origin (bookmaker/exchange). ``transport_provider_id``
    is the independent feed/API through which ArbiScan observed that price. Legacy and
    direct-source callers may omit the transport identity; it then defaults to the price
    provider so Phase-15 persisted fixtures and direct-provider semantics remain valid.
    """

    id: QuoteId
    provider_id: ProviderId
    event_id: EventId
    market_id: MarketId
    selection_id: SelectionId
    decimal_price: Decimal
    source_event_id: str
    source_market_id: str
    source_selection_id: str
    ingested_at: datetime
    status: QuoteStatus
    source_timestamp: datetime | None = None
    trace_id: str | None = None
    raw_source_reference: str | None = None
    transport_provider_id: ProviderId | None = None

    def __post_init__(self) -> None:
        require_instance(self.id, QuoteId, field="odds_quote.id")
        require_instance(self.provider_id, ProviderId, field="odds_quote.provider_id")
        transport_provider_id = self.transport_provider_id or self.provider_id
        require_instance(
            transport_provider_id,
            ProviderId,
            field="odds_quote.transport_provider_id",
        )
        object.__setattr__(self, "transport_provider_id", transport_provider_id)
        require_instance(self.event_id, EventId, field="odds_quote.event_id")
        require_instance(self.market_id, MarketId, field="odds_quote.market_id")
        require_instance(self.selection_id, SelectionId, field="odds_quote.selection_id")
        require_instance(self.status, QuoteStatus, field="odds_quote.status")

        price = require_decimal(self.decimal_price, field="odds_quote.decimal_price")
        if price <= Decimal("1"):
            raise DomainValidationError("odds_quote.decimal_price must be greater than 1")
        object.__setattr__(self, "decimal_price", price)

        for field_name in ("source_event_id", "source_market_id", "source_selection_id"):
            object.__setattr__(
                self,
                field_name,
                normalize_text(
                    getattr(self, field_name),
                    field=f"odds_quote.{field_name}",
                    max_length=512,
                ),
            )

        object.__setattr__(
            self,
            "ingested_at",
            normalize_datetime(self.ingested_at, field="odds_quote.ingested_at"),
        )
        object.__setattr__(
            self,
            "source_timestamp",
            normalize_optional_datetime(
                self.source_timestamp,
                field="odds_quote.source_timestamp",
            ),
        )
        object.__setattr__(
            self,
            "trace_id",
            normalize_optional_text(self.trace_id, field="odds_quote.trace_id", max_length=512),
        )
        object.__setattr__(
            self,
            "raw_source_reference",
            normalize_optional_text(
                self.raw_source_reference,
                field="odds_quote.raw_source_reference",
                max_length=2048,
            ),
        )
        if self.trace_id is None and self.raw_source_reference is None:
            raise DomainValidationError(
                "odds quote requires trace_id or raw_source_reference for auditability"
            )


@dataclass(frozen=True, slots=True)
class Opportunity:
    """Canonical detected theoretical arbitrage opportunity.

    Phase 3 owns the mathematics that creates this object; Phase 2 only defines
    the validated schema consumed by later subsystems.
    """

    id: OpportunityId
    event_id: EventId
    market_id: MarketId
    quote_ids: tuple[QuoteId, ...]
    implied_probability_sum: Decimal
    theoretical_profit_margin: Decimal
    detected_at: datetime
    status: OpportunityStatus = OpportunityStatus.ACTIVE

    def __post_init__(self) -> None:
        require_instance(self.id, OpportunityId, field="opportunity.id")
        require_instance(self.event_id, EventId, field="opportunity.event_id")
        require_instance(self.market_id, MarketId, field="opportunity.market_id")
        require_instance(self.status, OpportunityStatus, field="opportunity.status")

        quote_ids = tuple(self.quote_ids)
        for quote_id in quote_ids:
            require_instance(quote_id, QuoteId, field="opportunity.quote_ids[]")
        object.__setattr__(self, "quote_ids", quote_ids)
        object.__setattr__(
            self,
            "detected_at",
            normalize_datetime(self.detected_at, field="opportunity.detected_at"),
        )

        if len(quote_ids) < 2:
            raise DomainValidationError("opportunity requires at least two quotes")
        if len(set(quote_ids)) != len(quote_ids):
            raise DomainValidationError("opportunity quote IDs must be unique")

        implied_sum = require_positive_decimal(
            self.implied_probability_sum,
            field="opportunity.implied_probability_sum",
        )
        if implied_sum >= Decimal("1"):
            raise DomainValidationError("opportunity implied probability sum must be below 1")
        object.__setattr__(self, "implied_probability_sum", implied_sum)
        object.__setattr__(
            self,
            "theoretical_profit_margin",
            require_positive_decimal(
                self.theoretical_profit_margin,
                field="opportunity.theoretical_profit_margin",
            ),
        )


@dataclass(frozen=True, slots=True)
class StakeAllocation:
    """One stake instruction within a validated stake plan."""

    quote_id: QuoteId
    selection_id: SelectionId
    provider_id: ProviderId
    amount: Decimal
    expected_payout: Decimal

    def __post_init__(self) -> None:
        require_instance(self.quote_id, QuoteId, field="stake_allocation.quote_id")
        require_instance(
            self.selection_id,
            SelectionId,
            field="stake_allocation.selection_id",
        )
        require_instance(self.provider_id, ProviderId, field="stake_allocation.provider_id")
        object.__setattr__(
            self,
            "amount",
            require_positive_decimal(self.amount, field="stake_allocation.amount"),
        )
        object.__setattr__(
            self,
            "expected_payout",
            require_positive_decimal(
                self.expected_payout,
                field="stake_allocation.expected_payout",
            ),
        )


@dataclass(frozen=True, slots=True)
class StakePlan:
    """Executable rounded stake plan produced by the Phase 3 mathematics layer."""

    id: StakePlanId
    opportunity_id: OpportunityId
    currency: str
    bankroll: Decimal
    allocations: tuple[StakeAllocation, ...]
    guaranteed_payout: Decimal
    guaranteed_profit: Decimal
    created_at: datetime

    def __post_init__(self) -> None:
        require_instance(self.id, StakePlanId, field="stake_plan.id")
        require_instance(
            self.opportunity_id,
            OpportunityId,
            field="stake_plan.opportunity_id",
        )
        allocations = tuple(self.allocations)
        for allocation in allocations:
            require_instance(allocation, StakeAllocation, field="stake_plan.allocations[]")
        object.__setattr__(self, "allocations", allocations)
        object.__setattr__(self, "currency", normalize_currency(self.currency))
        object.__setattr__(
            self,
            "bankroll",
            require_positive_decimal(self.bankroll, field="stake_plan.bankroll"),
        )
        object.__setattr__(
            self,
            "guaranteed_payout",
            require_positive_decimal(
                self.guaranteed_payout,
                field="stake_plan.guaranteed_payout",
            ),
        )
        object.__setattr__(
            self,
            "guaranteed_profit",
            require_positive_decimal(
                self.guaranteed_profit,
                field="stake_plan.guaranteed_profit",
            ),
        )
        object.__setattr__(
            self,
            "created_at",
            normalize_datetime(self.created_at, field="stake_plan.created_at"),
        )

        if len(allocations) < 2:
            raise DomainValidationError("stake plan requires at least two allocations")

        quote_ids = [allocation.quote_id for allocation in allocations]
        if len(set(quote_ids)) != len(quote_ids):
            raise DomainValidationError("stake allocation quote IDs must be unique")
        selection_ids = [allocation.selection_id for allocation in allocations]
        if len(set(selection_ids)) != len(selection_ids):
            raise DomainValidationError("stake allocation selection IDs must be unique")

        total_staked = sum((allocation.amount for allocation in allocations), Decimal("0"))
        if total_staked > self.bankroll:
            raise DomainValidationError("stake plan total stake exceeds bankroll")

        minimum_payout = min(allocation.expected_payout for allocation in allocations)
        if self.guaranteed_payout != minimum_payout:
            raise DomainValidationError(
                "stake_plan.guaranteed_payout must equal the minimum allocation payout"
            )
        if self.guaranteed_profit != self.guaranteed_payout - total_staked:
            raise DomainValidationError(
                "stake_plan.guaranteed_profit must equal guaranteed payout minus total stake"
            )