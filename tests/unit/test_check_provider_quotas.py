"""Offline checks for the provider quota-only preflight output."""

import os
from contextlib import redirect_stdout
from datetime import UTC, datetime
from io import StringIO
from unittest.mock import patch

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


def test_missing_credentials_exits_without_api_calls() -> None:
    output = StringIO()
    with (
        patch.dict(os.environ, {"THE_ODDS_API_KEY": "", "ODDSPAPI_API_KEY": ""}),
        redirect_stdout(output),
    ):
        assert main() == 2

    text = output.getvalue()
    assert "uv run --env-file .env" in text
    assert "ODDSPAPI_API_KEY" in text
