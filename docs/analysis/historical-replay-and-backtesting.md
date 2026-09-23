# Historical replay and backtesting

Phase 18 provides deterministic offline analysis over canonical quote history.

## Corpus

`HistoricalQuoteCorpus` contains strictly chronological `HistoricalQuoteBatch`
records. `from_quotes()` groups canonical quotes by ingestion time and produces a
stable SHA-256 corpus digest.

The digest allows two code/configuration versions to be compared against the same
historical evidence without relying on a mutable filename or database location.

## Replay clock

For each historical batch:

```text
detector_time = batch.observed_at + configured_detection_latency
```

Before evaluation at that detector time, replay applies every quote batch that would
already have been observable through the production transport-aware live store. Each
transport retains its own latest accepted observation; out-of-order updates and
excessive source clock skew are rejected using `BacktestConfig.clock_skew_tolerance`
(five seconds by default). Eligible observations are consolidated by executable
bookmaker price slot. Equal-time conflicting feeds suppress that slot, as in live scans.

The configured freshness window is applied before consolidation. Market construction
then uses the normal production `build_market_books()` path. Only markets supported by
the generic arbitrage settlement policy are evaluated. An explicitly scoped market
that requires a different settlement path, such as Draw No Bet, is rejected.

## Detection and actionability

A complete market book is passed through the normal `evaluate_market()` function.
Positive evaluations become canonical `Opportunity` objects.

When an `ActionabilityPolicy` is configured, the same Phase-12
`revalidate_opportunity()` logic is run at the simulated detector time. Reports
therefore distinguish:

- theoretical detections;
- modeled actionable detections.

An actionable historical detection is still not a claim of realized execution.

## Opportunity duration

A market-level opportunity interval opens when theoretical arbitrage first appears and
closes at the first subsequent replay instant where it is absent. The report records:

- start and end;
- detection count;
- maximum theoretical margin;
- whether the interval was ever actionable;
- whether it remained open at end-of-stream.

## Latency sensitivity

`run_latency_sensitivity()` replays one fixed corpus under multiple non-negative
detection delays.

This measures whether short-lived signals disappear when the detector sees historical
updates later. It does not manufacture intermediate market states that were never
present in the corpus.

## Stale-data false positives

For each replay instant, the strict configured freshness result is compared with a
counterfactual that keeps the same accepted transport observations but widens only the
freshness window enough to admit older currently-known quotes. Both runs apply the
same conflict-safe consolidation after their respective freshness gates.

A theoretical arbitrage visible only in that relaxed run is recorded as a stale-data
false positive.

## Provider comparison

Provider metrics include:

- observed canonical quote count;
- count of quotes selected into the multi-provider best-price book;
- provider-only complete-book count;
- provider-only theoretical detection count;
- provider-only actionable detection count when actionability is modeled.

Provider-only detections answer a different question from best-price contribution and
are therefore reported separately.

## Matching quality

`evaluate_matching_quality()` evaluates externally labeled event-matching decisions.

A correct canonical identity is a true positive. A spurious non-null prediction is a
false positive. A missing expected identity is a false negative. A wrong non-null
identity counts as both false positive and false negative.

Precision and recall are calculated with controlled Decimal precision.

## Persistence

`SqliteAuditStore.load_quotes()` loads retained canonical quote history
chronologically with optional time and provider filters. The Phase-18 integration test
persists quote evidence, reloads it, constructs a corpus, and proves repeated replay
produces identical output.

## What Phase 18 does not claim

Phase 18 does not infer realized P&L from historical prices.

Unless explicitly modeled, reports exclude or cannot prove:

- wager acceptance;
- account-specific limits;
- price changes between detection and action;
- partial exchange matching;
- unavailable balance;
- bookmaker restrictions;
- manual execution latency;
- settlement disputes or rule differences not represented canonically.

See ADR-0024.
