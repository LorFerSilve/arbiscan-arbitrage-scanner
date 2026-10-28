# Dashboard and alert boundary

Phase 15 adds a transport-neutral user-facing projection plus dependency-free HTML rendering. The dashboard consumes backend-calculated opportunity values; it does not recompute odds, stakes, ROI, payout, or profit. This keeps displayed calculations identical to the backend source of truth.

Each displayed opportunity carries its lifecycle state, age, exact provider and decimal odds for every leg, recommended stake distribution, guaranteed payout and profit, and provenance. Inactive states (`stale`, `invalidated`, and `expired`) are excluded by default and can only be shown explicitly.

Filtering is supported by sport, competition, provider, minimum ROI, and minimum guaranteed profit. Provider filtering examines the attributed legs rather than provider-specific raw payloads.

`AlertTracker` provides channel-independent alert semantics. It emits a notification for a newly observed opportunity, a material change, or a transition into an inactive state. Repeated identical observations are deduplicated. Increasing age by itself is deliberately not a material change, preventing periodic refreshes from creating alert spam. Concrete browser, email, Discord, or Telegram delivery remains an adapter concern; the roadmap describes these channels as potential integrations rather than mandatory core dependencies.

All rendered text is HTML-escaped. The dashboard remains read-only and does not introduce order execution, credentials, fund movement, or provider-specific schemas.

## Interactive web dashboard handoff — planned Phase 20

The **Phase 15 implementation is a transport-neutral projection and static
HTML rendering contract, not a complete interactive web app**. The
[Phase 20 local web dashboard MVP](phase-20-web-dashboard-mvp.md) will
reuse these contracts behind a read-only Python HTTP adapter and a small
HTML/CSS/vanilla JavaScript frontend.

The first usable browser dashboard will work with deterministic synthetic
fixtures and visibly labeled demo, empty and blocked states, with **no
provider network requests, credentials or odds-credit usage**. It will
expose scanner/provider readiness, event/market overview, filtering, odds
age, attributed stakes/ROI/profit and evidence provenance from the
backend source of truth. An ordinary browser refresh must not perform
provider discovery or spend metered credits.

Only separately approved Phase 19 data rights, source-role/fixture
matching, bookmaker-specific settlement and quote-freshness gates can
activate real provider-backed opportunities. Browser controls never
perform betting or bypass the original Phase 15 lifecycle rules.
