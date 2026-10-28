"""Offline Phase-19 external-attestation intake and human-review checklist.

No network, API credentials, bookmaker calls, file writes or activation.
A user-supplied JSON record CANNOT establish that an email is genuine.
A complete record is only READY_FOR_MANUAL_REVIEW, never approved.
"""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from datetime import date
from enum import StrEnum
from pathlib import Path
from typing import Any

from scripts.audit_phase19_market_evidence import OFFICIAL_MATCH_ID
from scripts.prepare_live_odds import ReadinessEvidence

MAX_INPUT_BYTES = 32_768
ALLOWED_GATES = ("soccer_role_semantics", "bookmaker_settlement", "oddspapi_data_rights")


class ReviewState(StrEnum):
    MISSING = "MISSING"
    INCOMPLETE = "INCOMPLETE"
    CONFLICT = "CONFLICT"
    READY_FOR_MANUAL_REVIEW = "READY_FOR_MANUAL_REVIEW"


@dataclass(frozen=True, slots=True)
class GateFinding:
    gate: str
    state: ReviewState
    missing_fields: tuple[str, ...]
    reason: str


@dataclass(frozen=True, slots=True)
class AttestationReview:
    findings: tuple[GateFinding, ...]
    quote_authorized: bool = False
    production_authorized: bool = False

    @property
    def ready_for_manual_review(self) -> int:
        return sum(item.state is ReviewState.READY_FOR_MANUAL_REVIEW for item in self.findings)


def empty_packet() -> dict[str, Any]:
    """Scaffold contains NO invented vendor correspondence or permission."""
    return {
        "schema_version": 1,
        "official_match_id": OFFICIAL_MATCH_ID,
        "attestations": [],
    }


def _valid_date(value: object) -> bool:
    if not isinstance(value, str) or len(value) != 10:
        return False
    try:
        date.fromisoformat(value)
    except ValueError:
        return False
    return True


def _string_field(entry: dict[str, object], field: str) -> bool:
    value = entry.get(field)
    return isinstance(value, str) and bool(value.strip()) and len(value) <= 1024


# These are *provenance/scope fields*, not a vendor authorization parser.
# No raw evidence text is printed, echoed, saved or treated as permission.
_COMMON = (
    "issuer",
    "channel",
    "received_on",
    "source_reference",
    "reviewer",
    "reviewed_on",
)
_FIELDS: dict[str, tuple[str, ...]] = {
    "soccer_role_semantics": (
        "sport",
        "fixture_field_meaning",
        "home_away_exception_policy",
        "applicability",
    ),
    "bookmaker_settlement": (
        "bookmaker_slug",
        "market_name",
        "regulation_period",
        "abandoned_match_policy",
        "postponement_policy",
        "neutral_venue_policy",
        "cross_feed_market_evidence",
    ),
    "oddspapi_data_rights": (
        "subscription_scope",
        "storage_retention",
        "local_replay",
        "derived_dashboard",
        "jurisdiction",
        "redistribution_limits",
    ),
}
_EXPECTED_ISSUERS = {
    "soccer_role_semantics": "OddsPapi",
    "bookmaker_settlement": "Pinnacle",
    "oddspapi_data_rights": "OddsPapi",
}


def _entry_review(gate: str, entry: dict[str, object]) -> GateFinding:
    mandatory = (*_COMMON, *_FIELDS[gate])
    missing = tuple(
        field
        for field in mandatory
        if not (_valid_date(entry.get(field)) if field in {"received_on", "reviewed_on"} else _string_field(entry, field))
    )
    if missing:
        return GateFinding(gate, ReviewState.INCOMPLETE, missing, "Required review metadata is absent.")
    if entry["issuer"] != _EXPECTED_ISSUERS[gate]:
        return GateFinding(
            gate, ReviewState.CONFLICT, (), "Issuer does not match the gate's required source."
        )
    if entry["channel"] not in {"vendor_support_reply", "official_bookmaker_rules"}:
        return GateFinding(
            gate, ReviewState.CONFLICT, (), "Evidence channel is not an accepted primary source."
        )
    if gate == "bookmaker_settlement" and (
        entry["bookmaker_slug"] != "pinnacle"
        or entry["market_name"] != "soccer_regulation_1x2"
    ):
        return GateFinding(
            gate, ReviewState.CONFLICT, (), "Bookmaker or market scope does not match the audit."
        )
    if gate == "soccer_role_semantics" and entry["sport"] != "soccer":
        return GateFinding(
            gate, ReviewState.CONFLICT, (), "A different sport cannot establish soccer roles."
        )
    if gate == "oddspapi_data_rights" and entry["jurisdiction"] != "Belgium":
        return GateFinding(
            gate, ReviewState.CONFLICT, (), "Data-use jurisdiction is not Belgium."
        )
    # Human assessment of the actual message and bookmaker quote is mandatory.
    return GateFinding(
        gate,
        ReviewState.READY_FOR_MANUAL_REVIEW,
        (),
        "Metadata complete only: confirm genuine issuer, actual text, account scope and quote identity.",
    )


def review_packet(value: object) -> AttestationReview:
    """Validate an untrusted *local* record; never return executable authorization."""
    if not isinstance(value, dict):
        raise ValueError("packet must be a JSON object")
    if set(value) != {"schema_version", "official_match_id", "attestations"}:
        raise ValueError("unexpected evidence-packet keys")
    if type(value["schema_version"]) is not int or value["schema_version"] != 1:
        raise ValueError("unsupported packet schema")
    if value["official_match_id"] != OFFICIAL_MATCH_ID:
        raise ValueError("packet does not cover the reviewed official fixture")
    records = value["attestations"]
    if not isinstance(records, list) or len(records) > len(ALLOWED_GATES):
        raise ValueError("invalid attestation collection")
    found: dict[str, dict[str, object]] = {}
    for item in records:
        if not isinstance(item, dict) or set(item) - {"gate", *_COMMON, *sum(_FIELDS.values(), ())}:
            raise ValueError("unrecognized attestation fields")
        gate = item.get("gate")
        if not isinstance(gate, str) or gate not in ALLOWED_GATES or gate in found:
            raise ValueError("unknown or duplicate attestation gate")
        found[gate] = item
    findings = tuple(
        _entry_review(gate, found[gate])
        if gate in found
        else GateFinding(gate, ReviewState.MISSING, (), "No direct vendor/bookmaker attestation.")
        for gate in ALLOWED_GATES
    )
    return AttestationReview(findings)


def read_local_packet(path: Path) -> AttestationReview:
    """Cap read size; do not import or fetch URLs or write the evidence anywhere."""
    if not path.is_file() or path.stat().st_size > MAX_INPUT_BYTES:
        raise ValueError("local evidence packet missing or over size limit")
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (UnicodeError, json.JSONDecodeError) as exc:
        raise ValueError("invalid local JSON evidence packet") from exc
    return review_packet(payload)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--packet", type=Path, help="Offline JSON evidence record (metadata only, no secrets)"
    )
    parser.add_argument(
        "--template", action="store_true", help="Print empty JSON template without writing a file"
    )
    args = parser.parse_args()
    if args.template:
        print(json.dumps(empty_packet(), indent=2))
        return 0
    try:
        audit = (
            read_local_packet(args.packet) if args.packet is not None else review_packet(empty_packet())
        )
    except (ValueError, OSError):
        print("Evidence packet invalid or unsafe; no gate can be advanced.")
        return 2
    print(f"Phase 19 external evidence review: official match {OFFICIAL_MATCH_ID}")
    for finding in audit.findings:
        missing = ", ".join(finding.missing_fields) if finding.missing_fields else "none"
        print(f"{finding.gate}: {finding.state.value}; missing_fields={missing}")
        print(f"  {finding.reason}")
    print(f"Items requiring human source verification: {audit.ready_for_manual_review}/3")
    print(f"Current readiness blockers: {len(ReadinessEvidence().blockers())}/4")
    print("Quote authorization BLOCKED; production BLOCKED. No network, odds or writes.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
