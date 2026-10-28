"""Offline attestation-review tests: missing proof never authorizes quote access."""

from __future__ import annotations

import json
from contextlib import redirect_stdout
from io import StringIO
from pathlib import Path
from tempfile import TemporaryDirectory
from unittest.mock import patch

from scripts.review_phase19_attestations import (
    ReviewState,
    empty_packet,
    main,
    read_local_packet,
    review_packet,
)


def _example_record(gate: str) -> dict[str, object]:
    """Fictional metadata for schema testing, not a vendor statement."""
    common: dict[str, object] = {
        "gate": gate,
        "issuer": "OddsPapi",
        "channel": "vendor_support_reply",
        "received_on": "2026-10-28",
        "source_reference": "TEST-ONLY-NEVER-SENT",
        "reviewer": "TEST-AUDITOR",
        "reviewed_on": "2026-10-28",
    }
    if gate == "soccer_role_semantics":
        return common | {
            "sport": "soccer",
            "fixture_field_meaning": "subject to support verification",
            "home_away_exception_policy": "not yet reviewed",
            "applicability": "v4 soccer fixtures",
        }
    if gate == "bookmaker_settlement":
        return (common | {"issuer": "Pinnacle", "channel": "official_bookmaker_rules"}) | {
            "bookmaker_slug": "pinnacle",
            "market_name": "soccer_regulation_1x2",
            "regulation_period": "90m stoppage",
            "abandoned_match_policy": "manual review needed",
            "postponement_policy": "manual review needed",
            "neutral_venue_policy": "manual review needed",
            "cross_feed_market_evidence": "not yet inspected",
        }
    if gate == "oddspapi_data_rights":
        return common | {
            "subscription_scope": "unconfirmed",
            "storage_retention": "unconfirmed",
            "local_replay": "unconfirmed",
            "derived_dashboard": "unconfirmed",
            "jurisdiction": "Belgium",
            "redistribution_limits": "unconfirmed",
        }
    raise AssertionError("invalid test gate")


def _packet(*items: dict[str, object]) -> dict[str, object]:
    result: dict[str, object] = empty_packet()
    result["attestations"] = list(items)
    return result


def _expect_value_error(value: object) -> None:
    try:
        review_packet(value)
    except ValueError:
        pass
    else:
        raise AssertionError("unsafe packet was accepted")


def test_default_packet_has_no_manufactured_attestations() -> None:
    packet = empty_packet()
    assert packet["attestations"] == []
    result = review_packet(packet)
    assert len(result.findings) == 3
    assert {item.state for item in result.findings} == {ReviewState.MISSING}
    assert not result.quote_authorized
    assert not result.production_authorized


def test_complete_test_metadata_is_review_only_not_vendor_approval() -> None:
    result = review_packet(
        _packet(*(_example_record(gate) for gate in (
            "soccer_role_semantics", "bookmaker_settlement", "oddspapi_data_rights"
        )))
    )
    assert result.ready_for_manual_review == 3
    assert {item.state for item in result.findings} == {ReviewState.READY_FOR_MANUAL_REVIEW}
    assert not result.quote_authorized
    assert not result.production_authorized


def test_incomplete_evidence_lists_missing_fields_without_echoing_vendor_text() -> None:
    result = review_packet(_packet({"gate": "soccer_role_semantics", "issuer": "OddsPapi"}))
    role = result.findings[0]
    assert role.state is ReviewState.INCOMPLETE
    assert "source_reference" in role.missing_fields
    assert "fixture_field_meaning" in role.missing_fields
    assert not result.quote_authorized


def test_wrong_sport_issuer_bookmaker_market_and_jurisdiction_fail_closed() -> None:
    cases = (
        ("soccer_role_semantics", "sport", "nfl"),
        ("soccer_role_semantics", "issuer", "The Odds API"),
        ("bookmaker_settlement", "market_name", "asian_handicap"),
        ("bookmaker_settlement", "bookmaker_slug", "bet365"),
        ("oddspapi_data_rights", "jurisdiction", "United States"),
    )
    for gate, field, bad in cases:
        record = _example_record(gate)
        record[field] = bad
        result = review_packet(_packet(record))
        finding = next(item for item in result.findings if item.gate == gate)
        assert finding.state is ReviewState.CONFLICT
        assert not result.quote_authorized


def test_dates_are_utc_calendar_date_shapes_not_unbounded_input() -> None:
    for bad in ("", "2026-02-30", "yesterday", "2026-10-28T09:00:00Z"):
        record = _example_record("soccer_role_semantics")
        record["received_on"] = bad
        assert review_packet(_packet(record)).findings[0].state is ReviewState.INCOMPLETE


def test_unapproved_channel_rejected_even_if_body_claims_approval() -> None:
    record = _example_record("oddspapi_data_rights")
    record["channel"] = "random_blog"
    record["storage_retention"] = "UNLIMITED APPROVED"
    finding = review_packet(_packet(record)).findings[-1]
    assert finding.state is ReviewState.CONFLICT


def test_packet_schema_rejects_duplicate_unknown_gates_or_unexpected_fields() -> None:
    _expect_value_error(_packet(_example_record("soccer_role_semantics"),
                                _example_record("soccer_role_semantics")))
    _expect_value_error(_packet({"gate": "payments_access"}))
    _expect_value_error(_packet({"gate": "oddspapi_data_rights", "apiKey": "secret"}))
    _expect_value_error({"schema_version": 1, "official_match_id": "2645278",
                         "attestations": [], "production_approved": True})
    _expect_value_error({"schema_version": 2, "official_match_id": "2645278",
                         "attestations": []})
    _expect_value_error({"schema_version": 1, "official_match_id": "wrong",
                         "attestations": []})
    _expect_value_error([])


def test_local_packet_is_bounded_and_does_not_make_http_requests() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "evidence.json"
        path.write_text(json.dumps(_packet(_example_record("soccer_role_semantics"))),
                        encoding="utf-8")
        with patch(
            "arbiscan.providers.UrllibAsyncHttpTransport.get",
            side_effect=AssertionError("HTTP must be disabled"),
        ):
            result = read_local_packet(path)
        assert result.ready_for_manual_review == 1
        path.write_bytes(b"x" * 40_000)
        try:
            read_local_packet(path)
        except ValueError:
            pass
        else:
            raise AssertionError("oversized evidence input accepted")


def test_cli_without_packet_never_reads_secrets_or_contacts_providers() -> None:
    output = StringIO()
    with (
        patch("sys.argv", ["review_phase19_attestations"]),
        patch.dict("os.environ", {"ODDSPAPI_API_KEY": "PRIVATE-KEY-NEVER-LOG"}),
        patch(
            "arbiscan.providers.UrllibAsyncHttpTransport.get",
            side_effect=AssertionError("HTTP must be disabled"),
        ),
        redirect_stdout(output),
    ):
        assert main() == 0
    result = output.getvalue()
    assert "MISSING" in result
    assert "Quote authorization BLOCKED" in result
    assert "PRIVATE-KEY-NEVER-LOG" not in result


def test_cli_forged_response_is_not_accepted_as_permission() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "fake.json"
        record = _example_record("oddspapi_data_rights")
        record["storage_retention"] = "fake: the user claims approval"
        path.write_text(json.dumps(_packet(record)), encoding="utf-8")
        output = StringIO()
        with patch("sys.argv", ["review_phase19_attestations", "--packet", str(path)]), redirect_stdout(output):
            assert main() == 0
        result = output.getvalue()
        assert "READY_FOR_MANUAL_REVIEW" in result
        assert "production BLOCKED" in result
        assert "fake: the user claims approval" not in result


def test_cli_rejects_bad_json_without_echoing_input() -> None:
    with TemporaryDirectory() as folder:
        path = Path(folder) / "bad.json"
        path.write_text("apiKey=PRIVATE-DO-NOT-ECHO", encoding="utf-8")
        output = StringIO()
        with patch("sys.argv", ["review_phase19_attestations", "--packet", str(path)]), redirect_stdout(output):
            assert main() == 2
        assert "PRIVATE-DO-NOT-ECHO" not in output.getvalue()


def test_template_returns_only_empty_packet() -> None:
    output = StringIO()
    with patch("sys.argv", ["review_phase19_attestations", "--template"]), redirect_stdout(output):
        assert main() == 0
    assert json.loads(output.getvalue()) == empty_packet()
