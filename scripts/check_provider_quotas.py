"""Read each configured provider's quota without requesting event or odds data.

The Odds API uses its free /sports endpoint to return usage headers.
OddsPapi uses its unmetered /account endpoint. This command makes one
request per provider and does not save the response or any credentials.
"""

from __future__ import annotations

import asyncio
import os

from arbiscan.providers import (
    OddsPapiConfig,
    OddsPapiProvider,
    ProviderAdapter,
    ProviderError,
    RateLimitSnapshot,
    TheOddsApiConfig,
    TheOddsApiProvider,
)


def _quota_line(name: str, snapshot: RateLimitSnapshot | None) -> str:
    if snapshot is None or snapshot.limit is None or snapshot.remaining is None:
        return f"{name}: authenticated; remaining quota not reported"
    return f"{name}: {snapshot.remaining} of {snapshot.limit} monthly credits remaining"


async def _show_quota(name: str, adapter: ProviderAdapter) -> bool:
    try:
        snapshot = await adapter.rate_limit()
    except ProviderError as error:
        print(f"{name}: quota check failed ({error.kind.value})")
        return False
    print(_quota_line(name, snapshot))
    return True


async def _check_both(odds_key: str, papi_key: str) -> bool:
    odds_ok = await _show_quota(
        "The Odds API", TheOddsApiProvider(config=TheOddsApiConfig(api_key=odds_key))
    )
    papi_ok = await _show_quota(
        "OddsPapi", OddsPapiProvider(config=OddsPapiConfig(api_key=papi_key))
    )
    return odds_ok and papi_ok


def main() -> int:
    odds_key = os.environ.get("THE_ODDS_API_KEY", "").strip()
    papi_key = os.environ.get("ODDSPAPI_API_KEY", "").strip()
    if not odds_key or not papi_key:
        print(
            "Set THE_ODDS_API_KEY and ODDSPAPI_API_KEY in the local ignored .env file, "
            "then run: uv run --env-file .env python -m scripts.check_provider_quotas"
        )
        return 2
    return 0 if asyncio.run(_check_both(odds_key, papi_key)) else 1


if __name__ == "__main__":
    raise SystemExit(main())
