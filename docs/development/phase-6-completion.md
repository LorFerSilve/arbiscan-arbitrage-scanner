# Phase 6 completion record

Status: **Complete**

Phase 6 validates ArbiScan's provider architecture against a legitimate real-world odds-data source while preserving the architecture-first boundaries established in Phases 0–5.

## Selected provider

The first real integration is **The Odds API V4**. The provider decision and public API/terms review were verified on 2026-09-13 and are documented in `docs/providers/the-odds-api.md`.

The Phase 6 implementation deliberately limits the default request scope to the current MVP semantics:

```text
regions=eu
markets=h2h
oddsFormat=decimal
includeSids=true
```

Broader odds-format conversion, fuzzy identity resolution, and generalized market normalization remain later-phase responsibilities.

## Verification

PR #8 validated the Phase 6 implementation through the repository's protected pull-request workflow.

The final implementation-quality run before this completion record verified:

- `uv lock --check` succeeded;
- Ruff formatting: **100 files already formatted**;
- Ruff linting: **all checks passed**;
- strict mypy: **0 issues in 67 source files**;
- pytest: **82 / 82 tests passed**;
- `pip-audit`: **no known vulnerabilities found**;
- CodeQL dedicated PR scan: **no new alerts in code changed by this pull request**;
- CodeQL Python analysis: **success**;
- CodeQL GitHub Actions analysis: **success**.

CI does not require or receive a live provider credential and does not call the live odds API. Sanitized deterministic fixtures exercise the same parser, adapter contract, canonical normalization path, and arbitrage pipeline used by the runtime implementation.

## Exit criteria mapping

### A legitimate first real odds-data source has been selected and documented

Satisfied by the The Odds API V4 provider review and `docs/providers/the-odds-api.md`, which records API scope, authentication, rate/quota behavior, bookmaker/source identity, compliance boundary, and deliberately deferred functionality.

### The real provider satisfies the Phase 4 adapter contract

Satisfied by `TheOddsApiProvider` and the shared provider conformance suite in `tests/contract/providers/test_the_odds_api_contract.py`.

The adapter supports sport discovery, source competition discovery, event discovery, odds snapshots, health checks, and rate-limit metadata. Streaming remains explicitly unsupported rather than being simulated.

### Real payload shapes are structurally validated without live CI credentials

Satisfied by sanitized V4-shaped fixtures for sports, events, and event odds plus fixture-backed unit, contract, and integration tests.

Invalid JSON, invalid schema data, and provider-neutral source-model validation failures are translated to `ProviderErrorKind.MALFORMED_RESPONSE`; provider-specific or source-model exceptions do not leak through the adapter boundary.

### Rate-limit and failure behavior is explicit

Satisfied by parsing the documented `x-requests-remaining`, `x-requests-used`, and `x-requests-last` headers into rate-limit metadata and telemetry. HTTP authentication, authorization, invalid-request, rate-limit, upstream, and transport failures are translated into the shared provider error taxonomy. Numeric `Retry-After` metadata is retained when supplied.

### Provider telemetry reflects validated operations

Satisfied by backend-neutral provider telemetry that emits operation-level success only after the corresponding response has passed JSON, schema, and source-model validation. HTTP `2xx` alone is not considered a successful provider operation, and preparatory internal calls do not emit premature high-level success events.

### Aggregator identity and bookmaker price origin remain distinct

Satisfied by the Phase 6 extension to source-market provenance and ADR-0006. The Odds API remains the source/transport provider while the bookmaker that supplied a market price becomes the canonical quote provider.

This prevents multiple bookmaker prices delivered by one aggregator from being incorrectly collapsed under a single provider identity.

### Freshness remains part of correctness

Satisfied by retaining bookmaker-market update timestamps on `SourceMarket.source_timestamp` and evaluating freshness at market level where available.

The vertical slice also now distinguishes **live mode** from **replay mode**. Live mode samples its evaluation timestamp after provider collection, preventing network latency from causing fresh snapshots to be rejected as future ingestion. Explicit replay `as_of` timestamps remain authoritative so historical causality checks are not weakened.

### The real provider reaches the existing canonical arbitrage pipeline

Satisfied by `tests/integration/test_phase6_the_odds_api_vertical_slice.py`, which proves that a sanitized real V4 payload can travel through ingestion, strict canonical mapping, bookmaker attribution, best-price selection, and the existing arbitrage engine to an opportunity without bypassing the established domain contracts.

## Review findings resolved

PR review identified three material correctness issues and all are covered by regression tests:

1. **Live evaluation timing** — fixed by post-collection evaluation-time sampling in live mode while preserving deterministic replay semantics.
2. **Source-model validation leakage** — fixed by translating source-model validation failures to `MALFORMED_RESPONSE` at the provider boundary.
3. **Premature telemetry success** — fixed by delaying success until operation-level validation completes and suppressing success from preparatory internal calls.

The dedicated regression coverage is in `tests/unit/providers/test_the_odds_api_review_regressions.py`, while the live timing case is exercised by the Phase 6 integration test.

## Security and credential boundary

- `.env.example` contains only the `THE_ODDS_API_KEY` variable name with no credential value.
- The configuration object's representation excludes the secret.
- Provider errors and telemetry do not include authenticated request query strings.
- The concrete transport requires HTTPS endpoints.
- CI and CodeQL execute without live provider credentials.

## Deferred by design

Phase 6 does not implement:

- fuzzy participant or competition aliases;
- generic cross-provider event matching;
- generalized market-semantic normalization;
- fractional or American odds conversion;
- totals, handicaps, and broader market families;
- production best-price market-book policy;
- real-time streaming ingestion;
- persistence;
- automated bet placement.

These remain assigned to later roadmap phases and must not be inferred from the existence of the first real provider adapter.

## Next dependency

With this completion record validated and PR #8 merged, the next roadmap dependency is **Phase 7 — Normalization engine**.
