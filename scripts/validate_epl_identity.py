"""Non-executable Phase-19 EPL identity review using the Phase-7/8 gates.

A temporary canonical registry is anchored to The Odds API's fixture list;
it is NOT an independently reviewed, persistent canonical event catalog.
OddsPapi's participant1/2 roles are not documented as home/away, so every
result remains blocked from canonical quote and arbitrage eligibility.
"""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from datetime import timedelta

from arbiscan.domain import (
    Competition,
    CompetitionId,
    Event,
    EventId,
    EventStatus,
    Participant,
    ParticipantId,
    ParticipantKind,
    ProviderEventReference,
    Sport,
)
from arbiscan.matching import (
    CanonicalRegistry,
    EventMatcher,
    EventMatchStatus,
    NormalizedEventEvidence,
    ParticipantOrderPolicy,
)
from arbiscan.normalization import (
    CompetitionAlias,
    CompetitionNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    prepare_event_evidence,
)
from arbiscan.normalization.football_1x2 import (
    FixtureSideAlignment,
    assess_oddspapi_fixture_order,
)
from arbiscan.providers import SourceCompetition, SourceEvent
from arbiscan.providers.oddspapi import ODDSPAPI_PROVIDER_ID
from arbiscan.providers.the_odds_api import THE_ODDS_API_PROVIDER_ID

# An explicitly reviewed, narrow identity vocabulary taken from the named
# live discovery candidates. Other names, nicknames, women/youth/reserve
# teams and newly promoted clubs MUST NOT be guessed into this catalog.
_REVIEWED_CLUBS = (
    ("chelsea", "Chelsea"),
    ("manchester-united", "Manchester United"),
    ("hull-city", "Hull City"),
    ("ipswich-town", "Ipswich Town"),
    ("brentford", "Brentford"),
    ("nottingham-forest", "Nottingham Forest"),
    ("tottenham-hotspur", "Tottenham Hotspur"),
    ("crystal-palace", "Crystal Palace"),
    ("aston-villa", "Aston Villa"),
    ("fulham", "Fulham"),
    ("liverpool", "Liverpool"),
    ("arsenal", "Arsenal"),
    ("newcastle-united", "Newcastle United"),
    ("everton", "Everton"),
)
_COMPETITION = Competition(
    CompetitionId("competition:england:premier-league"),
    Sport.FOOTBALL,
    "Premier League",
    "England",
)
_PARTICIPANTS = tuple(
    Participant(
        ParticipantId(f"participant:football:{slug}"),
        Sport.FOOTBALL,
        name,
        ParticipantKind.TEAM,
    )
    for slug, name in _REVIEWED_CLUBS
)
_BY_ID = {participant.id: participant for participant in _PARTICIPANTS}
_COMPETITION_NORMALIZER = CompetitionNormalizer(
    (
        CompetitionAlias(
            "EPL",
            _COMPETITION.id,
            Sport.FOOTBALL,
            provider_id=THE_ODDS_API_PROVIDER_ID,
            region="Soccer",
        ),
        CompetitionAlias(
            "Premier League",
            _COMPETITION.id,
            Sport.FOOTBALL,
            provider_id=ODDSPAPI_PROVIDER_ID,
            region="England",
        ),
        CompetitionAlias(
            "Premier League",
            _COMPETITION.id,
            Sport.FOOTBALL,
            provider_id=ODDSPAPI_PROVIDER_ID,
            region="England clubs",
        ),
    )
)
_PARTICIPANT_NORMALIZER = ParticipantNormalizer(
    tuple(
        ParticipantAlias(
            alias,
            participant.id,
            Sport.FOOTBALL,
            ParticipantKind.TEAM,
            competition_id=_COMPETITION.id,
        )
        for participant in _PARTICIPANTS
        for alias in (participant.name, f"{participant.name} FC")
    )
)
_MAX_DELTA = timedelta(minutes=5)
_PREMATCH = frozenset({"pre-game", "pre-match", "not started"})


@dataclass(frozen=True, slots=True)
class CanonicalReview:
    """Read-only review result; no quote-authorizing canonical ID hooks."""

    provisional_pairs: tuple[tuple[SourceEvent, SourceEvent], ...]
    apparent_reversed_order: int
    unresolved_papi_events: int
    excluded_odds_events: int
    ambiguous_papi_events: int

    @property
    def quote_eligible_pairs(self) -> int:
        """Fail closed: participant1/2 is not verified as home/away."""
        return 0


def _prepare(
    event: SourceEvent,
    competition: SourceCompetition,
    *,
    odds_api: bool,
) -> NormalizedEventEvidence | None:
    provider = THE_ODDS_API_PROVIDER_ID if odds_api else ODDSPAPI_PROVIDER_ID
    expected_roles = ("home", "away") if odds_api else ("participant1", "participant2")
    if (
        event.sport is not Sport.FOOTBALL
        or len(event.participants) != 2
        or tuple(p.role for p in event.participants) != expected_roles
    ):
        return None
    try:
        result = prepare_event_evidence(
            provider_id=provider,
            event=event,
            competition=competition,
            competition_normalizer=_COMPETITION_NORMALIZER,
            participant_normalizer=_PARTICIPANT_NORMALIZER,
            participant_kind=ParticipantKind.TEAM,
            order_policy=(
                ParticipantOrderPolicy.ORDERED if odds_api else ParticipantOrderPolicy.UNORDERED
            ),
        )
    except ValueError:
        # Two distinct source labels may resolve to the *same* canonical team.
        # NormalizedEventEvidence rejects that duplicate; keep it ineligible.
        return None
    if result.evidence is None:
        return None
    ids = result.evidence.participant_ids
    return result.evidence if len(set(ids)) == 2 else None


def validate_epl_identity(
    odds_competition: SourceCompetition,
    odds_events: tuple[SourceEvent, ...],
    papi_competition: SourceCompetition,
    papi_events: tuple[SourceEvent, ...],
) -> CanonicalReview:
    """Normalize explicit club/competition aliases, then match using Phase 8.

    The Odds API's home/away records form an ephemeral comparison registry,
    not an approved independent source of canonical event truth. OddsPapi
    provides no documented home/away mapping for participant1/participant2.
    """
    # Source-local fixture IDs are identity-bearing. Reused IDs must never
    # establish distinct canonical events, even if teams and kickoff differ.
    odds_id_counts = Counter(event.external_id for event in odds_events)
    papi_id_counts = Counter(event.external_id for event in papi_events)
    anchors: list[Event] = []
    by_event_id: dict[EventId, tuple[SourceEvent, tuple[ParticipantId, ...]]] = {}
    excluded = 0
    for index, event in enumerate(odds_events):
        if odds_id_counts[event.external_id] != 1:
            excluded += 1
            continue
        evidence = _prepare(event, odds_competition, odds_api=True)
        if evidence is None:
            excluded += 1
            continue
        ids = evidence.participant_ids
        key = EventId(f"event:phase19-ephemeral:{index}")
        anchors.append(
            Event(
                id=key,
                sport=Sport.FOOTBALL,
                competition=_COMPETITION,
                participants=tuple(_BY_ID[participant_id] for participant_id in ids),
                scheduled_start=event.scheduled_start,
                status=EventStatus.SCHEDULED,
                provider_references=(
                    ProviderEventReference(THE_ODDS_API_PROVIDER_ID, event.external_id),
                ),
            )
        )
        by_event_id[key] = (event, ids)

    registry = CanonicalRegistry(
        competitions=(_COMPETITION,),
        participants=_PARTICIPANTS,
        events=tuple(anchors),
        markets=(),
        selections=(),
    )
    matcher = EventMatcher(registry)
    candidates: list[tuple[EventId, SourceEvent, SourceEvent, bool]] = []
    ambiguous = 0
    for event in papi_events:
        if papi_id_counts[event.external_id] != 1:
            continue
        if event.source_status.casefold() not in _PREMATCH:
            continue
        evidence = _prepare(event, papi_competition, odds_api=False)
        if evidence is None:
            continue
        decision = matcher.match(evidence)
        if decision.status is EventMatchStatus.AMBIGUOUS:
            ambiguous += 1
            continue
        if decision.status is not EventMatchStatus.MATCHED or decision.matched_event_id is None:
            continue
        anchor_event, anchor_ids = by_event_id[decision.matched_event_id]
        if abs(anchor_event.scheduled_start - event.scheduled_start) > _MAX_DELTA:
            continue
        candidates.append(
            (
                decision.matched_event_id,
                anchor_event,
                event,
                assess_oddspapi_fixture_order(
                    reference_home=anchor_ids[0],
                    reference_away=anchor_ids[1],
                    participant1=evidence.participant_ids[0],
                    participant2=evidence.participant_ids[1],
                )
                is FixtureSideAlignment.REVERSED,
            )
        )

    # A provider cannot identify one canonical fixture through multiple IDs.
    multiplicities = Counter(row[0] for row in candidates)
    accepted = tuple(row for row in candidates if multiplicities[row[0]] == 1)
    return CanonicalReview(
        provisional_pairs=tuple((row[1], row[2]) for row in accepted),
        apparent_reversed_order=sum(row[3] for row in accepted),
        unresolved_papi_events=len(papi_events) - len(accepted),
        excluded_odds_events=excluded,
        ambiguous_papi_events=ambiguous,
    )
