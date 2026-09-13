# ADR-0005 — Provider adapter boundary

- Status: Accepted
- Date: 2026-09-13
- Decision owners: ArbiScan maintainers
- Supersedes: N/A
- Superseded by: N/A

## Context

ArbiScan will integrate heterogeneous odds sources with different authentication models, identifiers, payloads, status vocabularies, odds formats, rate limits, and reliability characteristics. If those differences leak into the canonical domain or arbitrage core, every new provider would expand the blast radius of provider-specific behavior.

Phase 4 therefore requires a strict boundary before the first real integration.

## Decision

ArbiScan adopts an async provider-adapter contract with the following rules:

1. Every provider implements `ProviderAdapter`.
2. Provider identity uses the canonical Phase 2 `Provider` entity; credentials and transport configuration never enter that domain object.
3. Adapter methods return immutable, provider-neutral **source records** (`SourceCompetition`, `SourceEvent`, `SourceMarket`, `SourceSelectionQuote`, `OddsSnapshot`) after structural validation.
4. Source records intentionally preserve provider labels/status strings and raw odds encoding. They are not canonical events, markets, selections, or quotes. Semantic normalization remains a later subsystem responsibility.
5. Adapters may expose `CanonicalIdHooks` for already-known source-to-canonical identity mappings. Hooks return canonical IDs only and do not bypass normalization/matching safety rules.
6. Provider capabilities are declared explicitly. Optional streaming and rate-limit metadata may not be inferred from implementation details.
7. All adapter failures crossing the boundary use `ProviderError` with stable `ProviderErrorKind`, retryability, operation, provider identity, and optional `retry_after` metadata.
8. Provider-specific SDK/HTTP exceptions must be translated inside the adapter. The generic executor additionally fails closed by wrapping any untranslated `Exception` as a non-retryable internal provider error.
9. `ProviderExecutor` applies bounded per-attempt timeouts, bounded exponential backoff, optional jitter, retryability checks, and `retry_after` awareness.
10. `asyncio` task cancellation is not translated or retried; cancellation propagates to the caller.
11. Provider records and fixtures are immutable. Failed calls must not partially mutate canonical domain state.
12. Every implementation must pass the reusable provider conformance suite.

## Why source records are not canonical domain objects

Provider discovery happens before later normalization and cross-provider matching phases. Returning canonical `Event`, `Market`, or `OddsQuote` values directly from the I/O adapter would force provider-specific naming and settlement semantics into canonical identity too early.

The adapter therefore owns transport parsing and structural validation. Later layers own semantic normalization, entity resolution, market alignment, freshness policy, and arbitrage book construction.

## Fake provider boundary

Phase 4 includes a deterministic in-memory `FakeProvider` only to prove the complete adapter contract, resilience policy, capability declarations, and shared contract tests without network access.

The broader synthetic scenario matrix and first end-to-end vertical slice remain Phase 5 work. Phase 4 does not implement ingestion orchestration, event matching, market normalization, or arbitrage scanning across fake feeds.

## Consequences

### Positive

- adding a provider does not change the arbitrage engine;
- provider-specific SDK exceptions cannot become application-wide dependencies;
- timeout/retry behavior is consistent across providers;
- source semantics remain inspectable until normalization;
- tests can prove the contract without credentials or network access;
- cancellation remains cooperative and predictable.

### Trade-offs

- adapters require explicit translation and validation code;
- source DTOs add a layer between raw payloads and canonical domain objects;
- streaming retry/resubscription semantics are deferred until an ingestion phase owns stream lifecycle;
- canonical ID hooks are deliberately narrow and cannot replace later semantic matching.

## Revisit triggers

Revisit this ADR if:

- a real provider requires cursor/page semantics that cannot fit the discovery contract cleanly;
- streaming providers require a shared reconnect/resubscription protocol;
- raw payload retention needs a formal encrypted/audited storage contract;
- provider capabilities need market-level rather than adapter-level granularity.
