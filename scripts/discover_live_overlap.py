"""One-shot, quota-bounded discovery of matching football events across two APIs.

This deliberately stops BEFORE requesting or retaining odds prices. Candidate
event pairs are not confirmed canonical matches or arbitrage opportunities.
"""

from __future__ import annotations

import argparse
import asyncio
import os
import re
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from urllib.parse import urlsplit

from arbiscan.domain import Sport
from arbiscan.providers import (
    AsyncHttpTransport,
    HttpResponse,
    HttpTransportError,
    OddsPapiConfig,
    OddsPapiProvider,
    ProviderError,
    SourceCompetition,
    SourceEvent,
    TheOddsApiConfig,
    TheOddsApiProvider,
    UrllibAsyncHttpTransport,
)
from scripts.audit_official_fixture import (
    OFFICIAL_MATCH_ID,
    audit_official_chelsea_manchester_united,
    observed_provider_ids_for_official_fixture,
    unique_official_odds_anchor,
)
from scripts.validate_epl_identity import validate_epl_identity

THE_ODDS_HOST = "api.the-odds-api.com"
ODDSPAPI_HOST = "api.oddspapi.io"
ODDS_FREE_ROUTES = frozenset({"/v4/sports", "/v4/sports/soccer_epl/events"})
PAPI_DISCOVERY_ROUTES = frozenset({"/v4/account", "/v4/sports", "/v4/tournaments", "/v4/fixtures"})
PAPI_PAID_ROUTES = frozenset({"/v4/sports", "/v4/tournaments", "/v4/fixtures"})
PAPI_BUDGET = 3
START_TOLERANCE = timedelta(minutes=5)


class DiscoveryOnlyTransport:
    """Whitelist exact routes and reserve quota before each outgoing request."""

    def __init__(
        self,
        *,
        host: str,
        routes: frozenset[str],
        billable_routes: frozenset[str],
        max_billable: int,
        upstream: AsyncHttpTransport | None = None,
    ) -> None:
        self.host = host
        self.routes = routes
        self.billable_routes = billable_routes
        self.max_billable = max_billable
        self.upstream = upstream or UrllibAsyncHttpTransport()
        self.billable_attempts = 0

    async def get(
        self, *, url: str, query: Mapping[str, str], timeout_seconds: float
    ) -> HttpResponse:
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.netloc != self.host
            or parsed.path not in self.routes
            or parsed.query
            or parsed.fragment
        ):
            raise HttpTransportError("live discovery blocked a non-allowlisted endpoint")
        if parsed.path in self.billable_routes:
            if self.billable_attempts >= self.max_billable:
                raise HttpTransportError("live discovery quota cap reached")
            # Count even failed/timeout calls: OddsPapi may bill errors.
            self.billable_attempts += 1
        return await self.upstream.get(url=url, query=query, timeout_seconds=timeout_seconds)


def _england_premier_league(
    competitions: tuple[SourceCompetition, ...],
) -> SourceCompetition | None:
    candidates = [
        item
        for item in competitions
        if item.name.casefold() in {"premier league", "english premier league"}
        and (item.region or "").casefold() in {"england", "england clubs"}
    ]
    return candidates[0] if len(candidates) == 1 else None


def _team_key(name: str) -> str:
    tokens = re.findall(r"[a-z0-9]+", name.casefold())
    if tokens and tokens[-1] in {"fc", "cf"}:
        tokens.pop()
    return " ".join(tokens)


def _same_match(left: SourceEvent, right: SourceEvent) -> bool:
    if left.sport is not Sport.FOOTBALL or right.sport is not Sport.FOOTBALL:
        return False
    if len(left.participants) != 2 or len(right.participants) != 2:
        return False
    if abs(left.scheduled_start - right.scheduled_start) > START_TOLERANCE:
        return False
    if right.source_status.casefold() not in {"pre-game", "pre-match", "not started"}:
        return False
    left_names = {_team_key(p.name) for p in left.participants}
    right_names = {_team_key(p.name) for p in right.participants}
    return len(left_names) == 2 and left_names == right_names


def _events_in_window(
    events: tuple[SourceEvent, ...],
    *,
    starts_after: datetime,
    starts_before: datetime,
) -> tuple[SourceEvent, ...]:
    """Keep only events within the requested window, without remote date filters."""
    return tuple(
        event for event in events if starts_after <= event.scheduled_start <= starts_before
    )


def candidate_pairs(
    odds_events: tuple[SourceEvent, ...], papi_events: tuple[SourceEvent, ...]
) -> tuple[tuple[SourceEvent, SourceEvent], ...]:
    """Return only unique one-to-one candidate pairs (never assert canonical identity)."""
    return tuple(
        (left, right)
        for left in odds_events
        for right in papi_events
        if _same_match(left, right)
        and sum(_same_match(left, item) for item in papi_events) == 1
        and sum(_same_match(item, right) for item in odds_events) == 1
    )


async def run_discovery(
    odds_key: str,
    papi_key: str,
    *,
    odds_only: bool = False,
    verify_official: bool = False,
    reference_now: datetime | None = None,
    odds_upstream: AsyncHttpTransport | None = None,
    papi_upstream: AsyncHttpTransport | None = None,
) -> int:
    odds_transport = DiscoveryOnlyTransport(
        host=THE_ODDS_HOST,
        routes=ODDS_FREE_ROUTES,
        billable_routes=frozenset(),
        max_billable=0,
        upstream=odds_upstream,
    )
    papi_transport = DiscoveryOnlyTransport(
        host=ODDSPAPI_HOST,
        routes=PAPI_DISCOVERY_ROUTES,
        billable_routes=PAPI_PAID_ROUTES,
        max_billable=PAPI_BUDGET,
        upstream=papi_upstream,
    )
    odds = TheOddsApiProvider(config=TheOddsApiConfig(api_key=odds_key), transport=odds_transport)
    papi: OddsPapiProvider | None = None
    if not odds_only:
        papi = OddsPapiProvider(config=OddsPapiConfig(api_key=papi_key), transport=papi_transport)
    now = (reference_now or datetime.now(UTC)).astimezone(UTC)
    ends = now + timedelta(days=7)

    try:
        # No billable OddsPapi call until The Odds API free event discovery passes.
        odds_quota = await odds.rate_limit()
        if odds_quota is None or odds_quota.remaining is None:
            print("Stopped: The Odds API quota metadata unavailable.")
            return 1

        odds_competitions = await odds.discover_competitions(Sport.FOOTBALL)
        api_league = next((x for x in odds_competitions if x.external_id == "soccer_epl"), None)
        if api_league is None:
            print("Stopped: soccer_epl is not active at The Odds API.")
            return 1

        # The provider documents second-precision UTC filters; Python's
        # datetime.isoformat() adds microseconds for "now", which can cause
        # 422 validation errors. This zero-credit endpoint supports fetching
        # the league's event list without optional time parameters.
        all_odds_events = await odds.discover_events(api_league.external_id)
        odds_events = _events_in_window(
            all_odds_events,
            starts_after=now,
            starts_before=ends,
        )
        if odds_only:
            print(
                f"The Odds API free event discovery passed: {len(odds_events)} "
                "EPL fixtures within 7 days. OddsPapi discovery skipped."
            )
            return 0

        # Inspect all returned source IDs before local time filtering. A
        # conflicting record outside the seven-day window must still block.
        complete_anchor = (
            unique_official_odds_anchor(all_odds_events) if verify_official else None
        )
        in_window_anchor = (
            unique_official_odds_anchor(odds_events) if verify_official else None
        )
        if verify_official and (
            complete_anchor is None
            or in_window_anchor is None
            or complete_anchor.external_id != in_window_anchor.external_id
        ):
            print(
                "Official fixture verification stopped: no unique and safe "
                "Chelsea vs Manchester United home/away event in The Odds API "
                "free metadata. OddsPapi was not contacted."
            )
            return 1

        assert papi is not None  # Only constructed for full two-provider discovery.
        papi_quota = await papi.rate_limit()
        if papi_quota is None or papi_quota.remaining is None or papi_quota.remaining < PAPI_BUDGET:
            print("Stopped: OddsPapi quota unavailable or below discovery budget.")
            return 1

        papi_competitions = await papi.discover_competitions(Sport.FOOTBALL)
        papi_league = _england_premier_league(papi_competitions)
        if papi_league is None:
            print("Stopped: no unique England Premier League in OddsPapi catalog.")
            return 1

        papi_events = await papi.discover_events(
            papi_league.external_id, starts_after=now, starts_before=ends
        )
        if verify_official:
            review = validate_epl_identity(api_league, odds_events, papi_league, papi_events)
            evidence = observed_provider_ids_for_official_fixture(review)
            if evidence is None:
                print(
                    "Official fixture verification BLOCKED: no unique Phase 7/8 "
                    "pair agrees with official home/away, start, status and "
                    "safe provider identifiers. No IDs promoted."
                )
                return 1
            print(
                f"Official Premier League reference {OFFICIAL_MATCH_ID}: "
                "Chelsea (home) vs Manchester United (away); "
                "2026-10-31T12:30:00+00:00 UTC."
            )
            print(f"The Odds API observed soccer_epl event ID: {evidence.the_odds_api_event_id}")
            print(
                "The Odds API source roles: home=Chelsea; "
                "away=Manchester United. Team labels are source-derived, "
                "not independent numeric team IDs."
            )
            print(f"OddsPapi observed fixtureId: {evidence.oddspapi_fixture_id}")
            print(f"OddsPapi observed tournamentId: {evidence.oddspapi_competition_id}")
            print(
                "OddsPapi participant1Id: "
                f"{evidence.oddspapi_participant1_id} "
                f"({evidence.oddspapi_participant1_name})"
            )
            print(
                "OddsPapi participant2Id: "
                f"{evidence.oddspapi_participant2_id} "
                f"({evidence.oddspapi_participant2_name})"
            )
            print(
                "OddsPapi participant order versus official fixture: "
                f"{evidence.oddspapi_order_vs_official.value.upper()}."
            )
            print(
                "Observed provider IDs are linked by an independent official "
                "schedule check; this does NOT prove OddsPapi's participant1/2 "
                "home-away semantics, bookmaker settlement rules or data-use rights."
            )
            print("Quote authorization BLOCKED; no odds, prices or files requested.")
            return 0

        pairs = candidate_pairs(odds_events, papi_events)
        print(
            f"Next 7 days: The Odds API {len(odds_events)} fixtures; "
            f"OddsPapi {len(papi_events)} fixtures; "
            f"{len(pairs)} strict one-to-one candidates."
        )
        for a, _b in pairs[:10]:
            names = " vs ".join(participant.name for participant in a.participants)
            print(f"Candidate: {names} | {a.scheduled_start.isoformat()}")
        if not pairs:
            print("No exact candidates; aliases or coverage may differ. No odds fetched.")
        review = validate_epl_identity(api_league, odds_events, papi_league, papi_events)
        print(
            f"Phase 7/8 identity review: {len(review.provisional_pairs)} "
            "provisional matches; "
            f"{review.unresolved_papi_events} OddsPapi unresolved; "
            f"{review.excluded_odds_events} Odds API excluded; "
            f"{review.apparent_reversed_order} apparent participant-order reversals."
        )
        independent = audit_official_chelsea_manchester_united(review)
        if (
            independent.reviewed_provisional_pair
            and independent.papi_order_relative_to_official is not None
        ):
            print(
                "Official Premier League fixture 2645278: provisional pair "
                f"agrees with independent schedule; OddsPapi participant order "
                f"relative to reference = {independent.papi_order_relative_to_official.value}. "
                "Provider IDs and OddsPapi home/away role meaning remain unverified."
            )
        else:
            print(
                "Official Premier League fixture 2645278: "
                "no unique schedule-consistent Phase 7/8 pair."
            )
        print(
            "Quote-eligible canonical matches: 0. OddsPapi participant1/2 "
            "are not verified as home/away; market settlement is also unverified."
        )
        return 0
    except ProviderError as error:
        source = "The Odds API" if error.provider_id == odds.provider.id else "OddsPapi"
        # Source adapters return sanitized messages; expose only an HTTP code,
        # not raw provider response content or credential-bearing request URLs.
        http_status = re.search(r"HTTP ([1-5][0-9]{2})", str(error))
        detail = f"; HTTP {http_status.group(1)}" if http_status else ""
        print(f"Discovery stopped: {source} {error.operation} ({error.kind.value}{detail}).")
        return 1
    finally:
        print(
            "API requests: The Odds API billable odds calls = 0; "
            f"OddsPapi billable calls attempted = {papi_transport.billable_attempts}"
            f"/{PAPI_BUDGET}. No odds were requested or saved."
        )


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--execute", action="store_true", help="Allow a one-shot metadata discovery"
    )
    parser.add_argument(
        "--odds-only",
        action="store_true",
        help="Check only free The Odds API EPL events; use with --execute",
    )
    parser.add_argument(
        "--verify-official",
        action="store_true",
        help=(
            "Inspect only Chelsea v Manchester United 2026-10-31 source IDs "
            "and participant order; requires --execute, max 3 paid OddsPapi "
            "metadata calls and no odds"
        ),
    )
    args = parser.parse_args()
    if args.verify_official and (not args.execute or args.odds_only):
        print(
            "Official fixture ID inspection requires --execute and cannot "
            "be combined with --odds-only. No API requests made."
        )
        return 2
    if not args.execute:
        print(
            "Dry run: 0 billable The Odds API calls; up to 3 OddsPapi calls "
            "(/sports, /tournaments, /fixtures). No odds or disk storage. "
            "Pass --execute to proceed."
        )
        return 0
    odds_key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    papi_key = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if not odds_key:
        print("Missing THE_ODDS_API_KEY in your local .env.")
        return 2
    if not args.odds_only and not papi_key:
        print("Missing ODDSPAPI_API_KEY in your local .env for full discovery.")
        return 2
    return asyncio.run(
        run_discovery(
            odds_key,
            papi_key,
            odds_only=args.odds_only,
            verify_official=args.verify_official,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
