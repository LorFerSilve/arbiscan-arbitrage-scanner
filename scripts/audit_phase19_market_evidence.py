"""Public-source Phase 19 role, bookmaker settlement and data-rights audit.

This is an OFFLINE evidence/decision aid. It contains no provider HTTP client
and neither creates a canonical event match nor authorizes an odds request.

The observed Chelsea-Manchester United provider IDs are metadata supplied by
a user-run Phase 19 CLI on 2026-10-28, not independently authenticated
cross-provider IDs or executable quote hooks.
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import StrEnum

from scripts.prepare_live_odds import ReadinessEvidence

OFFICIAL_MATCH_ID = "2645278"
THE_ODDS_API_EVENT_ID = "6601f69175a02f03fb7065aacb538e01"
ODDSPAPI_FIXTURE_ID = "id1000001772221358"
ODDSPAPI_PARTICIPANT1_ID = "38"
ODDSPAPI_PARTICIPANT2_ID = "35"

ODDSPAPI_FIXTURES_DOC = "https://oddspapi.io/us/docs/get-fixtures"
ODDSPAPI_MARKETS_DOC = "https://oddspapi.io/us/docs/get-markets"
ODDSPAPI_FOOTBALL_BLOG = (
    "https://oddspapi.io/blog/football-data-api-betting-predictions/"
)
ODDSPAPI_NFL_BLOG = "https://oddspapi.io/blog/nfl-prediction-market-liquidity/"
PINNACLE_RULES_DOC = "https://www.pinnacle.bet/en/future/betting-rules"
ODDSPAPI_TERMS_DOC = "https://oddspapi.io/en/legal/terms"
THE_ODDS_API_TERMS_DOC = "https://the-odds-api.com/terms-and-conditions.html"


class EvidenceLevel(StrEnum):
    """A fact's provenance is not a grant of market or production rights."""

    PUBLIC_DOCUMENTED = "public_documented"
    USER_OBSERVED_METADATA = "user_observed_metadata"
    MISSING_ATTESTATION = "missing_attestation"


class MatchDisposition(StrEnum):
    """Conservatively classify situations under a published bookmaker rulebook."""

    COMPLETED_REGULATION = "completed_regulation"
    ABANDONED_OR_SHORTENED = "abandoned_or_shortened"
    POSTPONED_OR_UNPLAYED = "postponed_or_unplayed"
    VENUE_CHANGED = "venue_changed"
    EXTRA_TIME_OR_SHOOTOUT = "extra_time_or_shootout"
    UNKNOWN = "unknown"


@dataclass(frozen=True, slots=True)
class EvidenceFinding:
    code: str
    level: EvidenceLevel
    source: str
    scope: str
    conclusion: str

    def __post_init__(self) -> None:
        if not all((self.code, self.source, self.scope, self.conclusion)):
            raise ValueError("evidence findings require source and scope")
        if not isinstance(self.level, EvidenceLevel):
            raise TypeError("unrecognized evidence level")


@dataclass(frozen=True, slots=True)
class BookmakerRuleReview:
    bookmaker: str
    disposition: MatchDisposition
    documented_regulation_period: bool
    settlement_approved: bool
    reason: str


def review_bookmaker_soccer_1x2(
    *, bookmaker: str, disposition: MatchDisposition
) -> BookmakerRuleReview:
    """Review *public terms*, not a live source/bookmaker market contract.

    Pinnacle publicly documents normal 90m+stoppage soccer match markets;
    for abandoned/shortened games it has a specific 12-hour and 85-minute
    exception, so the normal-score grader must not silently settle them.
    It is not known whether this exact fixture/market is offered by
    Pinnacle through *both* data vendors; even a normal result never
    auto-approves an actionable quote.
    """
    if not isinstance(disposition, MatchDisposition):
        raise TypeError("unknown completion disposition")
    if bookmaker != "pinnacle":
        return BookmakerRuleReview(
            bookmaker,
            disposition,
            False,
            False,
            "no independently reviewed bookmaker-specific 1X2 rules for this slug",
        )
    if disposition is MatchDisposition.COMPLETED_REGULATION:
        return BookmakerRuleReview(
            bookmaker,
            disposition,
            True,
            False,
            "Pinnacle publicly specifies 90 minutes plus stoppage; the exact "
            "bookmaker market and its provider correspondence are not verified",
        )
    if disposition is MatchDisposition.EXTRA_TIME_OR_SHOOTOUT:
        return BookmakerRuleReview(
            bookmaker,
            disposition,
            True,
            False,
            "normal Pinnacle soccer match 1X2 excludes extra time/shootouts, "
            "but the precise market binding remains unverified",
        )
    return BookmakerRuleReview(
        bookmaker,
        disposition,
        True,
        False,
        "Pinnacle has case-specific void/action rules (12-hour noncompletion, "
        "referee-ended after at least 85 minutes, postponement, venue changes); "
        "normal 90-minute WIN/LOSE grading is unsafe without event evidence",
    )


def public_evidence_findings() -> tuple[EvidenceFinding, ...]:
    """Source/claim/scope pairs; their presence is not a permission grant."""
    return (
        EvidenceFinding(
            "fixture_metadata",
            EvidenceLevel.USER_OBSERVED_METADATA,
            "Phase 19 user-run discovery / official PL match 2645278",
            "2026-10-31 Chelsea home v Manchester United away",
            "The Odds API and OddsPapi source IDs observed, OddsPapi 38 Chelsea "
            "as participant1 and 35 Manchester United as participant2; "
            "ALIGNED for this event only",
        ),
        EvidenceFinding(
            "oddspapi_sport_specific_roles",
            EvidenceLevel.MISSING_ATTESTATION,
            ODDSPAPI_FIXTURES_DOC,
            "soccer fixture participant1/2 meaning",
            "official fixture reference calls these first/second participants, "
            "not an explicit soccer-wide home/away invariant",
        ),
        EvidenceFinding(
            "oddspapi_nfl_role_observation",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            ODDSPAPI_NFL_BLOG,
            "NFL example only, not soccer",
            "OddsPapi describes participant1 as NFL home in an NFL article; "
            "cannot extrapolate to football/soccer fixtures",
        ),
        EvidenceFinding(
            "oddspapi_soccer_1x2",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            ODDSPAPI_MARKETS_DOC,
            "soccer market 101, 101/102/103, fulltime",
            "1/X/2 corresponds to home/draw/away and regulation time; "
            "outcome IDs do not certify fixture participant1/2 ordering",
        ),
        EvidenceFinding(
            "pinnacle_normal_regulation",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            PINNACLE_RULES_DOC,
            "Pinnacle soccer default match markets",
            "90 minutes plus stoppage, excluding extra time and penalties",
        ),
        EvidenceFinding(
            "pinnacle_interrupted_rules",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            PINNACLE_RULES_DOC,
            "Pinnacle soccer uncompleted match/venue exceptions",
            "12-hour completion and referee-ended >=85-minute exceptions; "
            "requires exact event and market application evidence",
        ),
        EvidenceFinding(
            "the_odds_api_licence",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            THE_ODDS_API_TERMS_DOC,
            "The Odds API public service terms, updated 2026-08-31",
            "analytics, storage and UI uses permitted under the published "
            "conditions; raw standalone odds-feed redistribution prohibited",
        ),
        EvidenceFinding(
            "oddspapi_licence",
            EvidenceLevel.PUBLIC_DOCUMENTED,
            ODDSPAPI_TERMS_DOC,
            "OddsPapi public service terms",
            "standalone redistribution/resale prohibited; exact local storage, "
            "derived-dashboard use and subscription rights need confirmation",
        ),
        EvidenceFinding(
            "real_quote_market_binding",
            EvidenceLevel.MISSING_ATTESTATION,
            PINNACLE_RULES_DOC,
            "exact same regulated market and bookmaker on both source feeds",
            "no actual bookmaker-specific 1X2 quote has been inspected; "
            "public rules alone do not bind the same market in both feeds",
        ),
        EvidenceFinding(
            "account_data_rights",
            EvidenceLevel.MISSING_ATTESTATION,
            ODDSPAPI_TERMS_DOC,
            "account-specific subscription, retention and local jurisdiction",
            "no account-level or jurisdiction-specific permission can be "
            "inferred from generic public terms",
        ),
    )


@dataclass(frozen=True, slots=True)
class EvidenceAudit:
    findings: tuple[EvidenceFinding, ...]
    blockers: tuple[str, ...]

    @property
    def quote_eligible(self) -> bool:
        """Evidence cannot be used as an API request approval token."""
        return False


def audit_phase19_market_evidence() -> EvidenceAudit:
    """Return evidence with the existing fail-closed quote readiness blockers."""
    findings = public_evidence_findings()
    readiness = ReadinessEvidence()
    return EvidenceAudit(findings, readiness.blockers())


def main() -> int:
    audit = audit_phase19_market_evidence()
    print(f"Phase 19 public-evidence audit for Premier League match {OFFICIAL_MATCH_ID}:")
    print(
        "Observed metadata: The Odds API "
        f"{THE_ODDS_API_EVENT_ID}; OddsPapi {ODDSPAPI_FIXTURE_ID}; "
        "participant1=38 Chelsea FC, participant2=35 Manchester United."
    )
    for finding in audit.findings:
        print(
            f"[{finding.level.value}] {finding.code} | "
            f"scope={finding.scope} | {finding.conclusion}"
        )
        print(f"  Public/source reference: {finding.source}")
    print("Pinnacle 1X2: normal-regulation public rule documented, "
          "but no live bookmaker market binding or special-case settlement approved.")
    print("Quote authorization BLOCKED:")
    for reason in audit.blockers:
        print(f"- {reason}")
    print("No API requests, no odds, no persistent files and no production enablement.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
