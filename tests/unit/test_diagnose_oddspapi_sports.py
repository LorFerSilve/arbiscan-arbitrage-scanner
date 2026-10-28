"""Offline tests for the budgeted OddsPapi schema diagnostic."""

import asyncio
import json
from collections.abc import Mapping
from contextlib import redirect_stdout
from io import StringIO
from urllib.parse import urlsplit

from scripts.diagnose_oddspapi_sports import diagnose_sports

from arbiscan.providers import HttpResponse


class _FakeTransport:
    def __init__(self, sports: object, *, remaining: int = 249) -> None:
        self.sports = sports
        self.remaining = remaining
        self.paths: list[str] = []

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        path = urlsplit(url).path
        self.paths.append(path)
        if path == "/v4/account":
            data: object = {
                "current_subscription_id": "free",
                "subscriptions": [
                    {
                        "subscription_id": "free",
                        "is_active": True,
                        "request_limit": 250,
                        "request_count": 250 - self.remaining,
                    }
                ],
            }
        elif path == "/v4/sports":
            data = self.sports
        else:
            raise AssertionError("unexpected API endpoint")
        return HttpResponse(status_code=200, headers={}, body=json.dumps(data).encode())


def _run(transport: _FakeTransport) -> tuple[int, str]:
    output = StringIO()
    with redirect_stdout(output):
        code = asyncio.run(diagnose_sports("never-print-this-secret", upstream=transport))
    return code, output.getvalue()


def test_schema_diagnostic_reports_field_path_without_raw_data() -> None:
    data = [
        {"sportId": 10, "slug": "soccer", "sportName": "Soccer"},
        {"sportId": 20, "slug": None, "sportName": "Other"},
    ]
    transport = _FakeTransport(data)
    code, output = _run(transport)

    assert code == 1
    assert "malformed_response" in output
    assert "sports[1].slug" in output
    assert "never-print-this-secret" not in output
    assert "sportName" not in output
    assert "1/1" in output
    assert transport.paths == ["/v4/account", "/v4/sports"]


def test_valid_football_sport_passes_with_only_one_metered_call() -> None:
    transport = _FakeTransport(
        [{"sportId": 10, "slug": "soccer", "sportName": "Soccer"}]
    )
    code, output = _run(transport)

    assert code == 0
    assert "slug=soccer, sportId=10" in output
    assert "1/1" in output
    assert transport.paths == ["/v4/account", "/v4/sports"]


def test_empty_allowance_does_not_issue_billable_requests() -> None:
    transport = _FakeTransport([], remaining=0)
    code, output = _run(transport)

    assert code == 1
    assert "exhausted" in output
    assert "0/1" in output
    assert transport.paths == ["/v4/account"]
