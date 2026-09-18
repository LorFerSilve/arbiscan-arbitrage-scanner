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

The adapter still defaults to:

```text
regions=eu
markets=h2h
oddsFormat=decimal
includeSids=true
```

This preserves the validated winner-market baseline. Phase 17.1 added structured
parameter preservation for explicitly configured `totals` and `spreads` responses.
Phase 17.2 now enables the safe subset of football regulation totals after canonical
normalization, while the default provider request remains unchanged.

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

## Live versus replay evaluation time

The vertical slice has explicit time semantics so network latency cannot make fresh live data look as if it came from the future.

In **live mode**, callers omit `as_of`. Provider collection runs first and `detected_at` is sampled immediately afterwards. Every snapshot therefore has an ingestion timestamp less than or equal to the evaluation timestamp under a monotonic wall-clock assumption.

In **replay mode**, callers supply an explicit timezone-aware `as_of`. That value remains authoritative even if a fixture or replayed snapshot carries a later ingestion timestamp; strict normalization will reject such data as causally invalid. This preserves deterministic historical evaluation rather than silently relaxing the freshness invariant.

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
- invalid JSON/schema or provider-neutral source-model violations -> malformed response.

Provider-specific exceptions and source-model validation exceptions do not escape the adapter boundary.

Telemetry is operation-level rather than raw HTTP-success telemetry: a `2xx` response is not recorded as `SUCCESS` until the response has passed the relevant schema and source-model validation. Preparatory calls inside a larger provider operation do not emit a premature operation success.

## Phase 17.1 structured market parameters

ADR-0013 extends the provider-neutral source contract so advanced-market parameters do
not have to be recovered from labels.

When the adapter is explicitly configured for additional market keys:

- `totals`: every outcome must contain a numeric `point`; all outcomes must agree
  on exactly one point, which is preserved as `SourceMarket.line`;
- `spreads`: every outcome must contain a numeric signed `point`, preserved as
  `SourceSelectionQuote.handicap`;
- unexpected point-bearing market keys fail closed as malformed rather than being
  guessed.

All values cross the adapter boundary as exact finite `Decimal` values. A totals
payload whose Over and Under outcomes disagree on the point is rejected.

This is a **semantic-foundation change**, not a market enablement decision. The default
request remains `h2h`. Football totals require a dedicated Phase 17 market-family
specification covering settlement scope, selection completeness, canonical mappings,
cross-provider equivalence, and end-to-end detection before they can be enabled.
Spreads/Asian handicaps additionally require a documented canonical market-line
anchoring policy before activation.

## Phase 17.2 football regulation totals

When `totals` is explicitly included in `TheOddsApiConfig.markets`, the adapter
accepts the source market only when every outcome carries a numeric `point`, all
outcomes share the same point, and the outcome set is exactly one `Over` plus one
`Under`.

The shared point is preserved as `SourceMarket.line`. Canonical normalization then
requires exact line identity and the Phase 17.2 supported-market gate accepts only
positive regulation-time half-goal lines (`x.5`).

Integer and quarter-line totals may be structurally valid provider data but are not
eligible for generic ArbiScan arbitrage evaluation yet because the current payout
model does not represent PUSH or split settlement.

See [football regulation totals](../markets/football-regulation-totals.md) and
ADR-0014.

## Phase 17.3 football Asian handicap

When `spreads` is explicitly configured, Phase 17.3 treats the source points as
football Asian handicap semantics only after adapter-level orientation checks:

- exactly two outcomes are required;
- outcome labels must exactly match the event home and away participant labels;
- both outcomes require numeric `point` values;
- home and away points must be exact opposites;
- `SourceMarket.line` is the home participant's signed point;
- each source selection retains its own signed handicap.

This provider-specific home anchor is then translated into ArbiScan's canonical
ordered-participant-1 anchor. Strict normalization verifies exact market-line and
selection-handicap equality.

Only regulation-time half-goal lines are currently eligible for the generic
arbitrage/stake pipeline. Integer and quarter spread lines are structurally valid
advanced-market data but remain fail-closed until a settlement-aware payout engine
supports PUSH and split settlement.

The default adapter request remains `h2h`; spreads are opt-in.

See [football Asian handicap](../markets/football-asian-handicap.md) and ADR-0015.

## Phase 17.4 football both teams to score

The provider's documented soccer additional market key `btts` is available through
the event-odds endpoint already used by ArbiScan. The documented outcomes are
`Yes` and `No`.

When `btts` is explicitly configured, the adapter requires:

- exactly two outcomes;
- exactly one `Yes` and one `No`;
- no numeric `point` semantics.

The provider separately documents period-specific variants such as `btts_h1`.
Phase 17.4 therefore treats the exact source market key as part of market identity and
does not infer full-time settlement from a generic BTTS label.

The default request remains `h2h`; BTTS remains opt-in.

See [football BTTS](../markets/football-btts.md) and ADR-0016.

## Phase 17.5 football Draw No Bet

The provider documents the soccer additional market key `draw_no_bet` as match
winner excluding the draw, with a draw returning the bet.

When `draw_no_bet` is explicitly configured, the adapter requires:

- exactly two outcomes;
- outcome labels exactly matching the event home and away participants;
- no numeric `point` values.

The source is translated to the existing canonical Asian Handicap zero shape:

- `SourceMarket.line = 0`;
- both participant source selections carry `handicap = 0`.

Generic normalization still rejects line zero. The market becomes eligible only when
the caller explicitly selects the Phase 17.5 settlement-aware evaluation path, where
the shared draw refund is modeled.

The default provider request remains `h2h`; Draw No Bet is opt-in.

See [football Draw No Bet](../markets/football-draw-no-bet.md) and ADR-0017.

## Phase 17.8 tennis indexed set winner

The provider's current official market list documents the tennis keys:

- `h2h_s1` — moneyline for the first set;
- `h2h_s2` — moneyline for the second set.

When either key is explicitly configured, the adapter requires:

- a tennis event;
- exactly two outcomes;
- outcome labels exactly matching the event participants;
- no numeric `point` semantics.

It emits:

- `h2h_s1` with `SourceMarket.period_index=1`;
- `h2h_s2` with `SourceMarket.period_index=2`;
- no market line;
- no selection handicap.

Malformed participant identity or point-bearing set-moneyline data fails closed at
the adapter boundary.

The default request remains `h2h`; indexed set markets are opt-in.

Phase 17.8 fixtures also prove cross-transport equivalence with OddsPapi Set 1 / Set
2 winner and ADR-0012 consolidation when both transports observe Pinnacle.

Official references:

- https://the-odds-api.com/sports-odds-data/betting-markets.html
- https://the-odds-api.com/sports/tennis-odds.html

See [tennis indexed set winner](../markets/tennis-set-winner.md) and ADR-0018.

## Phase 17.7 tennis game-winner scope

The Phase 17.7 revalidation did **not** identify a fixed individual numbered
`Set N / Game M Winner` market key in the provider's current documented market list.

ArbiScan therefore adds no The Odds API `GAME_WINNER` mapping:

- set/game identity is never inferred from labels;
- `h2h_s1` / `h2h_s2` are set markets, not game markets;
- match `h2h`, spreads, and totals are not reinterpreted as individual game winner;
- no mutable "current game" state is reconstructed from score text.

See [tennis game-market identity](../markets/tennis-game-identity.md) and ADR-0019.

## Phase 17.9 basketball full-event spreads and totals

The provider currently exposes Basketball as a sport group, including NBA under
`basketball_nba`. Its featured `spreads` and `totals` markets are documented
separately from quarter and half variants such as `spreads_q1`, `totals_q1`,
`spreads_h1`, and `totals_h1`.

Phase 17.9 therefore:

- maps the Basketball sport group to `Sport.BASKETBALL`;
- preserves the exact featured spread/total point line;
- anchors a spread line to the event home participant and requires the away point to
  be its exact negation;
- requires an exact Over/Under pair for totals;
- does not infer overtime settlement from the transport key alone;
- requires an explicit `basketball_full_event_bookmakers` allowlist before featured
  basketball spread/total observations can enter the full-event path;
- keeps quarter/half and alternate keys outside that path;
- allows only half-point lines through the generic arbitrage/stake support gate.

The allowlist defaults to empty. Phase 17.9 opts in only Pinnacle and bet365 in its
deterministic test composition after verifying their current official basketball
settlement rules. Any other bookmaker remains fail-closed until separately verified.

The default provider request remains `h2h`; basketball spreads/totals are opt-in.

Official references:

- https://the-odds-api.com/sports/nba-odds.html
- https://the-odds-api.com/sports-odds-data/betting-markets.html

See [basketball full-event spreads and totals](../markets/basketball-full-event-spreads-totals.md)
and ADR-0020.

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
- canonical totals or handicap arbitrage enablement (structured source parameters begin in Phase 17.1);
- production market-book policy;
- persistence;
- WebSocket/streaming ingestion;
- automated bet placement.

Those remain assigned to later roadmap phases.

## Compliance boundary

Using an authorized data API does not remove jurisdictional or licensing obligations. The provider's terms assign responsibility for lawful use to the customer. ArbiScan remains a scanner/reporting system; automated wager placement is outside the initial product boundary.
