# Phase 16 — Multi-provider expansion readiness

This document is the hand-off from the completed Phase 15 baseline into Phase 16. Its purpose is to make the next implementation sequence explicit before another real odds source is added.

Phase 16 is an expansion of an already validated scanner core. It is not the phase in which ArbiScan becomes a packaged desktop/local application, acquires broad advanced-market support, or begins automated wager placement.

## Baseline entering Phase 16

The repository enters Phase 16 with the following boundaries already implemented and tested:

- provider-neutral canonical domain models;
- deterministic Decimal-based arbitrage mathematics and constrained stake allocation;
- strict async `ProviderAdapter` contract and reusable conformance suite;
- synthetic multi-provider vertical slices;
- one real authorized aggregator integration through The Odds API;
- deterministic normalization with fail-closed unknown semantics;
- cross-provider event matching with ambiguity rejection;
- canonical market-book construction and best-price selection;
- realtime polling, quote freshness, stale eviction, source invalidation, bounded concurrency, rate-limit controls, and provider isolation;
- durable canonical opportunity evidence and replay-oriented persistence;
- actionability/lifecycle revalidation;
- transport-neutral service/API contracts;
- system/provider observability and health separation;
- read-only dashboard projection and channel-independent alert semantics.

The existing runtime already accepts multiple adapter instances. What Phase 16 must prove is that **multiple independent real transport sources can safely coexist** under all existing correctness invariants.

## Terminology that Phase 16 must not blur

### Transport/source provider

The independent API, feed, or vendor through which ArbiScan receives data. It has its own authentication, quota, latency, outage domain, and adapter instance. `ProviderAdapter.provider` and `OddsSnapshot.provider_id` identify this layer.

### Price provider

The bookmaker or exchange that actually offers the executable price. An aggregator may expose many price providers in one response. `SourceMarket.price_provider` is normalized into `OddsQuote.provider_id`.

### Independent source

For the Phase 16 exit criterion, an independent source means a distinct transport/data source with its own operational failure domain. Multiple bookmakers returned by one aggregator are useful price origins, but they do **not** by themselves satisfy the requirement for two independent real data sources.

This distinction follows ADR-0006 and ADR-0012.

## Mandatory architecture gate: overlapping price origins

A second transport source may expose a bookmaker already present inside The Odds API. The current Phase 15 baseline is safe for its single real transport source, but general multi-source operation must not rely on transport observations being permanently disjoint.

Before overlapping real feeds are enabled, Phase 16 must implement ADR-0012:

- preserve transport/source identity explicitly in canonical quote evidence;
- ensure source-observation identifiers cannot collide merely because two feeds report the same bookmaker price at the same timestamp;
- keep live source observations distinct until deterministic consolidation;
- consolidate observations by price origin without counting one bookmaker twice;
- prefer the newest trustworthy observation after ordinary freshness/status filtering;
- fail closed on equal-time materially conflicting observations unless a separately documented policy resolves them;
- persist enough provenance to reconstruct which transport source supplied the selected price.

This is the first cross-cutting Phase 16 dependency. It is not optional even if the first selected second provider happens to have little current bookmaker overlap.

## Provider-selection gate

A candidate second real source must pass `docs/product/provider-integration-checklist.md` before implementation is considered production-eligible.

Preference should be given to a source that provides useful architectural validation rather than merely maximum raw bookmaker count. The candidate should ideally offer:

- official/authorized API access usable from Belgium/EU;
- an operationally independent transport/authentication/quota domain from The Odds API;
- football pre-match 1X2 and/or tennis pre-match two-way winner coverage matching the current MVP semantics;
- stable source event identifiers and usable source timestamps;
- explicit market/selection status behavior;
- documented rate limits and error semantics;
- terms compatible with the intended storage, analysis, and dashboard/alert use;
- fixture capture or another CI-safe test strategy permitted by the provider terms.

Do not select a source solely because it is easy to scrape. Unauthorized scraping, anti-bot circumvention, or brittle HTML parsing remains outside the accepted provider boundary.

## Phase 16 implementation sequence

### 16.1 — Candidate review and decision record

For at least two plausible candidates:

1. complete a compact provider comparison against the integration checklist;
2. document access/licensing/retention constraints;
3. document sports/market coverage and timestamp semantics;
4. document expected bookmaker overlap with the current source;
5. select one source for the first Phase 16 adapter based on correctness and operational suitability, not raw breadth alone.

No production adapter implementation should precede this review.

### 16.2 — Multi-source provenance hardening

Implement ADR-0012 before enabling overlapping coverage:

1. extend canonical/source-observation provenance with explicit transport-source identity;
2. update deterministic identifiers and serialization;
3. migrate persistence compatibly;
4. update live quote-state/consolidation behavior;
5. preserve price-provider identity for market-book and staking semantics;
6. add conflict diagnostics and telemetry.

The change must remain backward compatible with the existing single-source fixture path or include an explicit migration strategy.

### 16.3 — Second provider adapter

Implement the selected provider strictly behind `ProviderAdapter`:

- source-specific authentication/configuration;
- capability declaration;
- sport/competition/event discovery;
- odds retrieval and streaming only if genuinely supported;
- strict source schema validation;
- shared error taxonomy;
- timeouts/retries/rate-limit handling;
- health and telemetry;
- no provider-specific exceptions or schemas escaping the adapter boundary.

### 16.4 — Fixtures and provider conformance

Before cross-provider integration tests:

- add sanitized representative fixtures where terms permit;
- add parser/unit tests for success and malformed/error cases;
- run the shared provider conformance suite;
- verify unknown statuses/markets fail closed;
- verify no live credential is required by CI.

A provider is not considered integrated merely because its API response can be parsed.

### 16.5 — Normalization and event-matching validation

Add only the mappings necessary for currently supported MVP semantics. Validate:

- sport identity;
- competition resolution;
- participant identity and ordering;
- start-time/reschedule behavior;
- market semantics;
- selection semantics;
- status semantics;
- freshness timestamps.

Unknown or ambiguous provider semantics remain rejected rather than guessed.

### 16.6 — Real multi-source coexistence regressions

The Phase 16 suite must include deterministic tests for all of the following:

1. two independent source adapters observe the same canonical event and safely contribute different best bookmaker prices;
2. an outage or rate limit in source A does not corrupt source B state;
3. a stale source cannot override a fresher eligible observation;
4. the same bookmaker observed through two transports is never counted as two independent price providers;
5. same-time conflicting observations for one bookmaker/selection fail closed and expose diagnostics;
6. equivalent same-time observations consolidate deterministically without losing source provenance;
7. unmatched or ambiguous cross-source events cannot enter the same market book;
8. suspended/closed source data is invalidated independently;
9. provider inclusion/exclusion policies continue to operate on executable price origins;
10. persisted opportunity evidence identifies both selected price origin and transport provenance.

These tests should remain fixture-driven and deterministic in CI. Live-provider tests, if added at all, must be optional and must never gate ordinary pull requests on external service availability.

### 16.7 — Observability and operational tuning

For the new source, validate:

- provider-specific request/error/rate-limit metrics;
- last-success/update timing;
- freshness distribution;
- source-specific normalization/matching failures;
- overlap/conflict diagnostics introduced by ADR-0012;
- health degradation isolated to the affected source;
- bounded concurrency and polling cadence under the provider's real quota model.

### 16.8 — Staged enablement and closure

Enable the second source only after contract, semantic, freshness, matching, overlap, persistence, and observability gates pass.

Phase 16 is complete only when:

- at least two independent real transport sources can participate safely in the same scanner runtime;
- their failures remain isolated;
- overlapping bookmaker origins are consolidated without double counting or ambiguous overwrite behavior;
- adding the second provider required no provider-specific changes to arbitrage mathematics or the canonical core;
- the full repository quality gate passes;
- provider documentation, risk register, and Phase 16 completion evidence are updated.

## Explicit non-goals for Phase 16

The following should not be pulled into Phase 16 merely because multi-provider work touches adjacent code:

- a packaged/local launcher or desktop application;
- production deployment manifests or cloud infrastructure;
- automated wager placement;
- in-play/live betting support;
- advanced totals/handicaps/set/outright market expansion assigned to Phase 17;
- historical replay/backtesting expansion assigned to Phase 18;
- source-ranking heuristics based on anecdotal trust rather than measured evidence.

## Definition of ready to start

Phase 16 may begin when this readiness document, ADR-0012, the updated provider checklist/risk register, and completion records through Phase 15 are present on `main` and the normal CI quality gate is green.
