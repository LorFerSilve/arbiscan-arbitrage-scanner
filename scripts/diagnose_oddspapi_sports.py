"""Inspect the OddsPapi football sport schema with at most one billable call.

The command uses only /account (unmetered) and /sports (one credit). It prints
schema field paths but never raw provider data, request URLs or credentials.
"""

from __future__ import annotations

import asyncio
import os

from scripts.discover_live_overlap import DiscoveryOnlyTransport

from arbiscan.domain import Sport
from arbiscan.providers import (
    AsyncHttpTransport,
    OddsPapiConfig,
    OddsPapiProvider,
    ProviderError,
    ProviderErrorKind,
    ProviderOperation,
)


async def diagnose_sports(
    api_key: str, *, upstream: AsyncHttpTransport | None = None
) -> int:
    transport = DiscoveryOnlyTransport(
        host="api.oddspapi.io",
        routes=frozenset({"/v4/account", "/v4/sports"}),
        billable_routes=frozenset({"/v4/sports"}),
        max_billable=1,
        upstream=upstream,
    )
    adapter = OddsPapiProvider(
        config=OddsPapiConfig(api_key=api_key), transport=transport
    )
    try:
        quota = await adapter.rate_limit()
        if quota is None or quota.remaining is None or quota.remaining < 1:
            print("Stopped: OddsPapi quota is unavailable or exhausted.")
            return 1

        try:
            # Reproduce the exact first step of discover_competitions. No
            # /tournaments call is allowed in this diagnostic.
            sport = await adapter._resolve_sport_record(
                Sport.FOOTBALL,
                operation=ProviderOperation.DISCOVER_COMPETITIONS,
            )
        except ProviderError as error:
            print(f"OddsPapi football sport lookup failed: {error.kind.value}.")
            if error.kind is ProviderErrorKind.MALFORMED_RESPONSE:
                # This adapter constructs schema diagnostics from field names
                # and types, never from full payloads or the secret API key.
                print(f"Schema detail: {error}")
            return 1
        print(
            f"OddsPapi football sport lookup passed: "
            f"slug={sport.slug}, sportId={sport.external_id}."
        )
        return 0
    except ProviderError as error:
        print(f"OddsPapi quota check failed: {error.kind.value}.")
        return 1
    finally:
        print(
            "OddsPapi billable calls attempted: "
            f"{transport.billable_attempts}/1. No odds data requested or stored."
        )


def main() -> int:
    api_key = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if not api_key:
        print("Missing ODDSPAPI_API_KEY in your local environment.")
        return 2
    return asyncio.run(diagnose_sports(api_key))


if __name__ == "__main__":
    raise SystemExit(main())
