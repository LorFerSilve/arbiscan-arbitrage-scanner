# Phase 16.2 completion — multi-source provenance hardening

Date: 2026-09-17

## Scope

Phase 16.2 closes the architectural gap that exists when independent transport feeds can report prices from the same bookmaker or exchange. ArbiScan now keeps two identities separate through normalization, live state, consolidation, and persisted evidence:

- **transport provider** — the API/feed through which ArbiScan observed the quote;
- **price provider** — the bookmaker/exchange whose executable price the quote represents.

`OddsQuote.provider_id` remains the executable price-provider identity used by market books, arbitrage mathematics, provider inclusion/exclusion policy, and staking. `OddsQuote.transport_provider_id` identifies the independent observation source.

## Completed implementation

1. Canonical quotes carry explicit transport provenance while legacy/direct-source quotes deterministically default transport identity to their existing price-provider identity.
2. Canonical serialization is schema version 2 with deterministic schema-version-1 quote migration.
3. Normalized quote observation IDs include both transport provider and price provider, preventing independent feeds from colliding on the same bookmaker/event/market/selection timestamp.
4. `MultiSourceLiveQuoteStore` versions each transport independently by reusing the Phase-10 live-store semantics within isolated transport lanes.
5. Eligible transport observations are consolidated to one executable bookmaker/outcome slot before market-book construction. Newer observations win; equivalent equal-time observations collapse deterministically; equal-time material price/status conflicts fail closed and suppress the executable slot.
6. Explicit source invalidation is transport-specific. An inactive/suspended observation from one feed does not remove an independent feed's still-valid observation of the same bookmaker price origin.
7. The application-facing realtime scanner uses multi-source state by default while still accepting an explicitly supplied legacy `LiveQuoteStore` for backward-compatible tests/custom callers.
8. Consolidation diagnostics retain the contributing transport identities and the scanner emits structured multi-source telemetry with observation count, executable quote count, equivalent-overlap count, material-conflict count, diagnostic codes, and involved transport providers.
9. Persistence continues to index `provider_id` as the executable price origin while canonical serialized quote evidence preserves `transport_provider_id`; reconstructed opportunities therefore retain both identities.

## Safety invariants

- The same bookmaker is never treated as two independent arbitrage legs merely because two feeds observe it.
- Transport identity never replaces bookmaker/exchange identity in market-book or staking semantics.
- A stale observation cannot override a fresher eligible observation from another transport.
- Equal-time materially conflicting observations fail closed rather than selecting an arbitrary feed.
- Equivalent equal-time observations consolidate deterministically without discarding their diagnostic provenance.
- Source invalidation is isolated to the transport that supplied the inactive state.
- Existing single-source fixtures and direct-provider callers remain valid.

## Regression coverage

Phase 16.2 adds deterministic coverage for:

- independent transport observations surviving simultaneously in live state;
- deterministic equivalent-overlap consolidation;
- newest-eligible-observation selection;
- fail-closed same-time material conflict behavior;
- transport-specific invalidation isolation;
- realtime scanner consolidation and structured conflict telemetry;
- schema-v1 to schema-v2 migration;
- persisted opportunity reconstruction retaining both price-provider and transport-provider provenance.

The repository's normal quality gate remains authoritative for formatting, linting, strict typing, the full test suite, and dependency auditing.

## Handoff

Phase 16.2 is complete at the implementation boundary. The next roadmap dependency is **Phase 16.3 — second provider adapter**. That adapter must remain behind `ProviderAdapter` and must preserve the provenance and consolidation invariants established here.
