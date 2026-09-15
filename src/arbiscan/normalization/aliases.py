"""Context-aware explicit alias catalogs for normalization.

These catalogs intentionally avoid fuzzy matching.  Aliases only resolve when an
explicit catalog entry is compatible with the supplied context; missing context is
reported as unknown or ambiguous instead of being guessed.
"""

from __future__ import annotations

from dataclasses import dataclass

from arbiscan.domain import (
    CompetitionId,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Sport,
)
from arbiscan.normalization.resolution import Resolution
from arbiscan.normalization.text import normalize_alias_key, normalize_optional_alias_key


@dataclass(frozen=True, slots=True)
class SportAlias:
    alias: str
    sport: Sport
    provider_id: ProviderId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", normalize_alias_key(self.alias))
        if not isinstance(self.sport, Sport):
            raise ValueError("sport alias sport must be Sport")
        if self.provider_id is not None and not isinstance(self.provider_id, ProviderId):
            raise ValueError("sport alias provider_id must be ProviderId")


@dataclass(frozen=True, slots=True)
class SportNormalizer:
    entries: tuple[SportAlias, ...]

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, SportAlias) for entry in entries):
            raise ValueError("sport normalizer entries must be SportAlias values")
        object.__setattr__(self, "entries", entries)

    def resolve(self, alias: str, *, provider_id: ProviderId | None = None) -> Resolution[Sport]:
        key = normalize_alias_key(alias, field_name="sport alias")
        if provider_id is not None and not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")

        exact = tuple(entry for entry in self.entries if entry.alias == key)
        if provider_id is not None:
            provider_specific = tuple(entry for entry in exact if entry.provider_id == provider_id)
            matches = provider_specific or tuple(entry for entry in exact if entry.provider_id is None)
        else:
            matches = tuple(entry for entry in exact if entry.provider_id is None)

        candidates = tuple(sorted({entry.sport for entry in matches}, key=lambda value: value.value))
        if len(candidates) == 1:
            return Resolution.resolved(candidates[0], detail="explicit sport alias")
        if len(candidates) > 1:
            return Resolution.ambiguous(candidates, detail="sport alias maps to multiple sports")
        if exact and provider_id is None and any(entry.provider_id is not None for entry in exact):
            return Resolution.unknown(detail="sport alias requires provider context")
        return Resolution.unknown(detail="unknown sport alias")


@dataclass(frozen=True, slots=True)
class CompetitionAlias:
    alias: str
    competition_id: CompetitionId
    sport: Sport
    provider_id: ProviderId | None = None
    region: str | None = None
    season: str | None = None
    parent_competition_id: CompetitionId | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", normalize_alias_key(self.alias))
        if not isinstance(self.competition_id, CompetitionId):
            raise ValueError("competition alias competition_id must be CompetitionId")
        if not isinstance(self.sport, Sport):
            raise ValueError("competition alias sport must be Sport")
        if self.provider_id is not None and not isinstance(self.provider_id, ProviderId):
            raise ValueError("competition alias provider_id must be ProviderId")
        if self.parent_competition_id is not None and not isinstance(
            self.parent_competition_id, CompetitionId
        ):
            raise ValueError("competition alias parent_competition_id must be CompetitionId")
        object.__setattr__(
            self,
            "region",
            normalize_optional_alias_key(self.region, field_name="competition region"),
        )
        object.__setattr__(
            self,
            "season",
            normalize_optional_alias_key(self.season, field_name="competition season"),
        )


@dataclass(frozen=True, slots=True)
class CompetitionNormalizer:
    entries: tuple[CompetitionAlias, ...]

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, CompetitionAlias) for entry in entries):
            raise ValueError("competition normalizer entries must be CompetitionAlias values")
        object.__setattr__(self, "entries", entries)

    def resolve(
        self,
        alias: str,
        *,
        sport: Sport,
        provider_id: ProviderId | None = None,
        region: str | None = None,
        season: str | None = None,
        parent_competition_id: CompetitionId | None = None,
    ) -> Resolution[CompetitionId]:
        key = normalize_alias_key(alias, field_name="competition alias")
        if not isinstance(sport, Sport):
            raise ValueError("sport must be Sport")
        if provider_id is not None and not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if parent_competition_id is not None and not isinstance(
            parent_competition_id, CompetitionId
        ):
            raise ValueError("parent_competition_id must be CompetitionId")
        region_key = normalize_optional_alias_key(region, field_name="competition region")
        season_key = normalize_optional_alias_key(season, field_name="competition season")

        full: set[CompetitionId] = set()
        potential: set[CompetitionId] = set()
        for entry in self.entries:
            if entry.alias != key or entry.sport is not sport:
                continue
            states = (
                _context_state(entry.provider_id, provider_id),
                _context_state(entry.region, region_key),
                _context_state(entry.season, season_key),
                _context_state(entry.parent_competition_id, parent_competition_id),
            )
            if "conflict" in states:
                continue
            if "missing" in states:
                potential.add(entry.competition_id)
            else:
                full.add(entry.competition_id)

        candidates = full | potential
        if len(candidates) > 1:
            return Resolution.ambiguous(
                tuple(sorted(candidates, key=lambda value: value.value)),
                detail="competition alias remains ambiguous in the supplied context",
            )
        if len(full) == 1 and (not potential or potential == full):
            return Resolution.resolved(next(iter(full)), detail="explicit competition alias")
        if candidates:
            return Resolution.unknown(detail="competition alias requires additional context")
        return Resolution.unknown(detail="unknown competition alias")


@dataclass(frozen=True, slots=True)
class ParticipantAlias:
    alias: str
    participant_id: ParticipantId
    sport: Sport
    kind: ParticipantKind
    provider_id: ProviderId | None = None
    competition_id: CompetitionId | None = None
    region: str | None = None

    def __post_init__(self) -> None:
        object.__setattr__(self, "alias", normalize_alias_key(self.alias))
        if not isinstance(self.participant_id, ParticipantId):
            raise ValueError("participant alias participant_id must be ParticipantId")
        if not isinstance(self.sport, Sport):
            raise ValueError("participant alias sport must be Sport")
        if not isinstance(self.kind, ParticipantKind):
            raise ValueError("participant alias kind must be ParticipantKind")
        if self.provider_id is not None and not isinstance(self.provider_id, ProviderId):
            raise ValueError("participant alias provider_id must be ProviderId")
        if self.competition_id is not None and not isinstance(self.competition_id, CompetitionId):
            raise ValueError("participant alias competition_id must be CompetitionId")
        object.__setattr__(
            self,
            "region",
            normalize_optional_alias_key(self.region, field_name="participant region"),
        )


@dataclass(frozen=True, slots=True)
class ParticipantNormalizer:
    entries: tuple[ParticipantAlias, ...]

    def __post_init__(self) -> None:
        entries = tuple(self.entries)
        if any(not isinstance(entry, ParticipantAlias) for entry in entries):
            raise ValueError("participant normalizer entries must be ParticipantAlias values")
        object.__setattr__(self, "entries", entries)

    def resolve(
        self,
        alias: str,
        *,
        sport: Sport,
        kind: ParticipantKind | None = None,
        provider_id: ProviderId | None = None,
        competition_id: CompetitionId | None = None,
        region: str | None = None,
    ) -> Resolution[ParticipantId]:
        key = normalize_alias_key(alias, field_name="participant alias")
        if not isinstance(sport, Sport):
            raise ValueError("sport must be Sport")
        if kind is not None and not isinstance(kind, ParticipantKind):
            raise ValueError("kind must be ParticipantKind")
        if provider_id is not None and not isinstance(provider_id, ProviderId):
            raise ValueError("provider_id must be ProviderId")
        if competition_id is not None and not isinstance(competition_id, CompetitionId):
            raise ValueError("competition_id must be CompetitionId")
        region_key = normalize_optional_alias_key(region, field_name="participant region")

        full: set[ParticipantId] = set()
        potential: set[ParticipantId] = set()
        for entry in self.entries:
            if entry.alias != key or entry.sport is not sport:
                continue
            states = (
                _context_state(entry.kind, kind),
                _context_state(entry.provider_id, provider_id),
                _context_state(entry.competition_id, competition_id),
                _context_state(entry.region, region_key),
            )
            if "conflict" in states:
                continue
            if "missing" in states:
                potential.add(entry.participant_id)
            else:
                full.add(entry.participant_id)

        candidates = full | potential
        if len(candidates) > 1:
            return Resolution.ambiguous(
                tuple(sorted(candidates, key=lambda value: value.value)),
                detail="participant alias remains ambiguous in the supplied context",
            )
        if len(full) == 1 and (not potential or potential == full):
            return Resolution.resolved(next(iter(full)), detail="explicit participant alias")
        if candidates:
            return Resolution.unknown(detail="participant alias requires additional context")
        return Resolution.unknown(detail="unknown participant alias")


def _context_state(expected: object | None, actual: object | None) -> str:
    if expected is None:
        return "match"
    if actual is None:
        return "missing"
    return "match" if expected == actual else "conflict"
