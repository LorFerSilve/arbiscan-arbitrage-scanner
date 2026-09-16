# Phase 15 — User-facing dashboard and alerts

Phase 15 adds a read-only presentation boundary on top of the validated backend model. It intentionally does not turn ArbiScan into a packaged local application or introduce an HTTP/web-server deployment requirement.

## Implemented boundary

- validated dashboard projection models for opportunities and individual legs;
- filtering by sport, competition, price provider, minimum ROI, minimum guaranteed profit, and active/inactive lifecycle state;
- explicit visibility of opportunity state, age, exact provider/odds per leg, recommended stake amounts, guaranteed payout/profit, currency, assumptions, and provenance;
- dependency-free HTML rendering with escaping of untrusted display values;
- channel-independent `AlertTracker` semantics for newly observed opportunities, material changes, and transitions into inactive states;
- deterministic alert deduplication that ignores refresh-only age changes while treating financial/provenance changes as material;
- inactive opportunities are excluded by default and can only be included explicitly.

## Calculation boundary

The dashboard does not recalculate odds, stakes, ROI, payout, or guaranteed profit. Those values are projected from backend results and validated for representational sanity before rendering. Keeping presentation logic mathematically passive prevents UI code from becoming a second source of truth.

Concrete browser notifications, email, Discord, Telegram, or other delivery transports are intentionally outside the Phase 15 core boundary. They may consume the channel-independent alert events later without changing the dashboard semantics.

## Security and product boundary

All rendered text is HTML-escaped. The dashboard remains read-only and introduces no wager execution, credential handling, fund movement, or provider-specific raw schemas.

A local launcher, web server, packaged executable, deployment manifest, and end-user installation flow are not Phase 15 exit criteria. Those should only be introduced when the underlying engine and provider coverage are mature enough to justify productization.

## Validation evidence

`tests/unit/test_dashboard.py` verifies:

- rejection of invalid numeric/financial projections;
- dashboard filtering across the documented dimensions;
- visibility of backend financial context and provenance;
- HTML escaping of untrusted values;
- alert creation, material-change detection, expiry/invalidation notification, and deduplication.

The Phase 15 implementation is contained under `src/arbiscan/dashboard/` and documented in `docs/product/dashboard-and-alerts.md`.

## Exit-criteria mapping

- **UI never hides quote age or provider attribution:** the projection carries age and per-leg provider identity and the renderer exposes them.
- **Displayed calculations exactly match backend calculations:** presentation code consumes supplied backend-calculated financial values and does not implement competing arithmetic.
- **Stale opportunities disappear or are clearly invalidated:** stale/invalidated/expired lifecycle states are hidden by default and remain explicitly representable when requested.

## Phase 16 hand-off

Phase 15 is complete without requiring a runnable end-user application. The next dependency is Phase 16 multi-provider expansion, whose readiness requirements are documented in `docs/providers/phase-16-readiness.md`.
