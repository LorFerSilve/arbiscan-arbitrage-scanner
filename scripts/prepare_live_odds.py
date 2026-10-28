"""Phase-19 one-event live-odds *preflight*, not a live-odds fetcher.

Default mode is offline. --check-quotas makes exactly two non-billable
metadata calls: The Odds API /sports and OddsPapi /account. No discovery,
odds, bookmaker data, storage, retries or automatic quote authorization.

A separate QuoteProbeTransport provides hard-deny, single-event request
caps for a future explicitly approved live quote-observation workflow.
This module does not instantiate or execute that workflow.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from collections.abc import Mapping
from dataclasses import dataclass
from enum import StrEnum
from urllib.parse import urlsplit

from arbiscan.providers import (
    AsyncHttpTransport,
    HttpResponse,
    HttpTransportError,
    OddsPapiConfig,
    OddsPapiProvider,
    ProviderError,
    RateLimitSnapshot,
    TheOddsApiConfig,
    TheOddsApiProvider,
    UrllibAsyncHttpTransport,
)

THE_ODDS_API_HOST = "api.the-odds-api.com"
ODDSPAPI_HOST = "api.oddspapi.io"
# When starting from a fresh process, OddsPapi requires 3 discovery calls
# (sports, tournaments, fixtures) plus 2 quote calls (markets, odds).
ODDSPAPI_TOTAL_FRESH_RUN_RESERVE = 5
THE_ODDS_API_H2H_RESERVE = 1
_EVENT_ID = re.compile(r"[A-Za-z0-9_-]{1,128}\Z")


@dataclass(frozen=True, slots=True)
class ReadinessEvidence:
    """No claims of verification are inferred from provisional fixture matches."""

    canonical_event_verified: bool = False
    independent_home_away_verified: bool = False
    bookmaker_regulation_and_void_rules_verified: bool = False
    provider_data_rights_approved: bool = False

    def blockers(self) -> tuple[str, ...]:
        reasons: list[str] = []
        if not self.canonical_event_verified:
            reasons.append("canonical fixture identity needs independent verification")
        if not self.independent_home_away_verified:
            reasons.append("OddsPapi participant1/2 home-away meaning remains unverified")
        if not self.bookmaker_regulation_and_void_rules_verified:
            reasons.append("bookmaker-specific 1X2 regulation/void rules remain unverified")
        if not self.provider_data_rights_approved:
            reasons.append("provider licence and data-use rights remain unapproved")
        return tuple(reasons)


def quota_ready(
    odds: RateLimitSnapshot | None, papi: RateLimitSnapshot | None
) -> bool:
    """Missing/unknown balances fail closed; no quota is reserved or consumed."""
    return (
        odds is not None
        and papi is not None
        and odds.remaining is not None
        and papi.remaining is not None
        and odds.remaining >= THE_ODDS_API_H2H_RESERVE
        and papi.remaining >= ODDSPAPI_TOTAL_FRESH_RUN_RESERVE
    )


class MetadataOnlyTransport:
    """Allow one unmetered provider endpoint and reject all billable routes."""

    def __init__(
        self,
        *,
        provider: str,
        upstream: AsyncHttpTransport | None = None,
    ) -> None:
        if provider not in {"the_odds_api", "oddspapi"}:
            raise ValueError("unknown metadata provider")
        self.provider = provider
        self.upstream = upstream or UrllibAsyncHttpTransport()
        self.attempts = 0

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        parsed = urlsplit(url)
        host, path, allowed_query = (
            (THE_ODDS_API_HOST, "/v4/sports", frozenset({"apiKey", "all"}))
            if self.provider == "the_odds_api"
            else (ODDSPAPI_HOST, "/v4/account", frozenset({"apiKey"}))
        )
        if (
            parsed.scheme != "https"
            or parsed.netloc != host
            or parsed.path != path
            or parsed.query
            or parsed.fragment
            or set(query) - allowed_query
            or not isinstance(query.get("apiKey"), str)
            or not query["apiKey"]
            or (self.provider == "the_odds_api" and query.get("all") not in (None, "false"))
            or self.attempts >= 1
        ):
            raise HttpTransportError("preflight blocked a non-allowlisted metadata request")
        self.attempts += 1
        return await self.upstream.get(
            url=url, query=query, timeout_seconds=timeout_seconds
        )


class QuoteProbeSource(StrEnum):
    THE_ODDS_API = "the_odds_api"
    ODDSPAPI = "oddspapi"


class QuoteProbeTransport:
    """Future-only *single discovered event* transport budget firewall.

    It is intentionally not used in this script's CLI. Its caller must first
    independently verify fixture identity, home/away roles, bookmaker-specific
    settlement policy, rights and available credits. It does not make these
    assertions itself or produce canonical odds, quotes or arbitrage.
    """

    def __init__(
        self,
        *,
        provider: QuoteProbeSource,
        external_event_id: str,
        upstream: AsyncHttpTransport,
    ) -> None:
        if not isinstance(provider, QuoteProbeSource):
            raise ValueError("invalid quote probe provider")
        if not isinstance(external_event_id, str) or not _EVENT_ID.fullmatch(
            external_event_id
        ):
            raise ValueError("external event id must be a safe opaque identifier")
        self.provider = provider
        self.external_event_id = external_event_id
        self.upstream = upstream
        self.attempts: dict[str, int] = {}

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        parsed = urlsplit(url)
        if parsed.scheme != "https" or parsed.query or parsed.fragment:
            raise HttpTransportError("quote probe denied unsafe request URL")
        if not isinstance(query.get("apiKey"), str) or not query["apiKey"]:
            raise HttpTransportError("quote probe requires provider authentication")
        if self.provider is QuoteProbeSource.THE_ODDS_API:
            expected_path = (
                f"/v4/sports/soccer_epl/events/{self.external_event_id}/odds"
            )
            allowed = {
                "apiKey", "regions", "markets", "dateFormat", "oddsFormat",
                "includeSids",
            }
            permitted = (
                parsed.netloc == THE_ODDS_API_HOST
                and parsed.path == expected_path
                and set(query) == allowed
                and query["regions"] == "eu"
                and query["markets"] == "h2h"
                and query["dateFormat"] == "iso"
                and query["oddsFormat"] == "decimal"
                and query["includeSids"] in {"true", "false"}
            )
            max_calls = 1
        else:
            expected_path = parsed.path
            permitted = parsed.netloc == ODDSPAPI_HOST and (
                (
                    expected_path == "/v4/markets"
                    and set(query) == {"apiKey", "language"}
                    and query["language"] == "en"
                )
                or (
                    expected_path == "/v4/odds"
                    and set(query) == {
                        "apiKey", "fixtureId", "oddsFormat", "language", "verbosity"
                    }
                    and query["fixtureId"] == self.external_event_id
                    and query["oddsFormat"] == "decimal"
                    and query["language"] == "en"
                    and query["verbosity"] == "3"
                    and self.attempts.get("/v4/markets", 0) == 1
                )
            )
            max_calls = 1
        if not permitted or self.attempts.get(expected_path, 0) >= max_calls:
            raise HttpTransportError("quote probe denied route, scope or quota")
        # Reserve before forwarding: upstream failure might still consume credits.
        self.attempts[expected_path] = self.attempts.get(expected_path, 0) + 1
        return await self.upstream.get(
            url=url, query=query, timeout_seconds=timeout_seconds
        )


async def check_unmetered_quotas(
    odds_key: str,
    papi_key: str,
    *,
    odds_upstream: AsyncHttpTransport | None = None,
    papi_upstream: AsyncHttpTransport | None = None,
) -> bool:
    """Use only the official unmetered quotas, without fetching events or prices."""
    odds_transport = MetadataOnlyTransport(
        provider="the_odds_api", upstream=odds_upstream
    )
    papi_transport = MetadataOnlyTransport(
        provider="oddspapi", upstream=papi_upstream
    )
    odds = TheOddsApiProvider(
        config=TheOddsApiConfig(api_key=odds_key), transport=odds_transport
    )
    papi = OddsPapiProvider(
        config=OddsPapiConfig(api_key=papi_key), transport=papi_transport
    )
    try:
        odds_remaining = await odds.rate_limit()
        papi_remaining = await papi.rate_limit()
        if quota_ready(odds_remaining, papi_remaining):
            print("Quota reserve PASS: at least 1 The Odds API credit and 5 OddsPapi calls.")
        else:
            print("Quota reserve BLOCKED: insufficient or unknown provider balances.")
        print(
            "Quota check only: no billable routes, odds, events, prices, "
            "persistence or arbitrage."
        )
        return quota_ready(odds_remaining, papi_remaining)
    except ProviderError as error:
        source = (
            "The Odds API" if error.provider_id == odds.provider.id else "OddsPapi"
        )
        print(f"Quota check stopped: {source} ({error.kind.value}).")
        return False
    finally:
        print(
            "Preflight network attempts: "
            f"The Odds API free metadata = {odds_transport.attempts}/1; "
            f"OddsPapi unmetered account = {papi_transport.attempts}/1; "
            "paid quote requests = 0."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check-quotas",
        action="store_true",
        help="Only call free /sports and unmetered /account once each",
    )
    args = parser.parse_args()
    print(
        "Phase 19 one-event quote probe PLAN: "
        "The Odds API 1 h2h market x eu region (at most 1 credit); "
        "OddsPapi fresh discovery 3 calls + markets 1 + odds 1 "
        "(at most 5 billable requests)."
    )
    for reason in ReadinessEvidence().blockers():
        print(f"Quote authorization BLOCKED: {reason}.")
    if not args.check_quotas:
        print("Offline planning: 0 API requests, no odds, no disk writes.")
        return 0
    odds_key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    papi_key = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if not odds_key or not papi_key:
        print("Missing local provider API keys in .env; no requests made.")
        return 2
    return 0 if asyncio.run(check_unmetered_quotas(odds_key, papi_key)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
