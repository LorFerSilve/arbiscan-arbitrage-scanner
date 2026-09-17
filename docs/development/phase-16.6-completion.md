# Phase 16.6 completion — real multi-source coexistence regressions

Date: 2026-09-18

## Scope

Phase 16.6 proves that ArbiScan's two real transport adapter schemas can coexist
safely under the multi-source provenance, live-state, consolidation, market-book,
and persistence invariants established earlier in Phase 16.

The suite remains fully deterministic, fixture-driven, and credential-free. It does
not enable OddsPapi for production, introduce live-provider availability into CI, or
change provider-neutral arbitrage mathematics.

## Completed validation

1. Added multi-bookmaker football fixtures for both real adapters:
   - The Odds API exposes overlapping Pinnacle plus Bet365;
   - OddsPapi exposes overlapping Pinnacle plus Betfair.
2. Verified both real transports resolve the same canonical Liverpool versus
   Manchester United event and contribute executable prices to one canonical
   regulation 1X2 market.
3. Verified best-price construction can select different price origins from different
   transports in the same market:
   - home from Bet365 via The Odds API;
   - draw from Pinnacle via The Odds API;
   - away from Betfair via OddsPapi.
4. Verified a The Odds API upstream outage is isolated:
   - the failing provider produces issues and no snapshots;
   - the healthy OddsPapi source continues to produce snapshots without provider
     issues.
5. Verified a stale overlapping observation cannot override a fresher eligible
   observation, even when the stale price is artificially more attractive.
6. Verified overlapping Pinnacle observations remain distinct transport observations
   before consolidation but collapse to one executable price-provider slot per
   canonical selection.
7. Verified equal-time materially conflicting Pinnacle observations fail closed and
   emit a `MATERIAL_CONFLICT` diagnostic containing both transport identities.
8. Verified equal-time equivalent observations consolidate deterministically,
   independent of input order, while retaining both transport IDs and both source
   quote IDs in overlap diagnostics.
9. Verified an ordered-football identity mismatch is rejected before normalization
   and cannot leak into the healthy source's canonical market book.
10. Verified suspending one transport observation does not invalidate the independent
    observation of the same bookmaker/selection from the other transport.
11. Verified `ProviderBookPolicy` applies to executable price-provider IDs:
    excluding Bet365 changes best-price selection, while excluding The Odds API's
    transport-provider ID does not incorrectly filter its bookmaker prices.
12. Verified persisted opportunity evidence reconstructs the selected quotes with
    both executable `provider_id` and `transport_provider_id`, including Bet365
    via The Odds API and Betfair via OddsPapi.

## Phase 16.6 exit criteria mapping

The ten mandatory coexistence regressions from
`docs/providers/phase-16-readiness.md` are covered:

1. independent real sources contribute different best prices — covered;
2. source outage isolation — covered;
3. stale source cannot override fresher source — covered;
4. overlapping bookmaker not double counted — covered;
5. equal-time material conflict fails closed — covered;
6. equivalent equal-time overlap consolidates deterministically — covered;
7. unmatched source event cannot enter the shared book — covered;
8. suspended source state is invalidated independently — covered;
9. provider policy operates on executable price origins — covered;
10. persistence retains price-origin and transport provenance — covered.

## Quality evidence

The code-bearing Phase 16.6 head `81455a4490d74500408aa7b6d44d36039843b62a`
passed the repository's full quality gate:

- Ruff formatting: pass (`191 files already formatted`);
- Ruff lint: pass;
- strict mypy: pass (`131 source files`);
- pytest: pass (`228 passed`);
- `pip-audit`: no known vulnerabilities found.

The final pull-request head must retain the same quality/security gates after this
completion record and the development hand-off are committed.

## Handoff

Phase 16.6 is complete. The next roadmap dependency is **Phase 16.7 — observability
and operational tuning**.

Phase 16.7 should validate the second source under the operational surface already
defined for Phase 16:

- provider-specific request, error, and rate-limit metrics;
- last-success and last-update timing;
- source freshness distribution;
- source-specific normalization and matching failure telemetry;
- overlap/conflict diagnostics from ADR-0012;
- health degradation isolated to the affected transport;
- bounded concurrency and polling cadence under the provider quota model.

Phase 16.7 should continue to avoid live-service dependence in ordinary CI; any live
provider checks must remain optional and non-gating.
