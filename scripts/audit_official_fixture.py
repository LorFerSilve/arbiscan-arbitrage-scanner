"""Offline evidence audit for ONE independently sourced Premier League fixture.

Independent fixture facts are from the official Premier League match page,
cross-checked against Chelsea FC and Manchester United fixture listings on
2026-10-28. This does not certify OddsPapi participant1/2 home/away roles,
source fixture IDs, prices, bookmaker terms, licences or quote eligibility.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from arbiscan.normalization.football_1x2 import FixtureSideAlignment
from arbiscan.providers import SourceEvent
from scripts.validate_epl_identity import CanonicalReview

OFFICIAL_MATCH_ID = "2645278"
OFFICIAL_MATCH_URL = (
    "https://www.premierleague.com/en/match/2645278/"
    "chelsea-vs-manchester-united/info"
)
OFFICIAL_HOME = "Chelsea"
OFFICIAL_AWAY = "Manchester United"
OFFICIAL_KICKOFF = datetime(2026, 10, 31, 12, 30, tzinfo=UTC)
_MAX_DRIFT = timedelta(minutes=5)
_PREMATCH = frozenset({"pre-game", "pre-match", "not started"})


@dataclass(frozen=True, slots=True)
class IndependentFixtureAudit:
    """Comparison with the published fixture, not an executable event match."""

    official_reference_id: str
    reviewed_provisional_pair: bool
    papi_order_relative_to_official: FixtureSideAlignment | None
    reason: str

    @property
    def can_fetch_quotes(self) -> bool:
        """Never promote independent schedule agreement to quote authorization."""
        return False

    @property
    def provider_ids_independently_verified(self) -> bool:
        """An official fixture ID is not an API provider's fixture ID."""
        return False


def _club(name: str) -> str:
    """A narrow, exact alias: literal club name or one trailing ' FC' only."""
    value = name.strip().casefold()
    return value.removesuffix(" fc")


def _odds_matches_official(event: SourceEvent) -> bool:
    return (
        event.competition_external_id == "soccer_epl"
        and len(event.participants) == 2
        and tuple(p.role for p in event.participants) == ("home", "away")
        and _club(event.participants[0].name) == _club(OFFICIAL_HOME)
        and _club(event.participants[1].name) == _club(OFFICIAL_AWAY)
        and abs(event.scheduled_start - OFFICIAL_KICKOFF) <= _MAX_DRIFT
    )


def _papi_orientation(event: SourceEvent) -> FixtureSideAlignment:
    if (
        len(event.participants) != 2
        or tuple(p.role for p in event.participants) != ("participant1", "participant2")
        or event.source_status.casefold() not in _PREMATCH
        or abs(event.scheduled_start - OFFICIAL_KICKOFF) > _MAX_DRIFT
    ):
        return FixtureSideAlignment.CONFLICT
    names = tuple(_club(p.name) for p in event.participants)
    official = (_club(OFFICIAL_HOME), _club(OFFICIAL_AWAY))
    if names == official:
        return FixtureSideAlignment.ALIGNED
    if names == official[::-1]:
        return FixtureSideAlignment.REVERSED
    return FixtureSideAlignment.CONFLICT


def audit_official_chelsea_manchester_united(
    review: CanonicalReview,
) -> IndependentFixtureAudit:
    """Compare Phase-7/8 provisional pairs to the official fixture.

    The caller must supply results of `validate_epl_identity`, which already
    gates team aliases, duplicate source fixture IDs and competition evidence.
    Do not call with arbitrary unreviewed pairs to authorize event identity.
    """
    pairs = tuple(
        (odds, papi)
        for odds, papi in review.provisional_pairs
        if _odds_matches_official(odds)
    )
    if len(pairs) != 1:
        return IndependentFixtureAudit(
            OFFICIAL_MATCH_ID,
            False,
            None,
            "no unique Phase-7/8 provisional pair matches the official schedule",
        )
    orientation = _papi_orientation(pairs[0][1])
    if orientation is FixtureSideAlignment.CONFLICT:
        return IndependentFixtureAudit(
            OFFICIAL_MATCH_ID,
            False,
            orientation,
            "OddsPapi participant names, roles, status or start conflict",
        )
    return IndependentFixtureAudit(
        OFFICIAL_MATCH_ID,
        True,
        orientation,
        "official fixture agrees with provisional names and kickoff; "
        "provider fixture IDs and OddsPapi home/away semantics remain unverified",
    )


def main() -> int:
    """Read fixed official-source references without connecting to any APIs."""
    print(
        f"Independent Premier League reference {OFFICIAL_MATCH_ID}: "
        f"{OFFICIAL_HOME} (home) vs {OFFICIAL_AWAY} (away); "
        f"{OFFICIAL_KICKOFF.isoformat()} UTC."
    )
    print(f"Official source: {OFFICIAL_MATCH_URL}")
    print(
        "Source metadata check: official home, away and kickoff independently "
        "documented as of 2026-10-28."
    )
    print(
        "Provider source IDs, OddsPapi participant1/2 orientation, "
        "bookmaker-specific terms and account-level provider rights: "
        "NOT VERIFIED. Quote authorization BLOCKED."
    )
    print("API attempts = 0; odds requests = 0; no data saved.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
