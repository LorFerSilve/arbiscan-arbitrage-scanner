"""Deterministic HTTP transport and fixtures for The Odds API tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path

from arbiscan.providers.http import HttpResponse

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "providers" / "the_odds_api"


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    url: str
    query: Mapping[str, str]
    timeout_seconds: float


class FixtureHttpTransport:
    """Route requests to local JSON fixtures while recording request metadata."""

    def __init__(self, *, status_code: int = 200, retry_after: str | None = None) -> None:
        self.status_code = status_code
        self.retry_after = retry_after
        self.requests: list[RecordedRequest] = []

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        self.requests.append(
            RecordedRequest(
                url=url,
                query=dict(query),
                timeout_seconds=timeout_seconds,
            )
        )
        headers = {
            "x-requests-remaining": "487",
            "x-requests-used": "13",
            "x-requests-last": "1",
        }
        if self.retry_after is not None:
            headers["retry-after"] = self.retry_after

        if self.status_code != 200:
            return HttpResponse(
                status_code=self.status_code,
                headers=headers,
                body=b'{"message":"fixture upstream error"}',
            )

        if url.endswith("/sports"):
            body = _fixture_bytes("sports.json")
        elif url.endswith("/sports/soccer_epl/events"):
            body = _fixture_bytes("events_soccer_epl.json")
        elif url.endswith(
            "/sports/soccer_epl/events/epl-arsenal-chelsea-20260920/odds"
        ):
            body = _fixture_bytes("odds_event.json")
        else:
            raise AssertionError(f"unexpected fixture request route: {url}")
        return HttpResponse(status_code=200, headers=headers, body=body)


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()
