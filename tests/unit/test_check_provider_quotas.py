"""Offline checks for the provider quota-only preflight output."""

from datetime import UTC, datetime

import pytest
from scripts.check_provider_quotas import _quota_line, main

from arbiscan.providers import THE_ODDS_API_PROVIDER_ID, RateLimitSnapshot


def test_quota_line_reports_actual_remaining() -> None:
    snapshot = RateLimitSnapshot(
        provider_id=THE_ODDS_API_PROVIDER_ID,
        observed_at=datetime(2026, 10, 28, tzinfo=UTC),
        limit=500,
        remaining=487,
    )
    assert _quota_line("The Odds API", snapshot) == (
        "The Odds API: 487 of 500 monthly credits remaining"
    )


def test_missing_quota_metadata_does_not_invent_remaining_credits() -> None:
    assert "not reported" in _quota_line("OddsPapi", None)


def test_missing_credentials_exits_without_api_calls(
    monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    monkeypatch.delenv("THE_ODDS_API_KEY", raising=False)
    monkeypatch.delenv("ODDSPAPI_API_KEY", raising=False)

    assert main() == 2
    output = capsys.readouterr().out
    assert "uv run --env-file .env" in output
    assert "ODDSPAPI_API_KEY" in output
