# Phase 18 completion — Historical analysis, replay, and backtesting

**Status:** Technically complete on 2026-09-18.

## Delivered

- deterministic `HistoricalQuoteCorpus` and timestamped quote batches;
- stable SHA-256 corpus identity;
- historical replay using the same production market-book and arbitrage primitives;
- optional reuse of Phase-12 actionability revalidation;
- opportunity interval and duration analysis;
- configurable detection-latency replay;
- stale-data false-positive counterfactual analysis;
- provider quote/best-price/complete-book/detection metrics;
- labeled event-matching precision/recall metrics;
- explicit theoretical-versus-actionable reporting;
- deterministic historical quote loading from `SqliteAuditStore`;
- persistence-to-replay integration coverage;
- ADR-0024 and historical-analysis documentation.

## Correctness boundary

Historical detector output is not reported as realized wagering profit.

A theoretical detection proves only the canonical price relationship. An actionable
detection proves only that the recorded prices also satisfy the configured
`ActionabilityPolicy`. Neither proves order acceptance or actual execution.

## Exit criteria

- **Detection can be reproduced offline:** historical batches replay through the
  production market-book and arbitrage paths.
- **Changes can be evaluated against fixed evidence:** the corpus has a deterministic
  SHA-256 digest and replay output is deterministic.
- **Performance claims distinguish theoretical signal from execution:** theoretical
  and modeled-actionable counts are separate, and the documentation explicitly
  excludes realized-profit claims.

## Next dependency

**Phase 19 — performance and scalability engineering.**

Phase 19 should profile the existing live and replay workloads before changing data
structures or concurrency architecture.
