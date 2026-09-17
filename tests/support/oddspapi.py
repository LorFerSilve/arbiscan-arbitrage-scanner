"""Deterministic local OddsPapi transport for contract and parser tests."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse

from arbiscan.providers.http import HttpResponse

FIXTURE_ROOT = Path(__file__).parents[1] / "fixtures" / "providers" / "oddspapi"

_ROUTE_FIXTURES: Mapping[str, str] = {
    "/sports": "sports.json",
    "/tournaments": "tournaments_soccer.json",
    "/fixtures": "fixtures_tournament_17.json",
    "/markets": "markets.json",
    "/odds": "odds_fixture.json",
    "/account": "account.json",
}


@dataclass(frozen=True, slots=True)
class RecordedRequest:
    path: str
    query: Mapping[str, str]
    timeout_seconds: float


class FixtureHttpTransport:
    """Serve hand-authored schema-faithful fixtures without external I/O."""

    def __init__(
        self,
        *,
        fixture_overrides: Mapping[str, str] | None = None,
        body_overrides: Mapping[str, bytes] | None = None,
        status_overrides: Mapping[str, int] | None = None,
        retry_after: str | None = None,
    ) -> None:
        self.fixture_overrides = dict(fixture_overrides or {})
        self.body_overrides = dict(body_overrides or {})
        self.status_overrides = dict(status_overrides or {})
        self.retry_after = retry_after
        self.requests: list[RecordedRequest] = []

    async def get(
        self,
        *,
        url: str,
        query: Mapping[str, str],
        timeout_seconds: float,
    ) -> HttpResponse:
        path = urlparse(url).path
        if path.startswith("/v4"):
            path = path.removeprefix("/v4")
        self.requests.append(
            RecordedRequest(
                path=path,
                query=dict(query),
                timeout_seconds=timeout_seconds,
            )
        )

        status_code = self.status_overrides.get(path, 200)
        headers: dict[str, str] = {}
        if self.retry_after is not None:
            headers["retry-after"] = self.retry_after
        if status_code != 200:
            return HttpResponse(
                status_code=status_code,
                headers=headers,
                body=b'{"error":"fixture upstream error"}',
            )

        if path in self.body_overrides:
            body = self.body_overrides[path]
        else:
            fixture_name = self.fixture_overrides.get(path, _ROUTE_FIXTURES.get(path))
            if fixture_name is None:
                raise AssertionError(f"unexpected OddsPapi fixture route: {path}")
            body = _fixture_bytes(fixture_name)
        return HttpResponse(status_code=200, headers=headers, body=body)


def _fixture_bytes(name: str) -> bytes:
    return (FIXTURE_ROOT / name).read_bytes()
