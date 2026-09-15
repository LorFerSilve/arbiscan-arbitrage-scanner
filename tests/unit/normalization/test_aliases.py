"""Tests for deterministic context-aware alias catalogs."""

from arbiscan.domain import (
    CompetitionId,
    ParticipantId,
    ParticipantKind,
    ProviderId,
    Sport,
)
from arbiscan.normalization import (
    CompetitionAlias,
    CompetitionNormalizer,
    ParticipantAlias,
    ParticipantNormalizer,
    ResolutionStatus,
    SportAlias,
    SportNormalizer,
    normalize_alias_key,
)


def test_alias_key_is_conservative() -> None:
    assert normalize_alias_key("  Manchester   UNITED ") == "manchester united"
    assert normalize_alias_key("Bayern München") == "bayern münchen"
    assert normalize_alias_key("Bayern-München") == "bayern-münchen"


def test_sport_aliases_are_exact_and_provider_aware() -> None:
    provider = ProviderId("provider:test")
    normalizer = SportNormalizer(
        (
            SportAlias("football", Sport.FOOTBALL),
            SportAlias("soccer", Sport.FOOTBALL),
            SportAlias("tennis", Sport.TENNIS),
            SportAlias("motor sports", Sport.MOTORSPORT, provider_id=provider),
        )
    )

    assert normalizer.resolve(" Soccer ").value is Sport.FOOTBALL
    assert normalizer.resolve("motor sports").status is ResolutionStatus.UNKNOWN
    assert normalizer.resolve("motor sports", provider_id=provider).value is Sport.MOTORSPORT
    assert normalizer.resolve("rugby").status is ResolutionStatus.UNKNOWN


def test_competition_alias_requires_context_when_name_is_shared() -> None:
    england = CompetitionId("competition:england:premier-league")
    bangladesh = CompetitionId("competition:bangladesh:premier-league")
    normalizer = CompetitionNormalizer(
        (
            CompetitionAlias("Premier League", england, Sport.FOOTBALL, region="England"),
            CompetitionAlias("Premier League", bangladesh, Sport.FOOTBALL, region="Bangladesh"),
            CompetitionAlias("EPL", england, Sport.FOOTBALL, region="England"),
        )
    )

    unresolved = normalizer.resolve("Premier League", sport=Sport.FOOTBALL)
    assert unresolved.status is ResolutionStatus.AMBIGUOUS
    assert set(unresolved.candidates) == {england, bangladesh}

    resolved = normalizer.resolve(
        "Premier League",
        sport=Sport.FOOTBALL,
        region="England",
    )
    assert resolved.status is ResolutionStatus.RESOLVED
    assert resolved.value == england
    assert normalizer.resolve("EPL", sport=Sport.FOOTBALL).status is ResolutionStatus.UNKNOWN


def test_competition_season_and_hierarchy_are_contextual() -> None:
    parent = CompetitionId("competition:champions-league")
    group_stage = CompetitionId("competition:champions-league:group-stage:2026")
    normalizer = CompetitionNormalizer(
        (
            CompetitionAlias(
                "Group Stage",
                group_stage,
                Sport.FOOTBALL,
                season="2026/27",
                parent_competition_id=parent,
            ),
        )
    )

    assert normalizer.resolve("Group Stage", sport=Sport.FOOTBALL).status is ResolutionStatus.UNKNOWN
    resolved = normalizer.resolve(
        "Group Stage",
        sport=Sport.FOOTBALL,
        season="2026/27",
        parent_competition_id=parent,
    )
    assert resolved.value == group_stage


def test_participant_aliases_are_explicit_not_fuzzy() -> None:
    premier_league = CompetitionId("competition:england:premier-league")
    man_united = ParticipantId("participant:manchester-united")
    newcastle = ParticipantId("participant:newcastle-united")
    normalizer = ParticipantNormalizer(
        (
            ParticipantAlias(
                "Manchester United",
                man_united,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
            ParticipantAlias(
                "Man United",
                man_united,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
            ParticipantAlias(
                "Manchester Utd",
                man_united,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
            ParticipantAlias(
                "MUN",
                man_united,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
            ParticipantAlias(
                "United",
                man_united,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
            ParticipantAlias(
                "United",
                newcastle,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=premier_league,
            ),
        )
    )

    context = {
        "sport": Sport.FOOTBALL,
        "kind": ParticipantKind.TEAM,
        "competition_id": premier_league,
    }
    assert normalizer.resolve("Man United", **context).value == man_united
    assert normalizer.resolve("MUN", **context).value == man_united
    assert normalizer.resolve("United", **context).status is ResolutionStatus.AMBIGUOUS
    assert normalizer.resolve("Manchester United Women", **context).status is ResolutionStatus.UNKNOWN


def test_localized_participant_names_need_explicit_alias_data() -> None:
    bundesliga = CompetitionId("competition:germany:bundesliga")
    bayern = ParticipantId("participant:bayern-munich")
    normalizer = ParticipantNormalizer(
        (
            ParticipantAlias(
                "Bayern München",
                bayern,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=bundesliga,
            ),
            ParticipantAlias(
                "Bayern Munich",
                bayern,
                Sport.FOOTBALL,
                ParticipantKind.TEAM,
                competition_id=bundesliga,
            ),
        )
    )

    context = {
        "sport": Sport.FOOTBALL,
        "kind": ParticipantKind.TEAM,
        "competition_id": bundesliga,
    }
    assert normalizer.resolve("Bayern München", **context).value == bayern
    assert normalizer.resolve("Bayern Munich", **context).value == bayern
    assert normalizer.resolve("Bayern-Munich", **context).status is ResolutionStatus.UNKNOWN
