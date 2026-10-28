"""Offline Phase-19 market/role/terms evidence regression tests."""

from __future__ import annotations

from contextlib import redirect_stdout
from io import StringIO
from unittest.mock import patch

from scripts.audit_phase19_market_evidence import (
    ODDSPAPI_FIXTURE_ID,
    OFFICIAL_MATCH_ID,
    EvidenceFinding,
    EvidenceLevel,
    MatchDisposition,
    audit_phase19_market_evidence,
    main,
    public_evidence_findings,
    review_bookmaker_soccer_1x2,
)


def test_source_scope_distinguishes_nfl_home_rule_from_soccer() -> None:
    findings = {item.code: item for item in public_evidence_findings()}
    assert findings["oddspapi_nfl_role_observation"].level is EvidenceLevel.PUBLIC_DOCUMENTED
    assert "NFL example only" in findings["oddspapi_nfl_role_observation"].scope
    assert findings["oddspapi_soccer_score_example"].level is EvidenceLevel.PUBLIC_DOCUMENTED
    assert "not a universal" in findings["oddspapi_soccer_score_example"].conclusion
    assert findings["oddspapi_sport_specific_roles"].level is EvidenceLevel.MISSING_ATTESTATION
    assert "not an explicit soccer-wide" in findings["oddspapi_sport_specific_roles"].conclusion
    assert findings["fixture_metadata"].level is EvidenceLevel.USER_OBSERVED_METADATA
    assert "ALIGNED for this event only" in findings["fixture_metadata"].conclusion


def test_soccer_market_outcome_ids_are_documented_not_fixture_role_attestation() -> None:
    by_code = {finding.code: finding for finding in public_evidence_findings()}
    market = by_code["oddspapi_soccer_1x2"]
    assert market.level is EvidenceLevel.PUBLIC_DOCUMENTED
    assert "101/102/103" in market.scope
    assert "do not certify" in market.conclusion


def test_pinnacle_normal_90_minute_rule_never_auto_authorizes_market() -> None:
    review = review_bookmaker_soccer_1x2(
        bookmaker="pinnacle", disposition=MatchDisposition.COMPLETED_REGULATION
    )
    assert review.documented_regulation_period
    assert not review.settlement_approved
    assert "90 minutes plus stoppage" in review.reason


def test_extra_time_does_not_become_90_minute_outcome() -> None:
    review = review_bookmaker_soccer_1x2(
        bookmaker="pinnacle", disposition=MatchDisposition.EXTRA_TIME_OR_SHOOTOUT
    )
    assert review.documented_regulation_period
    assert not review.settlement_approved
    assert "excludes extra time" in review.reason


def test_abandonment_85_minute_and_12_hour_exceptions_require_actual_evidence() -> None:
    for disposition in (
        MatchDisposition.ABANDONED_OR_SHORTENED,
        MatchDisposition.POSTPONED_OR_UNPLAYED,
        MatchDisposition.VENUE_CHANGED,
        MatchDisposition.UNKNOWN,
    ):
        review = review_bookmaker_soccer_1x2(bookmaker="pinnacle", disposition=disposition)
        assert not review.settlement_approved
        assert "85 minutes" in review.reason
        assert "12-hour" in review.reason


def test_another_bookmakers_rulebook_is_never_inferred_from_pinnacle() -> None:
    for bookmaker in ("bet365", "pinnacle-eu", "", "Pinnacle"):
        review = review_bookmaker_soccer_1x2(
            bookmaker=bookmaker, disposition=MatchDisposition.COMPLETED_REGULATION
        )
        assert not review.documented_regulation_period
        assert not review.settlement_approved
        assert "not independently reviewed" in review.reason


def test_unknown_disposition_fails_closed() -> None:
    try:
        review_bookmaker_soccer_1x2(
            bookmaker="pinnacle",
            disposition="completed_regulation",  # type: ignore[arg-type]
        )
    except TypeError:
        pass
    else:
        raise AssertionError("untyped disposition silently accepted")


def test_public_provider_terms_do_not_approve_account_storage_or_distribution() -> None:
    findings = {item.code: item for item in public_evidence_findings()}
    odds = findings["the_odds_api_licence"]
    papi = findings["oddspapi_licence"]
    assert odds.level is EvidenceLevel.PUBLIC_DOCUMENTED
    assert papi.level is EvidenceLevel.PUBLIC_DOCUMENTED
    assert "storage and UI uses permitted" in odds.conclusion
    assert "subscription rights need confirmation" in papi.conclusion
    assert findings["account_data_rights"].level is EvidenceLevel.MISSING_ATTESTATION


def test_audit_never_promotes_observation_or_public_rule_to_quote_eligibility() -> None:
    audit = audit_phase19_market_evidence()
    assert len(audit.findings) == 11
    assert len(audit.blockers) == 4
    assert not audit.quote_eligible
    assert "home-away" in " ".join(audit.blockers)
    assert "data-use" in " ".join(audit.blockers)


def test_evidence_findings_reject_missing_source_or_invalid_level() -> None:
    try:
        EvidenceFinding("test", EvidenceLevel.PUBLIC_DOCUMENTED, "", "soccer", "fact")
    except ValueError:
        pass
    else:
        raise AssertionError("missing evidence source was accepted")

    try:
        EvidenceFinding("test", "guessed", "https://example.test", "soccer", "fact")  # type: ignore[arg-type]
    except TypeError:
        pass
    else:
        raise AssertionError("unknown evidence disposition was accepted")


def test_offline_cli_needs_no_credentials_and_never_calls_network() -> None:
    output = StringIO()
    with (
        patch.dict(
            "os.environ",
            {"THE_ODDS_API_KEY": "canary-key-123", "ODDSPAPI_API_KEY": "canary-key-456"},
        ),
        patch(
            "arbiscan.providers.UrllibAsyncHttpTransport.get",
            side_effect=AssertionError("no HTTP allowed for offline evidence audit"),
        ),
        redirect_stdout(output),
    ):
        assert main() == 0
    body = output.getvalue()
    assert OFFICIAL_MATCH_ID in body
    assert ODDSPAPI_FIXTURE_ID in body
    assert "Quote authorization BLOCKED" in body
    assert "No API requests" in body
    assert "canary-key-123" not in body
    assert "canary-key-456" not in body
