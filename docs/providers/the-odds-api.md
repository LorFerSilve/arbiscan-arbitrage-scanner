# The Odds API provider

## Status

Phase 6 first real odds-data integration. Provider selection was verified on 2026-09-13.

Official resources:

- product and plans: https://the-odds-api.com/
- V4 API guide: https://the-odds-api.com/liveapi/guides/v4/
- bookmaker coverage: https://the-odds-api.com/sports-odds-data/bookmaker-apis.html
- terms: https://the-odds-api.com/terms/

## Why this provider was selected

The Odds API is a documented odds aggregator with a low-friction starter tier and broad sports/bookmaker coverage. Its V4 API exposes stable event IDs, ISO timestamps, decimal odds, source IDs where available, usage headers, and a documented European bookmaker region. That makes it suitable for validating ArbiScan's Phase 4 provider boundary against real-world aggregator payloads before adding direct bookmaker integrations.

The Phase 6 adapter intentionally defaults to:

```text
regions=eu
markets=h2h
oddsFormat=decimal
includeSids=true
```

This matches the current MVP focus on football 1X2 and two-way match-winner data while avoiding premature implementation of Phase 7's general market/odds normalization.

## Credential

The adapter requires one runtime secret:

```text
THE_ODDS_API_KEY
```

Never commit the value. `.env.example` contains the variable name only. The adapter's configuration hides the credential from `repr`, errors and telemetry contain no request URL/query string, and CI uses local fixtures rather than a live credential.

Example construction:

```python
import os

from arbiscan.providers import TheOddsApiConfig, TheOddsApiProvider

provider = TheOddsApiProvider(
    config=TheOddsApiConfig(api_key=os.environ["THE_ODDS_API_KEY"]),
)
```

## Supported Phase 6 operations

The adapter implements the Phase 4 provider contract for:

- supported sport discovery;
- source competition discovery;
- event discovery;
- event odds retrieval;
- health checks;
- usage/rate-limit metadata.

Streaming is explicitly unsupported in this phase.

### Source competition model

The Odds API's sport keys such as `soccer_epl` are represented as `SourceCompetition` records. They are provider-local discovery identities, not canonical competition IDs.

Phase 6 maps only provider sport groups that ArbiScan already represents canonically:

- `Soccer` -> `Sport.FOOTBALL`;
- `Tennis` -> `Sport.TENNIS`;
- motorsport group variants -> `Sport.MOTORSPORT`.

Unknown groups are not guessed.

## Aggregator versus bookmaker identity

The most important architectural finding from the first real integration is that the source vendor and price origin are different concepts.

For example:

```text
The Odds API (aggregator/source)
  -> Pinnacle (bookmaker/price origin)
  -> Unibet (bookmaker/price origin)
```

An `OddsSnapshot.provider_id` therefore identifies The Odds API, while every flattened `SourceMarket` may carry its own `price_provider`. During strict canonical normalization, that underlying bookmaker becomes `OddsQuote.provider_id`.

This prevents prices from multiple bookmakers delivered by one aggregator from being incorrectly attributed to one source.

## Freshness

The event-odds V4 schema exposes update timestamps at bookmaker-market granularity. `SourceMarket.source_timestamp` preserves that timestamp. Strict normalization evaluates freshness per market when available and falls back to snapshot timestamps only when necessary.

This matters because two bookmakers in the same API response may have prices of different ages.

## Quota handling

The adapter reads the documented response headers:

```text
x-requests-remaining
x-requests-used
x-requests-last
```

They feed both `RateLimitSnapshot` and provider telemetry. HTTP `429` is translated to `ProviderErrorKind.RATE_LIMITED`, is retryable, and preserves a numeric `Retry-After` value when supplied.

Under the V4 quota model, sport and event discovery endpoints do not consume odds quota. Event-odds cost is based on unique requested markets multiplied by requested regions when odds are returned. With Phase 6's default one region (`eu`) and one market (`h2h`), a populated request normally costs one credit under the documented formula.

## Error policy

The adapter translates provider failures into the shared provider error taxonomy:

- `400` -> invalid request;
- `401` -> authentication;
- `403` -> authorization;
- `429` -> rate limited;
- `5xx` -> retryable upstream failure;
- network failures -> retryable transport failure;
- invalid JSON/schema -> malformed response.

Provider-specific exceptions do not escape the adapter boundary.

## CI and fixtures

CI never calls the live API. Sanitized fixtures under `tests/fixtures/providers/the_odds_api/` reproduce the documented V4 shapes for:

- `/sports`;
- `/sports/{sport}/events`;
- `/sports/{sport}/events/{eventId}/odds`.

The fixture values are deterministic test data and must not be interpreted as historical bookmaker prices. The same adapter parser and canonical pipeline used in production are exercised against those fixtures.

## Deliberately deferred

Phase 6 does **not** add:

- fuzzy participant aliases;
- generic cross-provider event matching;
- broad market-semantic normalization;
- fractional/American odds conversion;
- totals or handicaps;
- production market-book policy;
- persistence;
- WebSocket/streaming ingestion;
- automated bet placement.

Those remain assigned to later roadmap phases.

## Compliance boundary

Using an authorized data API does not remove jurisdictional or licensing obligations. The provider's terms assign responsibility for lawful use to the customer. ArbiScan remains a scanner/reporting system; automated wager placement is outside the initial product boundary.
