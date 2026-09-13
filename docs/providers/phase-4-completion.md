# Phase 4 completion record

Status: **Complete pending final CI verification on this documentation commit**

## Roadmap exit criteria

### A strict provider integration boundary exists

Satisfied by `ProviderAdapter`, a provider-independent async interface covering:

- canonical provider metadata;
- explicit capability declaration;
- supported-sport discovery;
- competition discovery;
- event discovery with optional time filtering;
- odds snapshot retrieval;
- optional odds streaming;
- provider health;
- rate-limit metadata;
- optional canonical-ID hooks.

The interface does not import or depend on the arbitrage mathematics package.

### Provider-specific data does not leak into the canonical domain

Adapters emit immutable provider-neutral source records after structural validation:

- `SourceCompetition`;
- `SourceParticipant`;
- `SourceEvent`;
- `SourceMarket`;
- `SourceSelectionQuote`;
- `OddsSnapshot`.

These values preserve source identifiers, labels, statuses, and raw odds encoding without pretending that provider semantics are already canonical. Canonical entity resolution, market alignment, odds normalization, freshness policy, and cross-provider matching remain later-phase responsibilities.

### Failure, retry, and cancellation semantics are explicit

Runtime provider failures cross the boundary as structured `ProviderError` values with stable error categories, provider identity, operation name, retryability, and optional `retry_after` metadata.

`ProviderExecutor` provides:

- bounded per-attempt timeouts;
- bounded retry counts;
- exponential backoff;
- bounded jitter;
- a true post-jitter `max_backoff_seconds` cap;
- provider `retry_after` support as an upstream minimum wait;
- fail-closed wrapping of untranslated adapter exceptions;
- unmodified task-cancellation propagation.

Provider-specific HTTP/SDK exceptions are required to be translated inside concrete adapters.

### Rate limits and optional capabilities are modeled explicitly

`RateLimitSnapshot` models request limits, remaining capacity, reset timestamps, and retry-after intervals when a provider exposes those values.

Capabilities are declared rather than inferred. In particular, streaming support is independent of whether a stream currently has queued updates: a supported but quiet stream is valid and yields no updates rather than being treated as unsupported.

### A deterministic fake provider proves the complete contract

`FakeProvider` implements the full Phase 4 adapter interface in memory and supports:

- deterministic discovery and snapshot reads;
- optional streaming capability;
- supported-but-quiet streams;
- health and rate-limit fixtures;
- optional canonical-ID hooks;
- scripted generic provider failures;
- scripted operation delays for timeout/cancellation tests;
- immutable source fixtures with graph validation.

The fake provider is deliberately a contract-proof implementation, not the broader Phase 5 synthetic scenario matrix.

### Shared conformance tests exist

`tests/contract/providers/conformance.py` contains reusable assertions intended for every future provider adapter. The fake provider runs through the same contract in both streaming and non-streaming configurations.

The suite and provider-specific regressions cover:

- stable provider identity;
- deterministic repeated reads;
- sport/competition/event discovery;
- odds retrieval;
- health and rate-limit identity;
- streaming support and unsupported behavior;
- a supported but quiet stream;
- structural DTO validation;
- retryable and non-retryable failures;
- timeout translation;
- retry-after behavior;
- jitter/backoff caps;
- task cancellation;
- failure isolation from immutable fixtures.

### Provider failure cannot corrupt domain state

Provider fixtures/source records are immutable. Retry/failure control state is isolated from returned domain/source data, and regression coverage verifies that a failed provider call does not alter subsequent deterministic reads.

### Adding a provider does not require arbitrage-engine changes

Phase 4 adds the provider boundary and tests without modifying the `src/arbiscan/arbitrage/` package. New adapters are expected to implement `ProviderAdapter` and pass the shared conformance suite rather than extending the mathematics core.

## Verified CI result before this completion-record commit

The Phase 4 pull request was validated on the repository's pinned Python 3.13.15 / uv toolchain with:

- `uv lock --check`: passed;
- Ruff format check: passed;
- Ruff lint: passed;
- strict mypy: **no issues in 44 source files**;
- pytest: **58 tests passed**;
- `pip-audit`: **no known vulnerabilities found**;
- CodeQL Python: passed;
- CodeQL Actions: passed.

The final documentation commit that adds this record and clarifies provider semantics must pass the same repository quality/security gates before merge.

## Review findings resolved during Phase 4

The pull-request review identified three issues before completion:

1. provider and domain `test_models.py` modules collided under pytest's default import mode; explicit test package boundaries now remove that ambiguity;
2. jitter could previously push retry sleep above `max_backoff_seconds`; the cap is now applied after jitter, with provider `retry_after` remaining an intentional upstream minimum;
3. fake streaming capability was initially inferred from whether stream fixtures contained updates; capability is now explicit, allowing supported-but-quiet streams.

Each issue has regression coverage and was revalidated by CI.

## Deliberate Phase 4 boundaries

- Phase 4 does not integrate a real bookmaker or odds API.
- Phase 4 does not normalize source odds into canonical `OddsQuote` values.
- Phase 4 does not perform cross-provider event/entity matching.
- Phase 4 does not build arbitrage books from provider data.
- Phase 4 does not implement persistent ingestion, replay, alerting, or wager execution.
- The larger stale/suspended/malformed/partial-outage synthetic scenario matrix belongs to Phase 5.

## Result

After final CI verification, Phase 4 establishes a reusable provider anti-corruption boundary with deterministic contract tests and a safe in-memory fake implementation. Phase 5 can therefore build the first network-free vertical slice without coupling provider I/O to the arbitrage mathematics core.
