"""Deterministic Phase 5 provider matrix and canonical fixture catalog."""

from __future__ import annotations

from dataclasses import dataclass
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
    ProviderEventReference,
    ProviderId,
    ProviderKind,
    ProviderMarketReference,
    Selection,
    SelectionId,
    SelectionKind,
    Sport,
)
from arbiscan.matching.catalog import CanonicalRegistry, StaticCanonicalIdHooks
from arbiscan.providers.fake import FakeProvider, FakeProviderFixtures
from arbiscan.providers.models import (
    OddsSnapshot,
    ProviderOperation,
    SourceCompetition,
    SourceEvent,
    SourceMarket,
    SourceOddsFormat,
    SourceParticipant,
    SourceSelectionQuote,
)
from arbiscan.providers.resilience import ProviderCallPolicy

PHASE5_AS_OF = datetime(2026, 9, 13, 12, 0, tzinfo=UTC)
PHASE5_FRESHNESS_WINDOW = timedelta(minutes=2)


@dataclass(frozen=True, slots=True)
class SyntheticScenario:
    """All deterministic inputs needed to run the Phase 5 vertical slice."""

    adapters: tuple[FakeProvider, ...]
    registry: CanonicalRegistry
    as_of: datetime
    freshness_window: timedelta
    provider_policy: ProviderCallPolicy


@dataclass(frozen=True, slots=True)
class _EventDefinition:
    key: str
    event_id: EventId
    market_id: MarketId
    home: Participant
    away: Participant
    home_selection_id: SelectionId
    draw_selection_id: SelectionId
    away_selection_id: SelectionId
    starts_at: datetime


def _participant(slug: str, name: str) -> Participant:
    return Participant(
        id=ParticipantId(f"participant:{slug}"),
        sport=Sport.FOOTBALL,
        name=name,
        kind=ParticipantKind.TEAM,
    )


def _event_definition(
    *,
    key: str,
    home: Participant,
    away: Participant,
    starts_at: datetime,
) -> _EventDefinition:
    return _EventDefinition(
        key=key,
        event_id=EventId(f"event:phase5:{key}"),
        market_id=MarketId(f"market:phase5:{key}:1x2"),
        home=home,
        away=away,
        home_selection_id=SelectionId(f"selection:phase5:{key}:home"),
        draw_selection_id=SelectionId(f"selection:phase5:{key}:draw"),
        away_selection_id=SelectionId(f"selection:phase5:{key}:away"),
        starts_at=starts_at,
    )


def _source_event(prefix: str, definition: _EventDefinition) -> SourceEvent:
    return SourceEvent(
        external_id=f"{prefix}:{definition.key}",
        sport=Sport.FOOTBALL,
        competition_external_id=f"{prefix}:epl",
        participants=(
            SourceParticipant(
                external_id=f"{prefix}:{definition.home.id.value}",
                name=definition.home.name,
                role="home",
            ),
            SourceParticipant(
                external_id=f"{prefix}:{definition.away.id.value}",
                name=definition.away.name,
                role="away",
            ),
        ),
        scheduled_start=definition.starts_at,
        source_status="scheduled",
    )


def _source_market(
    prefix: str,
    definition: _EventDefinition,
    prices: tuple[str, str, str],
    *,
    source_status: str = "active",
) -> SourceMarket:
    market_id = f"{prefix}:{definition.key}:1x2"
    return SourceMarket(
        external_event_id=f"{prefix}:{definition.key}",
        external_market_id=market_id,
        label="Full Time Result",
        source_status=source_status,
        selections=(
            SourceSelectionQuote(
                external_selection_id=f"{prefix}:{definition.key}:home",
                label=definition.home.name,
                price=prices[0],
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id=f"{prefix}:{definition.key}:draw",
                label="Draw",
                price=prices[1],
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id=f"{prefix}:{definition.key}:away",
                label=definition.away.name,
                price=prices[2],
                odds_format=SourceOddsFormat.DECIMAL,
            ),
        ),
    )


def _snapshot(
    provider_id: ProviderId,
    prefix: str,
    definition: _EventDefinition,
    prices: tuple[str, str, str],
    *,
    age: timedelta = timedelta(seconds=15),
    market_status: str = "active",
) -> OddsSnapshot:
    return OddsSnapshot(
        provider_id=provider_id,
        external_event_id=f"{prefix}:{definition.key}",
        markets=(
            _source_market(
                prefix,
                definition,
                prices,
                source_status=market_status,
            ),
        ),
        ingested_at=PHASE5_AS_OF,
        source_timestamp=PHASE5_AS_OF - age,
        trace_id=f"phase5:{prefix}:{definition.key}",
    )


def _hooks(
    prefix: str,
    definitions: tuple[_EventDefinition, ...],
    *,
    include_keys: frozenset[str],
) -> StaticCanonicalIdHooks:
    selected = tuple(value for value in definitions if value.key in include_keys)
    return StaticCanonicalIdHooks(
        competition_ids={f"{prefix}:epl": CompetitionId("competition:premier-league")},
        event_ids={f"{prefix}:{definition.key}": definition.event_id for definition in selected},
        market_ids={
            f"{prefix}:{definition.key}:1x2": definition.market_id for definition in selected
        },
        selection_ids={
            (
                f"{prefix}:{definition.key}:1x2",
                f"{prefix}:{definition.key}:home",
            ): definition.home_selection_id
            for definition in selected
        }
        | {
            (
                f"{prefix}:{definition.key}:1x2",
                f"{prefix}:{definition.key}:draw",
            ): definition.draw_selection_id
            for definition in selected
        }
        | {
            (
                f"{prefix}:{definition.key}:1x2",
                f"{prefix}:{definition.key}:away",
            ): definition.away_selection_id
            for definition in selected
        },
    )


def _canonical_registry(
    providers: tuple[Provider, Provider, Provider],
    definitions: tuple[_EventDefinition, ...],
) -> CanonicalRegistry:
    alpha, beta, gamma = providers
    competition = Competition(
        id=CompetitionId("competition:premier-league"),
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )

    provider_keys: dict[str, tuple[tuple[Provider, str], ...]] = {
        "arb": ((alpha, "alpha"), (beta, "beta"), (gamma, "gamma")),
        "noarb": ((alpha, "alpha"), (beta, "beta")),
        "stale": ((alpha, "alpha"),),
        "suspended": ((alpha, "alpha"),),
        "malformed": ((alpha, "alpha"),),
    }

    events: list[Event] = []
    markets: list[Market] = []
    selections: list[Selection] = []

    for definition in definitions:
        references = provider_keys[definition.key]
        events.append(
            Event(
                id=definition.event_id,
                sport=Sport.FOOTBALL,
                competition=competition,
                participants=(definition.home, definition.away),
                scheduled_start=definition.starts_at,
                status=EventStatus.SCHEDULED,
                provider_references=tuple(
                    ProviderEventReference(
                        provider_id=provider.id,
                        external_event_id=f"{prefix}:{definition.key}",
                    )
                    for provider, prefix in references
                ),
            )
        )
        markets.append(
            Market(
                id=definition.market_id,
                event_id=definition.event_id,
                kind=MarketKind.MATCH_WINNER_3_WAY,
                period=MarketPeriod.REGULATION,
                provider_references=tuple(
                    ProviderMarketReference(
                        provider_id=provider.id,
                        external_event_id=f"{prefix}:{definition.key}",
                        external_market_id=f"{prefix}:{definition.key}:1x2",
                    )
                    for provider, prefix in references
                ),
            )
        )
        selections.extend(
            (
                Selection(
                    id=definition.home_selection_id,
                    market_id=definition.market_id,
                    kind=SelectionKind.PARTICIPANT,
                    participant_id=definition.home.id,
                ),
                Selection(
                    id=definition.draw_selection_id,
                    market_id=definition.market_id,
                    kind=SelectionKind.DRAW,
                ),
                Selection(
                    id=definition.away_selection_id,
                    market_id=definition.market_id,
                    kind=SelectionKind.PARTICIPANT,
                    participant_id=definition.away.id,
                ),
            )
        )

    participants = tuple(
        sorted(
            {
                participant.id: participant
                for definition in definitions
                for participant in (definition.home, definition.away)
            }.values(),
            key=lambda participant: participant.id.value,
        )
    )
    return CanonicalRegistry(
        competitions=(competition,),
        participants=participants,
        events=tuple(events),
        markets=tuple(markets),
        selections=tuple(selections),
    )


def build_phase5_synthetic_scenario() -> SyntheticScenario:
    """Create the complete deterministic success/failure matrix for Phase 5."""
    alpha_provider = Provider(
        id=ProviderId("provider:synthetic-alpha"),
        name="Synthetic Alpha",
        kind=ProviderKind.SYNTHETIC,
    )
    beta_provider = Provider(
        id=ProviderId("provider:synthetic-beta"),
        name="Synthetic Beta",
        kind=ProviderKind.SYNTHETIC,
    )
    gamma_provider = Provider(
        id=ProviderId("provider:synthetic-gamma"),
        name="Synthetic Gamma Outage",
        kind=ProviderKind.SYNTHETIC,
    )

    definitions = (
        _event_definition(
            key="arb",
            home=_participant("arsenal", "Arsenal"),
            away=_participant("chelsea", "Chelsea"),
            starts_at=datetime(2026, 9, 20, 14, 0, tzinfo=UTC),
        ),
        _event_definition(
            key="noarb",
            home=_participant("liverpool", "Liverpool"),
            away=_participant("everton", "Everton"),
            starts_at=datetime(2026, 9, 20, 16, 30, tzinfo=UTC),
        ),
        _event_definition(
            key="stale",
            home=_participant("manchester-city", "Manchester City"),
            away=_participant("tottenham", "Tottenham"),
            starts_at=datetime(2026, 9, 21, 14, 0, tzinfo=UTC),
        ),
        _event_definition(
            key="suspended",
            home=_participant("manchester-united", "Manchester United"),
            away=_participant("newcastle", "Newcastle United"),
            starts_at=datetime(2026, 9, 21, 16, 30, tzinfo=UTC),
        ),
        _event_definition(
            key="malformed",
            home=_participant("aston-villa", "Aston Villa"),
            away=_participant("fulham", "Fulham"),
            starts_at=datetime(2026, 9, 22, 19, 0, tzinfo=UTC),
        ),
    )
    by_key = {definition.key: definition for definition in definitions}

    registry = _canonical_registry(
        (alpha_provider, beta_provider, gamma_provider),
        definitions,
    )

    competition_alpha = SourceCompetition(
        external_id="alpha:epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    alpha_events = tuple(_source_event("alpha", definition) for definition in definitions)
    alpha_snapshots = (
        _snapshot(alpha_provider.id, "alpha", by_key["arb"], ("2.90", "3.60", "3.00")),
        _snapshot(alpha_provider.id, "alpha", by_key["noarb"], ("2.10", "3.30", "3.50")),
        _snapshot(
            alpha_provider.id,
            "alpha",
            by_key["stale"],
            ("4.00", "4.00", "4.00"),
            age=timedelta(minutes=10),
        ),
        _snapshot(
            alpha_provider.id,
            "alpha",
            by_key["suspended"],
            ("4.20", "4.20", "4.20"),
            market_status="suspended",
        ),
        _snapshot(
            alpha_provider.id,
            "alpha",
            by_key["malformed"],
            ("3.20", "not-a-price", "3.20"),
        ),
    )
    alpha = FakeProvider(
        provider=alpha_provider,
        fixtures=FakeProviderFixtures(
            sports=(Sport.FOOTBALL,),
            competitions=(competition_alpha,),
            events=alpha_events,
            odds_snapshots=alpha_snapshots,
        ),
        canonical_id_hooks=_hooks(
            "alpha",
            definitions,
            include_keys=frozenset(definition.key for definition in definitions),
        ),
    )

    competition_beta = SourceCompetition(
        external_id="beta:epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    mismatch_event = SourceEvent(
        external_id="beta:lookalike",
        sport=Sport.FOOTBALL,
        competition_external_id="beta:epl",
        participants=(
            SourceParticipant(
                external_id="beta:participant:arsenal",
                name="Arsenal",
                role="home",
            ),
            SourceParticipant(
                external_id="beta:participant:chelsea",
                name="Chelsea",
                role="away",
            ),
        ),
        scheduled_start=datetime(2026, 9, 21, 14, 0, tzinfo=UTC),
        source_status="scheduled",
    )
    mismatch_market = SourceMarket(
        external_event_id="beta:lookalike",
        external_market_id="beta:lookalike:1x2",
        label="Full Time Result",
        selections=(
            SourceSelectionQuote(
                external_selection_id="beta:lookalike:home",
                label="Arsenal",
                price="9.00",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="beta:lookalike:draw",
                label="Draw",
                price="9.00",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
            SourceSelectionQuote(
                external_selection_id="beta:lookalike:away",
                label="Chelsea",
                price="9.00",
                odds_format=SourceOddsFormat.DECIMAL,
            ),
        ),
    )
    beta_events = (
        _source_event("beta", by_key["arb"]),
        _source_event("beta", by_key["noarb"]),
        mismatch_event,
    )
    beta_snapshots = (
        _snapshot(beta_provider.id, "beta", by_key["arb"], ("3.40", "3.40", "3.50")),
        _snapshot(beta_provider.id, "beta", by_key["noarb"], ("2.05", "3.40", "3.45")),
        OddsSnapshot(
            provider_id=beta_provider.id,
            external_event_id="beta:lookalike",
            markets=(mismatch_market,),
            ingested_at=PHASE5_AS_OF,
            source_timestamp=PHASE5_AS_OF - timedelta(seconds=15),
            trace_id="phase5:beta:lookalike",
        ),
    )
    beta = FakeProvider(
        provider=beta_provider,
        fixtures=FakeProviderFixtures(
            sports=(Sport.FOOTBALL,),
            competitions=(competition_beta,),
            events=beta_events,
            odds_snapshots=beta_snapshots,
        ),
        canonical_id_hooks=_hooks(
            "beta",
            definitions,
            include_keys=frozenset({"arb", "noarb"}),
        ),
    )

    competition_gamma = SourceCompetition(
        external_id="gamma:epl",
        sport=Sport.FOOTBALL,
        name="Premier League",
        region="England",
        season="2026/27",
    )
    gamma_event = _source_event("gamma", by_key["arb"])
    gamma = FakeProvider(
        provider=gamma_provider,
        fixtures=FakeProviderFixtures(
            sports=(Sport.FOOTBALL,),
            competitions=(competition_gamma,),
            events=(gamma_event,),
            odds_snapshots=(
                _snapshot(
                    gamma_provider.id,
                    "gamma",
                    by_key["arb"],
                    ("3.30", "3.30", "3.30"),
                ),
            ),
        ),
        canonical_id_hooks=_hooks(
            "gamma",
            definitions,
            include_keys=frozenset({"arb"}),
        ),
        operation_delays={ProviderOperation.FETCH_ODDS: 0.05},
    )

    return SyntheticScenario(
        adapters=(alpha, beta, gamma),
        registry=registry,
        as_of=PHASE5_AS_OF,
        freshness_window=PHASE5_FRESHNESS_WINDOW,
        provider_policy=ProviderCallPolicy(
            timeout_seconds=0.005,
            max_attempts=1,
            base_backoff_seconds=0.0,
            max_backoff_seconds=0.0,
            jitter_ratio=0.0,
        ),
    )
