# Provider adapter contract

## Purpose

The provider layer is ArbiScan's anti-corruption boundary around bookmakers, odds aggregators, exchanges, and synthetic sources. Networking, authentication, vendor SDK types, provider-specific payloads, and provider-specific exceptions stop at this boundary.

The arbitrage engine does **not** import provider adapters. It consumes only canonical domain data produced by later normalization/matching/book-construction stages.

## Public API

`arbiscan.providers` exposes:

- `ProviderAdapter`;
- `ProviderCapabilities` / `ProviderCapability`;
- `ProviderHealth` / `ProviderHealthState`;
- `RateLimitSnapshot`;
- `ProviderError` / `ProviderErrorKind`;
- `ProviderOperation`;
- `ProviderCallPolicy` / `ProviderExecutor`;
- provider-neutral source records;
- optional `CanonicalIdHooks`;
- `FakeProvider` / `FakeProviderFixtures`.

## Adapter operations

Every provider implements:

```text
provider metadata
capabilities
canonical_id_hooks
supported_sports()
discover_competitions(sport)
discover_events(competition_external_id, time window)
fetch_odds(external_event_id)
stream_odds(external_event_ids)
health()
rate_limit()
```

Streaming is part of the interface even when unsupported. A provider that does not declare `ODDS_STREAMING` must fail the stream operation with generic `ProviderErrorKind.UNSUPPORTED` rather than exposing an implementation-specific exception.

## Source records

The adapter validates untrusted/raw provider payloads and emits immutable provider-neutral records:

- `SourceCompetition`;
- `SourceParticipant`;
- `SourceEvent`;
- `SourceMarket`;
- `SourceSelectionQuote`;
- `OddsSnapshot`.

These records intentionally retain source identifiers, labels, status text, and odds format. They are structurally safe but **not yet semantically canonical**.

For example, a source market labelled `Full Time Result` is not automatically a canonical `MATCH_WINNER_3_WAY` market. That decision belongs to normalization/market alignment, where settlement rules can be evaluated explicitly.

## Canonical ID hooks

`CanonicalIdHooks` is an optional narrow interface for known mappings from source records to existing canonical IDs. It does not create canonical objects and does not permit guessing.

Unknown or ambiguous mappings return `None` and must remain unresolved until later normalization/matching logic can decide safely.

## Failure model

Only `ProviderError` crosses the adapter boundary for runtime provider failures. Stable categories include authentication, authorization, invalid request, throttling, timeout, transport failure, upstream failure, malformed response, unsupported capability, and internal adapter failure.

Each error carries:

- provider identity;
- operation;
- error category;
- retryability;
- optional `retry_after`.

Provider-specific HTTP/SDK exception classes must be translated inside the adapter.

## Timeout and retry policy

Calls should execute through `ProviderExecutor`.

The executor provides:

- an explicit per-attempt timeout;
- bounded attempt count;
- exponential backoff capped by configuration;
- bounded jitter;
- `retry_after` awareness;
- no retry for non-retryable errors;
- fail-closed wrapping of untranslated exceptions;
- unmodified propagation of task cancellation.

A retry always invokes a fresh call factory. Coroutine objects must not be reused across attempts.

## Rate-limit metadata

`RateLimitSnapshot` can represent:

- total request limit;
- remaining requests;
- reset timestamp;
- retry-after interval.

Providers that do not expose usable metadata return `None` and do not declare `RATE_LIMIT_METADATA`.

## Shared conformance tests

Every adapter must run the reusable contract suite under `tests/contract/providers/conformance.py` against deterministic/sanitized fixtures.

The suite verifies at minimum:

- stable provider identity;
- sport discovery;
- competition discovery;
- event discovery;
- odds retrieval;
- health identity;
- rate-limit identity when present;
- deterministic repeated reads;
- streaming capability semantics.

Provider-specific tests remain additive; passing custom tests does not replace conformance testing.

## Phase boundary

Phase 4 proves the provider port and one deterministic in-memory implementation. Phase 5 may expand the fake/synthetic data into stale odds, suspended markets, malformed cases, partial outages, profitable/non-profitable arbitrage fixtures, and the first network-free vertical pipeline.
