# Phase 10 — Real-time ingestion and freshness control

Phase 10 turns the earlier deterministic vertical slice into a persistent live-scanning runtime while keeping freshness and provider degradation inside the correctness boundary.

## Implemented boundary

- `RealtimeIngestionRuntime` polls multiple `ProviderAdapter` instances with bounded concurrency;
- provider-specific rate-limit state participates in scheduling and throttling decisions;
- `LiveQuoteStore` retains versioned quote state across cycles instead of rebuilding state from one request batch;
- freshness windows, stale-quote eviction, source suspension/closure invalidation, and clock-skew tolerance are enforced before market-book construction;
- partial provider failures are represented as provider-scoped issues rather than aborting the complete scan cycle;
- polling cadence tracks missed intervals and uses bounded scheduling rather than unbounded work accumulation;
- realtime cycle metrics expose provider latency/errors, accepted/duplicate/rejected quote updates, stale counts, quote age, ingestion-to-detection latency, rate-limit events, market books, and emitted opportunities.

## Correctness and failure behavior

A quote that is stale, explicitly suspended, or otherwise invalidated by the source cannot remain eligible merely because an older copy exists in live state. Invalid data is removed before canonical market books and arbitrage evaluation are produced.

Freshness is evaluated against the most specific trustworthy provider timestamp already preserved by the normalization boundary. The runtime also records its own ingestion/evaluation time, so source time and local processing time remain distinguishable.

The realtime scanner already accepts a tuple of provider adapters. Phase 10 therefore established the orchestration shape required by later multi-provider work, but Phase 10 did not claim that two independent real data sources had been onboarded; that remains Phase 16 scope.

## Validation evidence

The Phase 10 regression suite covers, among other cases:

- an initially valid arbitrage disappearing after its quotes exceed the freshness window;
- explicit provider-market suspension invalidating live quotes immediately;
- provider latency/error/update metrics matching the actual cycle state;
- bounded concurrency and provider-specific realtime controls in unit coverage;
- partial provider failure without corrupting unrelated provider state.

Relevant tests include `tests/integration/test_phase10_realtime_freshness.py` and the realtime-ingestion unit tests under `tests/unit/ingestion/`.

## Exit-criteria mapping

- **Quote freshness is measurable end to end:** quote age, provider request timing, ingestion timing, and ingestion-to-detection latency are explicit cycle metrics.
- **Stale provider data cannot generate actionable signals:** stale and source-invalidated quotes are removed before market-book construction and arbitrage evaluation.
- **Ingestion remains stable under partial provider failure:** provider work is isolated and failures are represented without collapsing the full cycle.

## Deliberately deferred

Phase 10 does not select or enable additional independent real odds sources. Cross-source overlap, duplicate price-origin resolution, and staged multi-provider enablement are Phase 16 concerns.
