# Phase 14 — Observability and operational resilience

Phase 14 makes degraded scanner behavior explicit without coupling the core domain to a telemetry backend.

## Implemented boundary

- dependency-free structured JSON log records with correlation identifiers and optional provider attribution;
- a backend-neutral log sink contract and deterministic in-memory sink for tests;
- an in-process metrics registry covering the roadmap's minimum provider, normalization, matching, quote, opportunity, rate-limit, and detection-latency signals;
- explicit system-versus-provider health assessment;
- fail-closed readiness when stale quote ratios indicate that scanner output cannot be trusted;
- provider degradation remains diagnosable independently rather than being misreported as total process failure.

Existing resilience mechanisms remain authoritative: provider calls already use bounded per-attempt timeouts and retry/backoff with jitter; realtime ingestion already enforces bounded concurrency, provider-specific rate-limit gating, freshness/stale eviction, clock-skew controls, backpressure-aware polling, and provider isolation. Phase 14 builds an explicit operational observability contract around those mechanisms rather than duplicating them.

Circuit breakers are intentionally not introduced without evidence that they improve the current provider model; the roadmap requires them only where justified. The scanner-only boundary remains unchanged.

## Alertable failure modes

The stable metric/health surface allows an external service or later transport adapter to alert on provider availability/error ratios, rate limiting, canonicalization failures, unmatched/ambiguous events, stale quote ratios, opportunity invalidations, and excessive end-to-end detection latency without importing ingestion or persistence internals.

## Exit-criteria mapping

- **Provider degradation is immediately diagnosable:** provider availability/request/error/rate-limit metrics and provider-specific health state are explicit.
- **Important failure modes have metrics/alerts:** the minimum Phase-14 failure signals have stable metrics; health reasons provide machine-readable alert predicates.
- **System health can be distinguished from provider health:** `HealthReport` exposes system and per-provider states separately, and readiness fails only for system-level untrustworthiness.
