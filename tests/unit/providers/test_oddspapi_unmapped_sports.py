"""Unmapped OddsPapi sports cannot block or contaminate football discovery."""

from __future__ import annotations

import asyncio
import json

from arbiscan.domain import Sport
from arbiscan.providers import (
    OddsPapiConfig,
    OddsPapiProvider,
    ProviderError,
    ProviderErrorKind,
)
from tests.support.oddspapi import FixtureHttpTransport


def _adapter(sports: list[dict[str, object]]) -> OddsPapiProvider:
    transport = FixtureHttpTransport(body_overrides={"/sports": json.dumps(sports).encode("utf-8")})
    return OddsPapiProvider(
        config=OddsPapiConfig(api_key="synthetic-not-a-secret"),
        transport=transport,
    )


def _catalogue_with_bad_unmapped_record(
    bad_record: dict[str, object],
) -> list[dict[str, object]]:
    sports: list[dict[str, object]] = [
        {"sportId": 10, "slug": "soccer", "sportName": "Soccer"},
        {"sportId": 11, "slug": "basketball", "sportName": "Basketball"},
        {"sportId": 12, "slug": "tennis", "sportName": "Tennis"},
    ]
    sports.extend(
        {
            "sportId": 100 + index,
            "slug": f"unmapped-sport-{index}",
            "sportName": f"Other sport {index}",
        }
        for index in range(66)
    )
    assert len(sports) == 69
    sports.append(bad_record)
    return sports


def test_unmapped_record_69_with_missing_or_empty_display_name_is_ignored() -> None:
    for record in (
        {"sportId": 999, "slug": "unmapped-extra", "sportName": None},
        {"sportId": 999, "slug": "unmapped-extra", "sportName": ""},
        {"sportId": 999, "slug": "unmapped-extra", "sportName": "  "},
        {"sportId": 999, "slug": "unmapped-extra"},
    ):
        adapter = _adapter(_catalogue_with_bad_unmapped_record(record))
        assert asyncio.run(adapter.supported_sports()) == (
            Sport.BASKETBALL,
            Sport.FOOTBALL,
            Sport.TENNIS,
        )
        competitions = asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
        assert any(competition.name == "Premier League" for competition in competitions)


def test_known_football_slug_still_rejects_missing_display_name() -> None:
    sports = _catalogue_with_bad_unmapped_record(
        {"sportId": 999, "slug": "soccer", "sportName": None}
    )
    adapter = _adapter(sports)
    try:
        asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "sports[69].sportName" in str(error)
    else:
        raise AssertionError("missing sportName for mapped football must be rejected")


def test_unknown_slug_cannot_hide_missing_identity() -> None:
    sports = _catalogue_with_bad_unmapped_record({"sportId": 999, "slug": None, "sportName": None})
    adapter = _adapter(sports)
    try:
        asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "sports[69].slug" in str(error)
    else:
        raise AssertionError("unknown sport with no slug must be rejected")


def test_duplicate_mapped_football_identity_remains_ambiguous() -> None:
    sports = _catalogue_with_bad_unmapped_record(
        {"sportId": 999, "slug": "soccer", "sportName": "Soccer"}
    )
    adapter = _adapter(sports)
    try:
        asyncio.run(adapter.discover_competitions(Sport.FOOTBALL))
    except ProviderError as error:
        assert error.kind is ProviderErrorKind.MALFORMED_RESPONSE
        assert "2 records" in str(error)
    else:
        raise AssertionError("ambiguous football source identity must be rejected")
